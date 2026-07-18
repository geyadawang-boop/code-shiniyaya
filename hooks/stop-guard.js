#!/usr/bin/env node
// stop-guard.js v3.5 — Stop hook: turn-end adversarial check (转移包§七: Stop=唯一可靠对抗审查入口)
// v2: pure-confirmation拦截+stall门; v3: clean-exit门(收敛声明须同turn落snapshot)+饱和豁免+结构化turn边界
// v3.2: task-notification边界不作userText(S5)+\bstop\b词边界+饱和豁免共现收窄+最终签收单形态
// v3.3: pre-launch门(第N轮→继声明但未调Workflow/Agent/Task→block 1次,区别于stall门的干净轮计数)
// v3.4: agentLaunched+substantive双正则同步补Workflow(50A终验P0——纯Workflow扫描轮被stall/确认双门漏检)
// v3.5: tool_result边界break防跨turn污染(Scan35 P0——continue导致前一turn的Agent/Write泄漏到当前turn绕过pure-confirmation+pre-launch门)
//       + userStop移除裸"报告"(过宽: "请报告进度"不应禁用保护门) + CONFIRM仅匹配text块(排除tool_use/tool_result块中的done/ok膨化)
// Intercepts pure-confirmation turns (>=2 confirmation words + zero Write/Edit/Agent calls),
// which PreToolUse structurally cannot see (no tool call → echo-guard never fires).
// stop_hook_active contract: max 1 intervention per stop — platform prevents hook self-loop.
// Silent-fail: parse failures → pass through; always exit 0.

const fs = require('fs');
const CONFIRM = /\b(done|ok|final|completed?|verified|confirmed)\b/gi;

function out(o) {
  try { process.stdout.write(JSON.stringify(o)); } catch (e) {}
  process.exit(0);
}

