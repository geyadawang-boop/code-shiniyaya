#!/usr/bin/env node
// Final adversarial hook verification — 2026-07-18
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

// === echo-guard v3.4 ===
// 1. echo blockade
let r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'echo done' } });
check('echo-guard: echo done blocked', r.out.includes('"block"'));

r = runHook('echo-guard.js', { session_id: sid + 'n', tool_input: { command: 'echo 42' } });
check('echo-guard: bare number echo blocked', r.out.includes('"block"'));

// 2. wc -l de-dupe
r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: first wc -l passes', r.code === 0 && !r.out.includes('"block"'));
r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: second wc -l blocked', r.out.includes('"block"'));

// 3. fingerprint escalation ladder
const cmd = { session_id: sid, tool_input: { command: 'python build.py --ladder' } };
r = runHook('echo-guard.js', cmd);
check('ladder 1st: pass', r.out === '{}');
r = runHook('echo-guard.js', cmd);
check('ladder 2nd: systemMessage', r.out.includes('systemMessage'));
r = runHook('echo-guard.js', cmd);
check('ladder 3rd: ask', r.out.includes('"ask"'));
r = runHook('echo-guard.js', cmd);
check('ladder 4th: deny', r.out.includes('"deny"'));

// 4. git status exempt from ladder
const sidG = sid + 'g';
for (let i = 0; i < 4; i++) r = runHook('echo-guard.js', { session_id: sidG, tool_input: { command: 'git status' } });
check('echo-guard: git status 4x exempt', r.out === '{}');

// 5. compound command bypass closed
const sidC = sid + 'c';
const compound = { session_id: sidC, tool_input: { command: 'git status; python danger.py' } };
let compoundEsc = false;
for (let i = 0; i < 4; i++) {
  r = runHook('echo-guard.js', compound);
  if (r.out.includes('"deny"') || r.out.includes('"ask"') || r.out.includes('systemMessage')) compoundEsc = true;
}
check('echo-guard: compound git status;X NOT exempt', compoundEsc);

// 6. 50 random commands always exit 0
let crashed = false;
for (let i = 0; i < 50; i++) {
  const junk = 'cmd_' + Math.random().toString(36).slice(2) + '_arg' + i;
  const rr = runHook('echo-guard.js', { session_id: sid + 'p' + i, tool_input: { command: junk } });
  if (rr.code !== 0) { crashed = true; break; }
}
check('echo-guard: 50 random exit 0', !crashed);

// 7. dirty state file normalization
const dirtySid = 'dirty' + Date.now();
fs.writeFileSync(path.join(os.tmpdir(), '.cc_echoguard_' + dirtySid + '.json'), '{"hist":5,"wcFiles":"x","count":"NaN"}', 'utf8');
r = runHook('echo-guard.js', { session_id: dirtySid, tool_input: { command: 'wc -l foo.md' } });
check('echo-guard: dirty state exit 0', r.code === 0);

// 8. READONLY grep exempt from ladder+cap
const roSid = 'ro' + Date.now();
let laddered = false;
for (let i = 0; i < 5; i++) {
  const rr = runHook('echo-guard.js', { session_id: roSid, tool_input: { command: 'grep -n TODO SKILL.md' } });
  if (rr.out.includes('deny') || rr.out.includes('ask') || rr.out.includes('block')) { laddered = true; break; }
}
check('echo-guard: READONLY grep exempt', !laddered);

