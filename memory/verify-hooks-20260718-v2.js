#!/usr/bin/env node
// Final adversarial hook verification — 2026-07-18 (fixed references)
const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOOKS = 'C:/Users/shiniyaya/.claude/hooks';
let pass = 0, fail = 0;

function runHook(hook, payload, env) {
  const r = spawnSync('node', [path.join(HOOKS, hook)], {
    input: JSON.stringify(payload), encoding: 'utf8', timeout: 10000,
    env: env ? Object.assign({}, process.env, env) : process.env
  });
  return { out: (r.stdout || '').trim(), code: r.status === null ? 1 : r.status };
}

function check(name, cond) {
  if (cond) { pass++; } else { fail++; console.log('FAIL: ' + name); }
}

const sid = 'fx' + Date.now();

// === echo-guard v3.4 (12 checks) ===

// 1. echo blockade
let r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'echo done' } });
check('echo-guard: echo done blocked', r.out.includes('"block"'));

// 2. bare number echo blocked
r = runHook('echo-guard.js', { session_id: sid + 'n', tool_input: { command: 'echo 42' } });
check('echo-guard: bare number echo blocked', r.out.includes('"block"'));

// 3. wc -l de-dupe
r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: first wc -l passes', r.code === 0 && !r.out.includes('"block"'));
r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: second wc -l blocked', r.out.includes('"block"'));

// 4. fingerprint escalation ladder
const cmd = { session_id: sid, tool_input: { command: 'python build.py --ladder' } };
r = runHook('echo-guard.js', cmd);
check('echo-guard: ladder 1st pass', r.out === '{}');
r = runHook('echo-guard.js', cmd);
check('echo-guard: ladder 2nd systemMessage', r.out.includes('systemMessage'));
r = runHook('echo-guard.js', cmd);
check('echo-guard: ladder 3rd ask', r.out.includes('"ask"'));
r = runHook('echo-guard.js', cmd);
check('echo-guard: ladder 4th deny exit 0', r.code === 0 && r.out.includes('"deny"'));

// 5. git status exempt (idempotent)
const sidG = sid + 'g';
for (let i = 0; i < 4; i++) r = runHook('echo-guard.js', { session_id: sidG, tool_input: { command: 'git status' } });
check('echo-guard: git status 4x exempt', r.out === '{}');

// 6. compound command NOT exempt
const sidC = sid + 'c';
const compound = { session_id: sidC, tool_input: { command: 'git status; python danger.py' } };
let compoundEsc = false;
for (let i = 0; i < 4; i++) {
  r = runHook('echo-guard.js', compound);
  if (r.out.includes('"deny"') || r.out.includes('"ask"') || r.out.includes('systemMessage')) compoundEsc = true;
}
check('echo-guard: compound git status;X NOT exempt', compoundEsc);

// 7. 50 random commands never crash
let crashed = false;
for (let i = 0; i < 50; i++) {
  const junk = 'cmd_' + Math.random().toString(36).slice(2) + '_arg' + i;
  const rr = runHook('echo-guard.js', { session_id: sid + 'p' + i, tool_input: { command: junk } });
  if (rr.code !== 0) { crashed = true; break; }
}
check('echo-guard: 50 random exit 0', !crashed);

// 8. dirty state normalization
const dirtySid = 'dirty' + Date.now();
fs.writeFileSync(path.join(os.tmpdir(), '.cc_echoguard_' + dirtySid + '.json'), '{"hist":5,"wcFiles":"x","count":"NaN"}', 'utf8');
r = runHook('echo-guard.js', { session_id: dirtySid, tool_input: { command: 'wc -l foo.md' } });
check('echo-guard: dirty state exit 0', r.code === 0);

// 9. READONLY grep exempt from ladder+cap
const roSid = 'ro' + Date.now();
let laddered = false;
for (let i = 0; i < 5; i++) {
  const rr = runHook('echo-guard.js', { session_id: roSid, tool_input: { command: 'grep -n TODO SKILL.md' } });
  if (rr.out.includes('deny') || rr.out.includes('ask') || rr.out.includes('block')) { laddered = true; break; }
}
check('echo-guard: READONLY grep 5x exempt', !laddered);

