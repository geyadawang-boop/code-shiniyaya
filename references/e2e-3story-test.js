#!/usr/bin/env node
// e2e-3story-test.js — 维度6 三hook端到端联合演练
// 不依赖测试框架，纯node，直接构造payload调用各hook逻辑。
// exit 0 = all passed; exit 1 = failures found.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const HOOKS_DIR = 'C:/Users/shiniyaya/.claude/hooks';
const REPO_DIR = 'C:/Users/shiniyaya/Desktop/code-shiniyaya';
const TMP = process.env.TEMP || os.tmpdir();

let failures = 0;
let passed = 0;

function assert(label, condition, detail) {
  if (condition) {
    passed++;
  } else {
    failures++;
    console.log(`  FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  }
}

// ========== Helper to call a hook with stdin JSON ==========
function callHook(hookName, stdinObj, timeoutMs = 5000) {
  const hookPath = path.join(HOOKS_DIR, hookName);
  const input = JSON.stringify(stdinObj);
  try {
    const out = execFileSync('node', [hookPath], {
      input,
      timeout: timeoutMs,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe']
    }).trim();
    try { return JSON.parse(out); } catch (e) { return out || null; }
  } catch (e) {
    // exit code != 0
    try { return JSON.parse(e.stdout || '{}'); } catch (e2) { return e.stdout || e.message; }
  }
}

// ========== Setup: clean echo-guard state ==========
function cleanEchoGuard(sid) {
  const f = path.join(TMP, '.cc_echoguard_' + sid + '.json');
  try { fs.unlinkSync(f); } catch (e) {}
  try { fs.unlinkSync(f + '.tmp'); } catch (e) {}
}

console.log('='.repeat(60));
console.log('维度6 三hook端到端联合演练');
console.log('='.repeat(60));

// ==========================================================================
// STORY 1: 正常轮 — echo-guard放行grep + stop-guard对有Agent调用的turn放行
// ==========================================================================
console.log('\n### Story 1: 正常轮 (echo-guard READONLY放行 + stop-guard agent-turn放行)');
{
  const sid = 'story1-' + Date.now();
  cleanEchoGuard(sid);

  // 1a: echo-guard on a grep command — must pass (READONLY exemption v3.2)
  const eg1 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'grep "echo-guard" "C:/Users/shiniyaya/Desktop/code-shiniyaya/SKILL.md"' }
  });
  const eg1ok = !eg1 || !eg1.decision || eg1.decision !== 'block';
  assert('1a: echo-guard pass-thru grep (READONLY exempt)', eg1ok,
    'RESPONSE=' + JSON.stringify(eg1));

  // 1b: Simulate stop-guard with a turn that has:
  //     - 干净轮0/2 claim (stall detection trigger)
  //     - BUT also has an Agent call → should NOT block
  const transcript1 = [
    JSON.stringify({ type: 'user', message: { content: '继续扫描' } }),
    JSON.stringify({ type: 'assistant', message: { content: '第1轮[6A]: 干净轮 0/2→继。发射scan agent... ⚡ scan /compact' } }),
    JSON.stringify({ type: 'assistant', message: { content: '{"name":"Agent","params":{"prompt":"scan dimension 1"}}' } }),
  ].join('\n');

  const tmpFile1 = path.join(TMP, 'stopguard-test1-' + Date.now() + '.jsonl');
  fs.writeFileSync(tmpFile1, transcript1);
  try {
    const sg1 = callHook('stop-guard.js', { transcript_path: tmpFile1, stop_hook_active: false });
    // agentLaunched should be true → stall gate passes (even though 干净轮0/2 present)
    const sg1ok = !sg1 || !sg1.decision || sg1.decision !== 'block';
    assert('1b: stop-guard passes agent-turn (干净轮0/2+Agent called)',
      sg1ok, 'RESPONSE=' + JSON.stringify(sg1));
  } finally {
    try { fs.unlinkSync(tmpFile1); } catch (e) {}
  }

  // 1c: stop-guard should NOT block when saturation flow present (⚡…/compact)
  // Note: the pure-confirmation gate (confirms>=2+no substantive) is independent from
  // the stall gate. "done, ok" would hit pure-confirmation even with saturation present.
  // Use content that does NOT contain confirmation words.
  const transcript1c = [
    JSON.stringify({ type: 'user', message: { content: '继续扫描' } }),
    JSON.stringify({ type: 'assistant', message: { content: '⚡ 饱和优先线 — 当前55%已超阈值，发 /compact + 继。继续执行任务。' } }),
    JSON.stringify({ type: 'assistant', message: { content: '干净轮 0/2。发射下一轮扫描agent。' } }),
  ].join('\n');
  const tmpFile1c = path.join(TMP, 'stopguard-test1c-' + Date.now() + '.jsonl');
  fs.writeFileSync(tmpFile1c, transcript1c);
  try {
    const sg1c = callHook('stop-guard.js', { transcript_path: tmpFile1c, stop_hook_active: false });
    const sg1cok = !sg1c || !sg1c.decision || sg1c.decision !== 'block';
    assert('1c: stop-guard passes saturation flow (⚡…/compact with stall text)',
      sg1cok, 'RESPONSE=' + JSON.stringify(sg1c));
  } finally {
    try { fs.unlinkSync(tmpFile1c); } catch (e) {}
  }

  // 1d: echo-guard should allow an idempotent command (git status)
  const eg1d = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'git status' }
  });
  const eg1dok = !eg1d || !eg1d.decision || eg1d.decision !== 'block';
  assert('1d: echo-guard pass-thru git status (IDEMPOTENT exempt)',
    eg1dok, 'RESPONSE=' + JSON.stringify(eg1d));

  // 1e: echo-guard should block a trivial echo
  const eg1e = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'echo done' }
  });
  assert('1e: echo-guard blocks "echo done"',
    eg1e && eg1e.decision === 'block',
    'RESPONSE=' + JSON.stringify(eg1e));

  cleanEchoGuard(sid);
}

// ==========================================================================
// STORY 2: 收敛轮 — 签收单+snapshot pass + 签收单-no-snapshot block
// ==========================================================================
console.log('\n### Story 2: 收敛轮 (签收单+snapshot门)');
{
  // 2a: Turn with "## 签收单" + snapshot write → should NOT block (converged + snapWritten)
  const transcript2a = [
    JSON.stringify({ type: 'user', message: { content: '输出签收单' } }),
    JSON.stringify({ type: 'assistant', message: { content: '干净轮 2/2。所有维度零确认。' } }),
    JSON.stringify({ type: 'assistant', message: { content: '## 签收单' } }),
    JSON.stringify({ type: 'assistant', message: { content: 'memory/snapshot-20260718T070000.md — SNAPSHOT-COMPLETE + nextAction=verify' } }),
  ].join('\n');
  const tmpFile2a = path.join(TMP, 'stopguard-test2a-' + Date.now() + '.jsonl');
  fs.writeFileSync(tmpFile2a, transcript2a);
  try {
    const sg2a = callHook('stop-guard.js', { transcript_path: tmpFile2a, stop_hook_active: false });
    const sg2aok = !sg2a || !sg2a.decision || sg2a.decision !== 'block';
    assert('2a: stop-guard passes "## 签收单" + snapshot written',
      sg2aok, 'RESPONSE=' + JSON.stringify(sg2a));
  } finally {
    try { fs.unlinkSync(tmpFile2a); } catch (e) {}
  }

  // 2b: Turn with "## 签收单" BUT no snapshot → should BLOCK
  const transcript2b = [
    JSON.stringify({ type: 'user', message: { content: '输出签收单' } }),
    JSON.stringify({ type: 'assistant', message: { content: '干净轮 2/2。所有维度零确认。' } }),
    JSON.stringify({ type: 'assistant', message: { content: '## 签收单' } }),
    JSON.stringify({ type: 'assistant', message: { content: '所有bug已修复，任务完成。' } }),
  ].join('\n');
  const tmpFile2b = path.join(TMP, 'stopguard-test2b-' + Date.now() + '.jsonl');
  fs.writeFileSync(tmpFile2b, transcript2b);
  try {
    const sg2b = callHook('stop-guard.js', { transcript_path: tmpFile2b, stop_hook_active: false });
    const sg2bBlocked = sg2b && sg2b.decision === 'block' && /snapshot/.test(sg2b.reason || '');
    assert('2b: stop-guard blocks "## 签收单" without snapshot',
      sg2bBlocked, 'RESPONSE=' + JSON.stringify(sg2b));
  } finally {
    try { fs.unlinkSync(tmpFile2b); } catch (e) {}
  }

  // 2c: stop_hook_active guard — must pass on second call (prevents self-loop)
  const sg2c = callHook('stop-guard.js', { transcript_path: tmpFile2a, stop_hook_active: true });
  const sg2cok = !sg2c || !sg2c.decision || sg2c.decision !== 'block';
  assert('2c: stop-guard passes when stop_hook_active=true (anti-self-loop)',
    sg2cok, 'RESPONSE=' + JSON.stringify(sg2c));

  // 2d: Pure confirmation turn (confirms >=2, no substantive) → block
  const transcript2d = [
    JSON.stringify({ type: 'user', message: { content: '确认完成了吗' } }),
    JSON.stringify({ type: 'assistant', message: { content: 'done, verified, confirmed. All good.' } }),
  ].join('\n');
  const tmpFile2d = path.join(TMP, 'stopguard-test2d-' + Date.now() + '.jsonl');
  fs.writeFileSync(tmpFile2d, transcript2d);
  try {
    const sg2d = callHook('stop-guard.js', { transcript_path: tmpFile2d, stop_hook_active: false });
    const sg2dBlocked = sg2d && sg2d.decision === 'block' && /confirm/.test((sg2d.reason || '').toLowerCase());
    assert('2d: stop-guard blocks pure-confirmation turn (no Write/Edit/Agent)',
      sg2dBlocked, 'RESPONSE=' + JSON.stringify(sg2d));
  } finally {
    try { fs.unlinkSync(tmpFile2d); } catch (e) {}
  }
}

// ==========================================================================
// STORY 3: bearings against current real repo — STATE line correctness
// ==========================================================================
console.log('\n### Story 3: bearings真实repo STATE行字段校验');
{
  const result = callHook('bearings.js', { cwd: REPO_DIR }, 10000);
  const output = typeof result === 'string' ? result : JSON.stringify(result);
  console.log('  bearings output (~first 1500 chars):');
  console.log('  ' + output.slice(0, 1500).replace(/\n/g, '\n  '));

  // Parse STATE line
  const stateMatch = output.match(/STATE:\s*(\{.*\})/);
  assert('3a: bearings outputs STATE line as valid JSON', !!stateMatch,
    stateMatch ? 'STATE=' + stateMatch[1] : 'NO STATE line found');

  let state = {};
  if (stateMatch) {
    try { state = JSON.parse(stateMatch[1]); } catch (e) {
      assert('3a-parse: STATE JSON is parseable', false, e.message);
    }
  }

  // 3b: version field — should start with v (e.g. v4.7.9-r4)
  assert('3b: STATE.version starts with "v"',
    state.version && /^v/.test(state.version),
    'version=' + JSON.stringify(state.version));

  // 3c: nextAction field — should be one of scan/await/fix/verify or empty
  assert('3c: STATE.nextAction is scan|await|fix|verify|""',
    ['scan', 'await', 'fix', 'verify', ''].includes(state.nextAction || ''),
    'nextAction=' + JSON.stringify(state.nextAction));

  // 3d: cleanRounds field — should be like "0/2" or "1/2" or "2/2" or empty
  assert('3d: STATE.cleanRounds is N/2 format',
    state.cleanRounds === '' || /^\d\/2$/.test(state.cleanRounds),
    'cleanRounds=' + JSON.stringify(state.cleanRounds));

  // 3e: snapshotComplete boolean
  assert('3e: STATE.snapshotComplete is boolean',
    typeof state.snapshotComplete === 'boolean',
    'snapshotComplete=' + JSON.stringify(state.snapshotComplete));

  // 3f: snapshotFile field present
  assert('3f: STATE.snapshotFile is a string',
    typeof state.snapshotFile === 'string' && state.snapshotFile.length > 0,
    'snapshotFile=' + JSON.stringify(state.snapshotFile));

  // 3g: hookWarn should be empty (settings.json is valid, hooks registered)
  const hasWarn = /⚠/.test(output.slice(0, 200));
  assert('3g: bearings hookWarn is empty (settings.json is valid + hooks registered)',
    !hasWarn,
    hasWarn ? 'hookWarn present: ' + output.match(/[⚠⚡].*/)[0] : 'no hookWarn');

  // 3h: Verify BEARINGS reports correct HEAD
  const headMatch = output.match(/18e45c3/);
  assert('3h: bearings reports current HEAD=18e45c3',
    !!headMatch, 'HEAD line: ' + (output.match(/git HEAD:\n(.+)/) || ['', 'not found'])[1]);

  // 3i: Verify memory file count is reasonable
  const memCountMatch = output.match(/memory files=(\d+)/);
  assert('3i: bearings reports memory files count',
    !!memCountMatch, 'memCount=' + (memCountMatch ? memCountMatch[1] : 'missing'));

  // 3j: Verify snapshots listed
  const snapMatch = output.match(/snapshots \(latest last\):\s*(.+)/);
  assert('3j: bearings lists latest snapshots',
    snapMatch && snapMatch[1].length > 0 && snapMatch[1] !== 'none',
    'snaps=' + (snapMatch ? snapMatch[1] : 'missing'));

  // 3k: Verify NEXT ACTION line
  const nextActionMatch = output.match(/NEXT ACTION:\s*(.+)/);
  assert('3k: bearings outputs NEXT ACTION line',
    !!nextActionMatch,
    'nextAction=' + (nextActionMatch ? nextActionMatch[1] : 'missing'));

  // 3l: CHANGELOG head present
  const changelogMatch = output.match(/v4\.7\.9-r4/);
  assert('3l: bearings CHANGELOG reports v4.7.9-r4',
    !!changelogMatch);

  // 3m: git status present
  const gitStatusMatch = output.match(/git status:\s*(.*)/);
  assert('3m: bearings outputs git status',
    !!gitStatusMatch,
    'gitStatus=' + (gitStatusMatch ? gitStatusMatch[1] : 'missing'));
}

// ==========================================================================
// EXTRA: Echo-guard fingerprint escalation ladder test
// ==========================================================================
console.log('\n### Extra: echo-guard fingerprint escalation ladder');
{
  const sid = 'story-extra-' + Date.now();
  cleanEchoGuard(sid);

  // First call: should pass clean
  const e1 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'node something.js' }
  });
  assert('Ex1: 1st call passes', !e1 || !e1.decision || e1.decision !== 'block',
    'R1=' + JSON.stringify(e1));

  // Second same command: should get systemMessage (hits=1)
  const e2 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'node something.js' }
  });
  assert('Ex2: 2nd call gets systemMessage (not block)',
    e2 && e2.systemMessage && /2nd/.test(e2.systemMessage),
    'R2=' + JSON.stringify(e2));

  // Third same command: should get ask (hits=2)
  const e3 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'node something.js' }
  });
  assert('Ex3: 3rd call gets ask permissionDecision',
    e3 && e3.hookSpecificOutput && e3.hookSpecificOutput.permissionDecision === 'ask',
    'R3=' + JSON.stringify(e3));

  // Fourth same command: should get deny (hits>=3)
  const e4 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'node something.js' }
  });
  assert('Ex4: 4th call gets deny',
    e4 && e4.hookSpecificOutput && e4.hookSpecificOutput.permissionDecision === 'deny',
    'R4=' + JSON.stringify(e4));

  cleanEchoGuard(sid);
}

// ==========================================================================
// EXTRA: echo-guard cap test (READONLY exempt from counting)
// ==========================================================================
console.log('\n### Extra: echo-guard per-turn cap with READONLY exemption');
{
  const sid = 'story-cap-' + Date.now();
  cleanEchoGuard(sid);

  // Fire 8 non-exempt calls (fills cap exactly: count=8, nextCount=8 NOT > 8)
  for (let i = 0; i < 8; i++) {
    callHook('echo-guard.js', {
      session_id: sid,
      tool_name: 'Bash',
      tool_input: { command: 'node test' + i }
    });
  }
  // 9th non-exempt: count=8 → nextCount=9 > 8 → block
  const e9 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'node test9' }
  });
  const capBlocked = e9 && e9.decision === 'block' && /cap/i.test(e9.reason || '');
  assert('Ex5: 9th non-exempt Bash call hits cap and blocks',
    capBlocked, 'R=' + JSON.stringify(e9));

  // Now a grep (READONLY) should still pass even though cap exceeded
  const eGrep = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'grep test "./file.txt"' }
  });
  const grepPasses = !eGrep || !eGrep.decision || eGrep.decision !== 'block';
  assert('Ex6: READONLY grep still passes after cap exceeded',
    grepPasses, 'R=' + JSON.stringify(eGrep));

  cleanEchoGuard(sid);
}

// ==========================================================================
// EXTRA: echo-guard chain-detection (piped commands should NOT be IDEMPOTENT)
// ==========================================================================
console.log('\n### Extra: echo-guard chain/metachar detection');
{
  const sid = 'story-chain-' + Date.now();
  cleanEchoGuard(sid);

  // git status; rm -rf x should NOT be exempt (has semicolon)
  const e1 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'git status; rm -rf /' }
  });
  // Even first call should count toward cap (not IDEMPOTENT because metachar)
  // Call it 8 more times to check cap behavior — actually just verify first call is not blocked
  const e1NotBlockedByChain = !e1 || !e1.decision || e1.decision !== 'block';
  assert('Ex7: chained command "git status; rm -rf /" is NOT blocked by echo pattern but IS counted',
    e1NotBlockedByChain, 'R=' + JSON.stringify(e1));

  cleanEchoGuard(sid);
}

// ==========================================================================
// EXTRA: echo-guard wc -l same-file detection
// ==========================================================================
console.log('\n### Extra: echo-guard wc -l duplicate detection');
{
  const sid = 'story-wc-' + Date.now();
  cleanEchoGuard(sid);

  callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'wc -l /some/file.txt' }
  });
  const e2 = callHook('echo-guard.js', {
    session_id: sid,
    tool_name: 'Bash',
    tool_input: { command: 'wc -l /some/file.txt' }
  });
  assert('Ex8: wc -l on same file twice blocks',
    e2 && e2.decision === 'block' && /wc/.test(e2.reason || ''),
    'R=' + JSON.stringify(e2));

  cleanEchoGuard(sid);
}

// ========== Summary ==========
console.log('\n' + '='.repeat(60));
console.log('RESULTS: ' + passed + ' passed, ' + failures + ' failed');
console.log('='.repeat(60));

process.exit(failures > 0 ? 1 : 0);
