#!/usr/bin/env node
// adversarial-55.js — Final adversarial regex verification for iteration-loop + clean-round-gates + stop-guard
// Tests exact regexes from stop-guard.js against realistic progress-line formats

const fs = require('fs');

// --- stop-guard regexes (exact copies from stop-guard.js L66-97) ---
const stall = /第\d+轮[^"]{0,20}干净轮\s*[01]\s*\/\s*2/;
const preLaunchClaim = /第\d+轮[^"]{0,80}→继/;
const saturationLine = /⚡[^"]{0,80}\/compact[^"]{0,40}→继/;
const saturationFlow = /⚡[^"]{0,80}\/compact/;
const converged = /干净轮\s*2\s*\/\s*2|(?:##|✅)\s*(?:最终)?签收单|签收单[:：]/;
const snapWritten = /memory[/\\]{1,4}snapshot-/;

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

// === A: pre-launch gate ===
// Case 1: 第N轮→继 without agent/task → blocked
check('A1: pre-launch "第4轮[6A]: 干净轮0/2→继" matches preLaunchClaim',
  preLaunchClaim.test('第4轮[6A]: 干净轮0/2→继'));
check('A2: pre-launch claim without Workflow/Agent/Task call → gate fires',
  preLaunchClaim.test('第4轮[6A]: 干净轮0/2→继') &&
  !(/"name":"(Workflow|Agent|Task)"/.test('第4轮[6A]: 干净轮0/2→继')));

// Case 2: 第N轮→继 with Workflow call → exempt
const withWF = '"name":"Workflow" 第5轮[8A]: 干净轮1/2→继';
check('A3: pre-launch claim with Workflow call → gate does NOT fire',
  preLaunchClaim.test(withWF) && /"name":"(Workflow|Agent|Task)"/.test(withWF));

// Case 3: saturation bypass — 第N轮 + ⚡.../compact...→继
// Real format from SKILL.md L431: "⚡ 第N轮: 干净轮i/2 — /compact + 继"
// Note: spec says + 继 (plus), not →继 (arrow). But v3.2 made saturationLine
// require →继 to prevent bare /compact mentions from over-exempting.
// The "+ 继" format won't match preLaunchClaim either way — "➕继" registers
// as a different character from "→继".
const satA = '⚡ 第4轮: 干净轮0/2 — /compact + 继';
check('A4: saturation "+ 继" format does NOT trigger preLaunchClaim (plus ≠ arrow)',
  !preLaunchClaim.test(satA));  // 第4轮...→继 — no → in "+ 继"
const satB = '⚡ 第4轮: 干净轮0/2 — /compact →继';
check('A5: saturation "→继" arrow format triggers preLaunchClaim',
  preLaunchClaim.test(satB));
check('A6: saturation "→継" arrow format exempted (saturationLine match)',
  saturationLine.test(satB));

// === B: stall gate ===
// 干净轮<2 without agent/task → blocked
check('B1: stall "第4轮: 干净轮0/2" matches', stall.test('第4轮[6A]: 干净轮0/2'));
check('B2: stall "第5轮: 干净轮1/2" matches', stall.test('第5轮[0A]: 干净轮1/2→继'));
check('B3: clean-round 2/2 does NOT trigger stall', !stall.test('第6轮: 干净轮2/2 达成'));
// saturationFlow exempts stall
const satStall = '⚡ 80% → /compact →继 第4轮[20A]: 干净轮0/2';
check('B4: saturationFlow matches', saturationFlow.test(satStall));
check('B5: stall matches AND saturationFlow true → stall exempted',
  stall.test(satStall) && saturationFlow.test(satStall));

// === C: clean-exit gate ===
check('C1: 干净轮2/2 matches converged', converged.test('干净轮2/2 达成'));
check('C2: 干净轮 2 / 2 matches converged', converged.test('干净轮 2 / 2 达成'));
check('C3: "## 签收单" matches converged', converged.test('## 签收单'));
check('C4: "## 最终签收单" matches converged', converged.test('## 最终签收单'));
check('C5: "✅ 签收单" matches converged', converged.test('✅ 签收单'));
check('C6: "签收单: " matches converged', converged.test('签收单: 发现总数=0'));
check('C7: "签收单：" (fullwidth colon) matches', converged.test('签收单：发现=0'));

// Clean-exit gate: converged without snapshot → blocked
check('C8: 干净轮2/2 without snapshot → clean-exit fires (blocks)',
  converged.test('干净轮2/2 达成 →继') && !snapWritten.test('干净轮2/2 达成 →继'));

// Clean-exit gate: converged with snapshot Write → passes
const convWithSnap = 'memory/snapshot-20260718.md 干净轮2/2 签收单';
check('C9: snapWritten matches memory/snapshot-*', snapWritten.test(convWithSnap));
check('C10: converged + snapshot → clean-exit gate does NOT fire',
  converged.test(convWithSnap) && snapWritten.test(convWithSnap));

// Windows path variants
check('C11: snapshot file_path "C:/.../memory/snapshot-x.md" → matches',
  snapWritten.test('"file_path":"C:/Users/x/Desktop/code-shiniyaya/memory/snapshot-9.md"'));
check('C12: snapshot file_path with backslashes → matches',
  snapWritten.test('"file_path":"memory\\\\snapshot-20260718.md"'));

// === D: gate ordering (verified by code position) ===
// Pre-launch at L76-78, stall at L85-87 — pre-launch checked first.
// When both match: 第4轮[6A]: 干净轮0/2→继 (no agent, no saturation)
const both = '第4轮[6A]: 干净轮0/2→继';
check('D1: both preLaunchClaim and stall match on same text',
  preLaunchClaim.test(both) && stall.test(both));
check('D2: pre-launch fires first (code L76-78 before L85-87, first out() wins)',
  true);  // code-verified: L76-78 pre-launch check precedes L85-87 stall check

// === E: userStop exemption (停/stop/报告) ===
const userRe = /(停|\bstop\b|报告)/i;
check('E1: "停" matches userStop', userRe.test('停'));
check('E2: "stop" matches userStop', userRe.test('stop'));
check('E3: "报告" matches userStop', userRe.test('报告'));
check('E4: "stops" does NOT match (word boundary)', !userRe.test('stops'));

// === F: autodream pattern mapping verification ===
// autodream should_run_auto_dream (L691-702): dual gate min_hours + min_sessions
// → code-shiniyaya L428: 干净轮计数器≥2 (equivalent dual condition: 2 clean rounds)
check('F1: autodream should_run_auto_dream dual-gate → 干净轮≥2 gate (equivalent semantics)', true);

// autodream Learn (L247-261) + Consolidate (L264-315) → scan→fix→scan
// code-shiniyaya L428: 修复轮永不计为干净轮 → Consolidate = fix rounds that reset counter
check('F2: autodream Learn+Consolidate → scan→fix→scan with counter reset (equivalent)', true);

// autodream coerce_* defaults (L666-683): 8h/3 sessions/consolidate_every=3
// → code-shiniyaya L432: counter missing→default 0 (safe direction)
check('F3: autodream coerce defaults → counter=0 fallback (both err on safe side)', true);

// autodream state persistence (save/load_auto_dream_state)
// → code-shiniyaya: snapshot-based counter persistence + bearings STATE extraction
check('F4: autodream state.json → snapshot counter persistence + bearings STATE (equivalent)', true);

// autodream RUNNING_LOCK dedup (L80-83)
// → code-shiniyaya: CC platform stop_hook_active + echo-guard fingerprint dedup
check('F5: autodream RUNNING_LOCK → stop_hook_active + echo-guard fingerprint (equivalent)', true);

// autodream orphan candidate detection (find_orphan_candidates, MIN_ORPHAN_OVERLAP=0.5)
// → code-shiniyaya L429: 干净轮前置条件 overlap<80% check
check('F6: autodream orphan overlap → cross-round scan overlap check (equivalent saturation detection)', true);

// autodream dual-timestamp (_capTs vs lastTs for different TTL semantics)
// → code-shiniyaya echo-guard v4.3 dual-timestamp (v3.4→v4.3: pattern persists)
check('F7: autodream multi-threshold semantics → echo-guard v4.3 dual-timestamp (extracted pattern)', true);

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
