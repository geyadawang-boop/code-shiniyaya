// audit-pre-launch.js — dedicated pre-launch gate tests for dimension 3 audit
const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOOK = 'C:/Users/shiniyaya/.claude/hooks/stop-guard.js';
let pass = 0, fail = 0;

function check(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

// Test 1: pre-launch claims "第N轮...→继" with NO agent → blocked
const t1 = path.join(os.tmpdir(), 'sg-audit-1-' + Date.now() + '.jsonl');
fs.writeFileSync(t1, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '第6轮[10A]: 干净轮0/2→继' }
  ]} })
].join('\n'), 'utf8');
const r1 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t1 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: 第N轮→继 no Agent → blocked', r1.stdout.includes('"block"') && r1.stdout.includes('预发射'));
try { fs.unlinkSync(t1); } catch(e) {}

// Test 2: saturation bypass: ⚡.../compact+→继 → exempt
const t2 = path.join(os.tmpdir(), 'sg-audit-2-' + Date.now() + '.jsonl');
fs.writeFileSync(t2, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '⚡ 86% saturated → /compact →继' }
  ]} })
].join('\n'), 'utf8');
const r2 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t2 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: saturation ⚡.../compact→继 → exempt (passthrough)', r2.stdout === '{}' || !r2.stdout.includes('"block"'));

// Test 3: pre-launch with Agent call → exempt
const t3 = path.join(os.tmpdir(), 'sg-audit-3-' + Date.now() + '.jsonl');
fs.writeFileSync(t3, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'tool_use', name: 'Workflow', input: {} },
    { type: 'text', text: '第5轮[8A]: 干净轮1/2→继' }
  ]} })
].join('\n'), 'utf8');
const r3 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t3 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: →继 with Workflow call → exempt (passthrough)', r3.stdout === '{}' || !r3.stdout.includes('"block"'));
try { fs.unlinkSync(t3); } catch(e) {}

// Test 4: pre-launch + userStop → exempt
const t4 = path.join(os.tmpdir(), 'sg-audit-4-' + Date.now() + '.jsonl');
fs.writeFileSync(t4, [
  JSON.stringify({ type: 'user', message: { content: '停' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '第4轮[6A]: 干净轮0/2→继' }
  ]} })
].join('\n'), 'utf8');
const r4 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t4 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: →继 + userStop(停) → exempt (passthrough)', r4.stdout === '{}' || !r4.stdout.includes('"block"'));
try { fs.unlinkSync(t4); } catch(e) {}

// Test 5: pre-launch gate ordering — when both stall and pre-launch match,
// pre-launch fires first (preLaunchClaim test is before stall test in code at lines 73-78 vs 84-87)
const t5 = path.join(os.tmpdir(), 'sg-audit-5-' + Date.now() + '.jsonl');
fs.writeFileSync(t5, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '第4轮[6A]: 干净轮0/2→继' }
  ]} })
].join('\n'), 'utf8');
const r5 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t5 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch vs stall: 干净轮0/2→继 no Agent → pre-launch wins (fires first)',
  r5.stdout.includes('预发射') && !r5.stdout.includes('干净轮<2'));
try { fs.unlinkSync(t5); } catch(e) {}

// Test 6: bare "→继" without 第N轮 prefix → no pre-launch
const t6 = path.join(os.tmpdir(), 'sg-audit-6-' + Date.now() + '.jsonl');
fs.writeFileSync(t6, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '继续扫描 →继.' }
  ]} })
].join('\n'), 'utf8');
const r6 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t6 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: bare →继 without 第N轮 → no match (passthrough)', r6.stdout === '{}' || !r6.stdout.includes('"block"'));
try { fs.unlinkSync(t6); } catch(e) {}

// Test 7: gate ordering — 干净轮2/2→继 no Agent no snapshot:
// pre-launch fires first (line 76-78), clean-exit second (line 95-97),
// but pre-launch out() exits the process so clean-exit never reaches
// WAIT: actually both match, but pre-launch fires `out()` first at line 77 which calls `process.exit(0)`.
// So clean-exit never runs. This is correct: pre-launch is the more specific gate.
// This was empirically verified in the earlier bash run: output was clean-exit because
// that test had 干净轮2/2→继 which matches both `converged` regex and `preLaunchClaim` regex.
// Let's confirm which gate actually fires.
const t7 = path.join(os.tmpdir(), 'sg-audit-7-' + Date.now() + '.jsonl');
fs.writeFileSync(t7, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '干净轮2/2→继' }
  ]} })
].join('\n'), 'utf8');
const r7 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t7 }),
  encoding: 'utf8', timeout: 5000
});
// Note: "干净轮2/2→继" matches preLaunchClaim (第\d+轮...→继) — but wait,
// "干净轮2/2→继" does NOT contain "第\d+轮" — it's missing the 第N轮 prefix!
// "干净轮2/2" not "第N轮干净轮2/2" — so preLaunchClaim won't match.
// But converged regex /干净轮\s*2\s*\/\s*2/ DOES match. So clean-exit should fire.
const hasPreLaunch = r7.stdout.includes('预发射');
const hasCleanExit = r7.stdout.includes('snapshot');
console.log('  (info) 干净轮2/2→继: pre-launch fires=' + hasPreLaunch + ', clean-exit fires=' + hasCleanExit);
check('gate ordering: 干净轮2/2→继 (no 第N轮 prefix) → clean-exit fires, not pre-launch',
  hasCleanExit && !hasPreLaunch);
try { fs.unlinkSync(t7); } catch(e) {}

// Test 8: "第\d+轮" prefix but no "→继" → pre-launch NO match
const t8 = path.join(os.tmpdir(), 'sg-audit-8-' + Date.now() + '.jsonl');
fs.writeFileSync(t8, [
  JSON.stringify({ type: 'user', message: { content: 'go' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '第4轮完成，干净轮1/2' }
  ]} })
].join('\n'), 'utf8');
const r8 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t8 }),
  encoding: 'utf8', timeout: 5000
});
check('pre-launch: 第N轮 without →继 → no pre-launch match', r8.stdout === '{}' || (!r8.stdout.includes('预发射') && !r8.stdout.includes('"block"')));
try { fs.unlinkSync(t8); } catch(e) {}

// Test 9: the notification boundary test from hooks.test.js line 189-195
// This is the existing test that exercises the pre-launch gate indirectly:
// transcript=第4轮[6A]: 干净轮0/2→继, user=notification → pre-launch fires
const t9 = path.join(os.tmpdir(), 'sg-audit-9-' + Date.now() + '.jsonl');
fs.writeFileSync(t9, [
  JSON.stringify({ type: 'user', message: { content: '[SYSTEM NOTIFICATION - NOT USER INPUT]\nA task-notification fires each time this agent stops with no live background children.' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第4轮[6A]: 干净轮0/2→继' }] } })
].join('\n'), 'utf8');
const r9 = spawnSync('node', [HOOK], {
  input: JSON.stringify({ transcript_path: t9 }),
  encoding: 'utf8', timeout: 5000
});
const isPreLaunch9 = r9.stdout.includes('预发射');
const isStall9 = r9.stdout.includes('干净轮<2');
console.log('  (info) notification test: pre-launch=' + isPreLaunch9 + ', stall=' + isStall9);
check('pre-launch gate: notification + 第N轮→继 no Agent → pre-launch fires', isPreLaunch9 && r9.stdout.includes('"block"'));
try { fs.unlinkSync(t9); } catch(e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