// 9. destruct-vet: find -delete NOT exempt
const fdsid = 'fd' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name *.tmp -delete' } }); }
r = runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name *.tmp -delete' } });
check('echo-guard: find -delete NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// 10. destruct-vet: sort -o NOT exempt
const sosid = 'so' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } }); }
r = runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } });
check('echo-guard: sort -o NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// 11. read-only find IS exempt
const frsid = 'fr' + Date.now();
let frhit = false;
for (let i = 0; i < 6; i++) {
  const rr = runHook('echo-guard.js', { session_id: frsid, tool_input: { command: 'find . -name *.py' } });
  if (rr.out.includes('deny') || rr.out.includes('ask')) { frhit = true; }
}
check('echo-guard: read-only find exempt', !frhit);

// 12. dual-timestamp: READONLY does not freeze cap
const dtSid = 'dt' + Date.now();
for (let i = 0; i < 6; i++) { runHook('echo-guard.js', { session_id: dtSid, tool_input: { command: 'grep test .' } }); }
r = runHook('echo-guard.js', { session_id: dtSid, tool_input: { command: 'python test.py' } });
check('echo-guard: dual-timestamp RO not freeze cap', r.out === '{}');

// 13. escalate → allowed blocked calls still exit 0
for (let i = 0; i < 4; i++) { runHook('echo-guard.js', { session_id: sid + 'es', tool_input: { command: 'echo confirmed' } }); }
r = runHook('echo-guard.js', { session_id: sid + 'es', tool_input: { command: 'echo confirmed' } });
check('echo-guard: always exit 0 on block', r.code === 0);

// === stop-guard v3.3 ===
// 14. stop_hook_active passthrough
r = runHook('stop-guard.js', { stop_hook_active: true, transcript_path: 'nonexistent' });
check('stop-guard: stop_hook_active passthrough', r.out === '{}');

// 15. missing transcript silent pass
r = runHook('stop-guard.js', { transcript_path: 'Z:/nonexist.jsonl' });
check('stop-guard: missing transcript silent pass', r.out === '{}');

// 16. pure-confirmation blocked
const tmpT = path.join(os.tmpdir(), 'sg-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpT,
  JSON.stringify({ type: 'user', message: { content: 'do thing' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done. verified. all ok.' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpT });
check('stop-guard: pure-confirmation blocked', r.out.includes('"block"'));

// 17. substantive turn passes
fs.writeFileSync(tmpT,
  JSON.stringify({ type: 'user', message: { content: 'do thing' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: {} }] } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done.' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpT });
check('stop-guard: substantive turn passes', r.out === '{}');
try { fs.unlinkSync(tmpT); } catch (e) {}

// 18. v3 clean-exit: converged w/o snapshot blocked
const tmpC = path.join(os.tmpdir(), 'sg-cln-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpC,
  JSON.stringify({ type: 'user', message: { content: 'continue' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'Round 3: clean 2/2 reached, signoff below' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpC });
check('stop-guard: converged w/o snapshot blocked', r.out.includes('"block"') && r.out.includes('snapshot'));

// 19. converged with snapshot passes
fs.writeFileSync(tmpC,
  JSON.stringify({ type: 'user', message: { content: 'continue' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: { file_path: 'C:/x/memory/snapshot-9.md' } }, { type: 'text', text: 'clean rounds 2/2 signoff complete' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpC });
check('stop-guard: converged with snapshot passes', r.out === '{}');
try { fs.unlinkSync(tmpC); } catch (e) {}

// 20. v3.2 notification boundary
const tmpN = path.join(os.tmpdir(), 'sg-notif-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpN,
  JSON.stringify({ type: 'user', message: { content: '[SYSTEM NOTIFICATION - NOT USER INPUT]\nA task-notification fires.' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'Round 4[6A]: clean 0/2' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpN });
check('stop-guard: notification boundary works', r.out.includes('"block"'));
try { fs.unlinkSync(tmpN); } catch (e) {}

// 21. v3.3 pre-launch gate
const tmpP = path.join(os.tmpdir(), 'sg-pre-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpP,
  JSON.stringify({ type: 'user', message: { content: 'continue' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'Round 5: 2 fixes done' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpP });
check('stop-guard: pre-launch gate blocks 第N轮 without agent', r.out.includes('Workflow/Agent/Task'));

// 22. saturation flow exempt from pre-launch
fs.writeFileSync(tmpP,
  JSON.stringify({ type: 'user', message: { content: 'continue' } }) + '\n' +
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'lightning 55% /compact + continue' }] } })
, 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpP });
check('stop-guard: saturation exemption works', r.out === '{}');
try { fs.unlinkSync(tmpP); } catch (e) {}

// === bearings v3.0-r9 ===
// 23. silent outside repo
r = runHook('bearings.js', { cwd: os.tmpdir() });
check('bearings: silent outside repo', r.out === '');

// 24. emits in repo
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' });
check('bearings: emits in repo', (r.out.startsWith('NEXT ACTION:') || r.out.startsWith('[BEARINGS]')) && r.out.includes('[BEARINGS]'));

// 25. STATE json present
check('bearings: STATE json present', /STATE: {"version"/.test(r.out));

// 26. STATE has -rN suffix
check('bearings: STATE has -rN suffix', r.out.includes('"version":"v4.7.9-r'));

// 27. hookWarn on truncated settings.json
const fakeHome = path.join(os.tmpdir(), 'bh-' + Date.now());
fs.mkdirSync(path.join(fakeHome, '.claude'), { recursive: true });
fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"model":"opus"}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on truncated settings', r.out.startsWith('⚠ HOOK REGISTRATION LOST'));

// 28. hookWarn on invalid JSON
fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"hooks":{"a":["echo-guard.js","stop-guard.js"],}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on invalid JSON', r.out.startsWith('⚠ settings.json UNPARSEABLE'));

// 29. hookWarn on missing settings.json
fs.unlinkSync(path.join(fakeHome, '.claude', 'settings.json'));
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings: hookWarn on missing settings', r.out.startsWith('⚠ settings.json MISSING'));
try { fs.rmSync(fakeHome, { recursive: true, force: true }); } catch (e) {}

// 30. journal.jsonl path (v3.0-r8/r9 fixed)
check('bearings: journal line present or gracefully absent', r.out.includes('journal (') || r.out.includes('recovery: user sends'));

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