// 10. destruct-vet: find -delete NOT exempt
const fdsid = 'fd' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name *.tmp -delete' } }); }
r = runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name *.tmp -delete' } });
check('echo-guard: find -delete NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// 11. destruct-vet: sort -o NOT exempt
const sosid = 'so' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } }); }
r = runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } });
check('echo-guard: sort -o NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// 12. read-only find IS exempt (no ladder)
const frsid = 'fr' + Date.now();
let frhit = false;
for (let i = 0; i < 6; i++) {
  const rr = runHook('echo-guard.js', { session_id: frsid, tool_input: { command: 'find . -name *.py' } });
  if (rr.out.includes('deny') || rr.out.includes('ask')) { frhit = true; }
}
check('echo-guard: read-only find exempt', !frhit);

// 13. dual-timestamp: READONLY does not freeze cap (v3.4 fix)
const dtSid = 'dt' + Date.now();
for (let i = 0; i < 6; i++) { runHook('echo-guard.js', { session_id: dtSid, tool_input: { command: 'grep test .' } }); }
r = runHook('echo-guard.js', { session_id: dtSid, tool_input: { command: 'python test.py' } });
check('echo-guard: dual-timestamp RO no freeze cap', r.out === '{}');

// 14. always exit 0 even on blocks (silent-fail contract)
for (let i = 0; i < 4; i++) { runHook('echo-guard.js', { session_id: sid + 'es', tool_input: { command: 'echo confirmed' } }); }
r = runHook('echo-guard.js', { session_id: sid + 'es', tool_input: { command: 'echo confirmed' } });
check('echo-guard: always exit 0 on block', r.code === 0);

// === stop-guard v3.3 (10 checks) ===

// 15. stop_hook_active passthrough
r = runHook('stop-guard.js', { stop_hook_active: true, transcript_path: 'nonexistent' });
check('stop-guard: stop_hook_active passthrough', r.out === '{}');

// 16. missing transcript silent pass
r = runHook('stop-guard.js', { transcript_path: 'Z:/nonexist.jsonl' });
check('stop-guard: missing transcript silent pass', r.out === '{}');

// 17. pure-confirmation blocked (no Write/Edit/Agent)
const t17 = path.join(os.tmpdir(), 'sg17-' + Date.now() + '.jsonl');
fs.writeFileSync(t17,
  JSON.stringify({ type: 'user', message: { content: 'do thing' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done. verified. all ok.' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t17 });
check('stop-guard: pure-confirmation blocked', r.out.includes('"block"'));
try { fs.unlinkSync(t17); } catch (e) {}

// 18. substantive turn passes (has Write)
const t18 = path.join(os.tmpdir(), 'sg18-' + Date.now() + '.jsonl');
fs.writeFileSync(t18,
  JSON.stringify({ type: 'user', message: { content: 'do thing' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: {} }] } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done.' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t18 });
check('stop-guard: substantive turn (Write) passes', r.out === '{}');
try { fs.unlinkSync(t18); } catch (e) {}

// 19. v3 clean-exit: converged without snapshot -> blocked
const t19 = path.join(os.tmpdir(), 'sg19-' + Date.now() + '.jsonl');
fs.writeFileSync(t19,
  JSON.stringify({ type: 'user', message: { content: '继续' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第3轮: 干净轮2/2 达成, 签收单如下' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t19 });
check('stop-guard: converged w/o snapshot blocked', r.out.includes('"block"') && r.out.includes('snapshot'));
try { fs.unlinkSync(t19); } catch (e) {}

// 20. converged with snapshot Write -> passes
const t20 = path.join(os.tmpdir(), 'sg20-' + Date.now() + '.jsonl');
fs.writeFileSync(t20,
  JSON.stringify({ type: 'user', message: { content: '继续' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: { file_path: 'C:/x/memory/snapshot-9.md' } }, { type: 'text', text: '干净轮2/2 签收单完成' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t20 });
check('stop-guard: converged with snapshot passes', r.out === '{}');
try { fs.unlinkSync(t20); } catch (e) {}

// 21. v3.2 notification boundary: task-notification must not disarm stall gate
const t21 = path.join(os.tmpdir(), 'sg21-' + Date.now() + '.jsonl');
fs.writeFileSync(t21,
  JSON.stringify({ type: 'user', message: { content: '[SYSTEM NOTIFICATION - NOT USER INPUT]\nA task-notification fires each time this agent stops.' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第4轮[6A]: 干净轮0/2→继' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t21 });
check('stop-guard: notification boundary disarm stall', r.out.includes('"block"'));
try { fs.unlinkSync(t21); } catch (e) {}

// 22. v3.3 pre-launch gate: 第N轮→继 without Workflow/Agent/Task call
const t22 = path.join(os.tmpdir(), 'sg22-' + Date.now() + '.jsonl');
fs.writeFileSync(t22,
  JSON.stringify({ type: 'user', message: { content: '继续' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第5轮: 2→2→继' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t22 });
check('stop-guard: pre-launch gate blocks 第N轮→继 without agent', r.out.includes('Workflow/Agent/Task'));
try { fs.unlinkSync(t22); } catch (e) {}

// 23. v3.3 saturation exemption: ⚡/compact→继 bypasses pre-launch
const t23 = path.join(os.tmpdir(), 'sg23-' + Date.now() + '.jsonl');
fs.writeFileSync(t23,
  JSON.stringify({ type: 'user', message: { content: '继续' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '⚡ 55% — /compact + 继' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: t23 });
check('stop-guard: saturation flow exempt from pre-launch', r.out === '{}');
try { fs.unlinkSync(t23); } catch (e) {}

// 24. stop-guard exit code always 0 (silent-fail contract on garbage input)
r = runHook('stop-guard.js', { stop_hook_active: false });
check('stop-guard: garbage input silent exit 0', r.code === 0);

// === bearings v3.0-r9 (6 checks) ===

// 25. silent outside code-shiniyaya repo
r = runHook('bearings.js', { cwd: os.tmpdir() });
check('bearings: silent outside repo', r.out === '');

// 26. emits BEARINGS in repo
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' });
const bearOut = r;
check('bearings: emits in repo', (r.out.startsWith('NEXT ACTION:') || r.out.startsWith('[BEARINGS]') || r.out.startsWith('⚠')) && r.out.includes('[BEARINGS]'));

// 27. STATE json present (machine-readable snapshot digest)
check('bearings: STATE json present', /STATE: {"version"/.test(r.out));

// 28. hookWarn on truncated settings.json (missing hook registrations)
const fakeHome = path.join(os.tmpdir(), 'bh-' + Date.now());
fs.mkdirSync(path.join(fakeHome, '.claude'), { recursive: true });
fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"model":"opus"}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on truncated settings', r.out.startsWith('⚠ HOOK REGISTRATION LOST'));

// 29. hookWarn on invalid JSON settings.json
fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"hooks":{"a":["echo-guard.js","stop-guard.js"],}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on invalid JSON', r.out.startsWith('⚠ settings.json UNPARSEABLE'));

// 30. hookWarn on missing settings.json
fs.unlinkSync(path.join(fakeHome, '.claude', 'settings.json'));
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on missing settings', r.out.startsWith('⚠ settings.json MISSING'));
try { fs.rmSync(fakeHome, { recursive: true, force: true }); } catch (e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