let buf = '';
let fin = false;
function finish() {
  if (fin) return;
  fin = true;
  let p = {};
  try { p = JSON.parse(buf.replace(/^﻿/, '') || '{}'); } catch (e) { out({}); }
  if (p.stop_hook_active) out({}); // already intervened once this stop — must pass

  let lines = [];
  try { lines = fs.readFileSync(p.transcript_path, 'utf8').trim().split('\n'); } catch (e) { out({}); }

  let confirms = 0;
  let substantive = false;
  let turnText = '';
  let userText = '';
  // Walk backwards through the last turn (until real user message). 400-line window:
  // one JSONL line per event; 25-50 Agent waves (rule-24 standard rounds) exceed the old
  // 120 — early Write/Edit must stay visible or a legit converged turn gets a false block.
  for (let i = lines.length - 1; i >= 0 && i > lines.length - 400; i--) {
    let m;
    try { m = JSON.parse(lines[i]); } catch (e) { continue; }
    const c = (m.message && m.message.content) || '';
    const s = JSON.stringify(c);
    if (m.type === 'user') {
      // structural boundary check — substring 'tool_result' misfires when the user pastes
      // hook source/transcripts containing that literal
      const isToolResult = Array.isArray(c) && c.some(b => b && b.type === 'tool_result');
      if (!isToolResult) {
        // v3.2 (Scan 7 S5): task-notification turns are machine boilerplate whose text
        // contains "stops" — matching userStop against it disabled both gates on ~19%
        // of real turns. Boundary stands, but machine messages contribute no userText.
        const flat = typeof c === 'string' ? c : s;
        userText = /task-notification|SYSTEM NOTIFICATION - NOT USER INPUT/.test(flat) ? '' : s;
        break;
      }
      // v3.5: tool_result = turn boundary — break to prevent cross-turn pollution
      // (previous turn's Agent/Write leaking substantive=true into current turn)
      break;
    }
    if (m.type === 'assistant') {
      // v3.5: CONFIRM only on text blocks — tool_use/tool_result names/content
      // (e.g. "Build completed successfully") inflated confirm counts, making
      // pure-confirmation gate's >=2 threshold always true.
      const textBlocks = Array.isArray(c)
        ? c.filter(b => b && b.type === 'text').map(b => b.text || '').join(' ')
        : (typeof c === 'string' ? c : '');
      const textS = JSON.stringify(textBlocks);
      confirms += (textS.match(CONFIRM) || []).length;
      turnText += s;
      if (/"name":"(Write|Edit|MultiEdit|NotebookEdit|Agent|Task|Workflow)"/.test(s)) substantive = true;
    }
  }

  // v2 (v4.7.8): clean-round stall detection — 规则24 turn-terminal obligation at L2.
  // Progress line claims counter < 2 but the turn launched no scan Agent → block once.
  // [01] excludes 2/2 so a converged sign-off turn passes; user stop words protect pauses.
  const stall = /第\d+轮[^"]{0,20}干净轮\s*[01]\s*\/\s*2/.test(turnText);
  const agentLaunched = /"name":"(Agent|Task|Workflow)"/.test(turnText);
  // v3.5: removed bare 报告 (too broad: "请报告进度" shouldn't disarm protection gates)
  const userStop = /(停|\bstop\b)/i.test(userText);
  // v3.3 pre-launch gate: 模型输出"第N轮...→继"(预发射声明)但同turn未调用Workflow/Agent/Task
  // → block 1次,注入要求实际Workflow发射Agent。与stall门区别: stall检查"干净轮<2+未发射",
  // 此门检查"声称发射但实际没发"——无论干净轮计数。饱和行(⚡...→继)豁免:那是放弃发射的信号。
  const preLaunchClaim = /第\d+轮[^"]{0,80}→继/.test(turnText);
  const saturationLine = /⚡[^"]{0,80}\/compact[^"]{0,40}→继/.test(turnText);
  const workflowOrAgentCalled = /"name":"(Workflow|Agent|Task)"/.test(turnText);
  if (preLaunchClaim && !saturationLine && !workflowOrAgentCalled && !userStop) {
    out({ decision: 'block', reason: 'stop-guard: 本turn含预发射声明(第N轮...→继)但未调用Workflow/Agent/Task发射Agent. 请实际调用Workflow发射对应Agent后再停止;或输出⚡饱和行(含/compact)以放弃发射.' });
  }

  // v3: saturation exemption — the mandated ≥55% flow ends with "⚡ … /compact + 继" and
  // deliberately does NOT launch agents (SKILL.md 饱和优先线 overrides 强制扫描).
  // v3.2: require ⚡ and /compact near each other — either alone over-exempted (prose
  // mentioning /compact, Edit payloads containing ⚡).
  const saturationFlow = /⚡[^"]{0,80}\/compact/.test(turnText);
  if (stall && !agentLaunched && !userStop && !saturationFlow) {
    out({ decision: 'block', reason: 'stop-guard: 干净轮<2且本turn未启动扫描Agent(规则24 turn-end统一决策②). 立即启动下轮扫描Agent, 再输出进度行停止. 规则24三硬门任一触发(饱和≥55%/预算不足/在飞)→直接再次停止即放行.' });
  }

  // v3 (Scan 4 carry-forward): clean-exit gate — a convergence declaration (干净轮2/2 or
  // sign-off-form 签收单) must persist a snapshot in the same turn, else the "converged"
  // state is lost on next compact. Bare "签收单" in planning prose ("收敛后→签收单") is
  // excluded by requiring sign-off punctuation/heading forms (最终签收单 included, v3.2).
  const converged = /干净轮\s*2\s*\/\s*2|(?:##|✅)\s*(?:最终)?签收单|签收单[:：]/.test(turnText);
  const snapWritten = /memory[\/\\]{1,4}snapshot-/.test(turnText);
  if (converged && !snapWritten && !userStop) {
    out({ decision: 'block', reason: 'stop-guard: 收敛/签收声明但本turn未写snapshot. 先写 memory/snapshot-<ts>.md(含SNAPSHOT-COMPLETE哨兵+nextAction), 再停止.' });
  }

  if (confirms >= 2 && !substantive) {
    out({ decision: 'block', reason: 'stop-guard: pure-confirmation turn (>=2 confirm words, zero Write/Edit/Agent). Write snapshot + output "⚡…继" progress line, then stop. Do not output more confirmation words.' });
  }
  out({});
}

process.stdin.on('data', c => { buf += c; });
process.stdin.on('end', finish);
process.stdin.on('error', finish);
setTimeout(finish, 1500).unref();
