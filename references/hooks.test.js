#!/usr/bin/env node
// hooks.test.js — zero-dep runnable check for the 4 defense hooks (ponytail "one runnable check" rule)
// Run: node references/hooks.test.js
// History: v1.0 shipped argv-vs-stdin bug (all regexes dead), v3.0 shipped ReferenceError in deny
// tier (fail-open). Both broke in paths manual testing skipped. This file closes that class.
// v1.1: spawnSync with input option — no shell, no quoting hazards.
// v3.2: echo-guard dirty-state/destruct-vet/lastTs-freeze; stop-guard notification-boundary tests added.
// v3.3: echo-guard READONLY bypass checks (find -delete/sort -o blocked + grep exempt).

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
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

const sid = 'test' + Date.now();

// --- echo-guard ---
let r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'echo done' } });
check('echo-guard: echo done blocked, exit 0', r.code === 0 && r.out.includes('"block"'));

r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'echo 42' } });
check('echo-guard: bare number echo blocked', r.out.includes('"block"'));

r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: first wc -l passes', r.code === 0 && !r.out.includes('"block"'));
r = runHook('echo-guard.js', { session_id: sid + 'wc', tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: second wc -l same file blocked', r.out.includes('"block"'));

// escalation ladder on a non-idempotent command (4 runs: pass, warn, ask, deny — all exit 0)
const cmd = { session_id: sid, tool_input: { command: 'python build.py --ladder-test' } };
r = runHook('echo-guard.js', cmd);
check('ladder 1st: pass', r.code === 0 && r.out === '{}');
r = runHook('echo-guard.js', cmd);
check('ladder 2nd: systemMessage warn', r.code === 0 && r.out.includes('systemMessage'));
r = runHook('echo-guard.js', cmd);
check('ladder 3rd: ask', r.code === 0 && r.out.includes('"ask"'));
r = runHook('echo-guard.js', cmd);
check('ladder 4th: deny, exit 0 (the v3.0 ReferenceError regression)', r.code === 0 && r.out.includes('"deny"'));

// idempotent exemption — fresh sid (per-turn cap would otherwise interfere at 9th call)
const sidG = sid + 'g';
for (let i = 0; i < 4; i++) r = runHook('echo-guard.js', { session_id: sidG, tool_input: { command: 'git status' } });
check('echo-guard: git status 4x exempt from ladder', r.code === 0 && r.out === '{}');

// compound-command bypass (adversarial audit A3): "git status; X" must NOT be exempt — fresh sid
const sidC = sid + 'c';
const compound = { session_id: sidC, tool_input: { command: 'git status; python danger.py' } };
let compoundEscalated = false;
for (let i = 0; i < 4; i++) {
  r = runHook('echo-guard.js', compound);
  if (r.out.includes('"deny"') || r.out.includes('"ask"') || r.out.includes('systemMessage')) compoundEscalated = true;
}
check('echo-guard: compound "git status; X" NOT exempt (A3 bypass closed)', compoundEscalated);

// random commands never crash
let crashed = false;
for (let i = 0; i < 50; i++) {
  const junk = 'cmd' + Math.random().toString(36).slice(2) + ' "arg ' + i + '" --x';
  const rr = runHook('echo-guard.js', { session_id: sid + 'p' + i, tool_input: { command: junk } });
  if (rr.code !== 0) { crashed = true; break; }
}
check('echo-guard: 50 random commands, always exit 0', !crashed);

// --- stop-guard ---
r = runHook('stop-guard.js', { stop_hook_active: true, transcript_path: 'nonexistent' });
check('stop-guard: stop_hook_active passthrough', r.code === 0 && r.out === '{}');

r = runHook('stop-guard.js', { transcript_path: 'Z:/does/not/exist.jsonl' });
check('stop-guard: missing transcript silent pass', r.code === 0 && r.out === '{}');

const tmpT = path.join(os.tmpdir(), 'sg-test-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpT, [
  JSON.stringify({ type: 'user', message: { content: 'do the thing' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done. verified. all ok.' }] } })
].join('\n'), 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpT });
check('stop-guard: pure-confirmation turn blocked', r.out.includes('"block"'));

fs.writeFileSync(tmpT, [
  JSON.stringify({ type: 'user', message: { content: 'do the thing' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: {} }] } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'done. verified.' }] } })
].join('\n'), 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpT });
check('stop-guard: substantive turn (Write) passes', r.code === 0 && r.out === '{}');
try { fs.unlinkSync(tmpT); } catch (e) {}

// --- bearings ---
r = runHook('bearings.js', { cwd: os.tmpdir() });
check('bearings: silent outside code-shiniyaya repo', r.code === 0 && r.out === '');

r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' });
check('bearings: emits BEARINGS (or NEXT ACTION first line) in repo', r.code === 0 && (r.out.startsWith('[BEARINGS]') || (r.out.startsWith('NEXT ACTION:') && r.out.includes('[BEARINGS]'))));

// --- v3 (Scan 4 carry-forward) ---
const tmpC = path.join(os.tmpdir(), 'sg-clean-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpC, [
  JSON.stringify({ type: 'user', message: { content: '继续' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第3轮: 干净轮2/2 达成, 签收单如下' }] } })
].join('\n'), 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpC });
check('stop-guard v3: converged w/o snapshot blocked', r.out.includes('"block"') && r.out.includes('snapshot'));

fs.writeFileSync(tmpC, [
  JSON.stringify({ type: 'user', message: { content: '继续' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: { file_path: 'C:/x/memory/snapshot-9.md' } }, { type: 'text', text: '干净轮2/2 签收单完成' }] } })
].join('\n'), 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpC });
check('stop-guard v3: converged with snapshot Write passes', r.code === 0 && r.out === '{}');
try { fs.unlinkSync(tmpC); } catch (e) {}

r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' });
check('bearings v3: STATE json line present', /STATE: \{"version"/.test(r.out));

const fakeHome = path.join(os.tmpdir(), 'bear-fakehome-' + Date.now());
fs.mkdirSync(path.join(fakeHome, '.claude'), { recursive: true });
fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"model":"opus"}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings v3: hookWarn on truncated settings.json', r.out.startsWith('⚠ HOOK REGISTRATION LOST'));

fs.writeFileSync(path.join(fakeHome, '.claude', 'settings.json'), '{"hooks":{"a":["echo-guard.js","stop-guard.js"],]}', 'utf8');
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings v3: hookWarn on invalid-JSON settings (2026-07-18 trailing-comma class)', r.out.startsWith('⚠ settings.json UNPARSEABLE'));

fs.unlinkSync(path.join(fakeHome, '.claude', 'settings.json'));
r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' }, { USERPROFILE: fakeHome });
check('bearings v3: hookWarn on missing settings.json (ENOENT no longer silent)', r.out.startsWith('⚠ settings.json MISSING'));
try { fs.rmSync(fakeHome, { recursive: true, force: true }); } catch (e) {}

r = runHook('bearings.js', { cwd: 'C:/Users/shiniyaya/Desktop/code-shiniyaya' });
check('bearings v3: STATE version keeps -rN suffix (live snapshot says v4.7.9-r2)', r.out.includes('"version":"v4.7.9-r'));

// --- v3.2 (Scan 7) ---
// echo-guard: corrupted state file must not break the exit-0 contract
const dirtySid = 'dirty' + Date.now();
fs.writeFileSync(path.join(os.tmpdir(), '.cc_echoguard_' + dirtySid + '.json'), '{"hist":5,"wcFiles":"x","count":"NaN"}', 'utf8');
r = runHook('echo-guard.js', { session_id: dirtySid, tool_input: { command: 'wc -l foo.md' } });
check('echo-guard v3.2: dirty state file still exit 0', r.code === 0);

// echo-guard: READONLY repetition (mandated test reruns / audit greps) never climbs the ladder
const roSid = 'ro' + Date.now();
let laddered = false;
for (let i = 0; i < 5; i++) {
  const rr = runHook('echo-guard.js', { session_id: roSid, tool_input: { command: 'grep -n TODO SKILL.md' } });
  if (rr.out.includes('deny') || rr.out.includes('ask') || rr.out.includes('block')) { laddered = true; break; }
}
check('echo-guard v3.2: READONLY grep 5x exempt from ladder+cap', !laddered);

// --- v3.3 (Scan 8) ---
// echo-guard: destruct-vet blocks find -delete from READONLY exemption
const fdsid = 'fd' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name "*.tmp" -delete' } }); }
const fdf = runHook('echo-guard.js', { session_id: fdsid, tool_input: { command: 'find . -name "*.tmp" -delete' } });
check('echo-guard v3.3: find -delete NOT exempt (destruct-vet)', fdf.out.includes('deny') || fdf.out.includes('ask'));

// echo-guard: sort -o is destruct — not exempt
const sosid = 'so' + Date.now();
for (let i = 0; i < 5; i++) { runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } }); }
const sof = runHook('echo-guard.js', { session_id: sosid, tool_input: { command: 'sort data.txt -o output.txt' } });
check('echo-guard v3.3: sort -o NOT exempt', sof.out.includes('deny') || sof.out.includes('ask'));

// echo-guard: read-only find . -name IS exempt
const frsid = 'fr' + Date.now();
let frhit = false;
for (let i = 0; i < 6; i++) {
  const rr = runHook('echo-guard.js', { session_id: frsid, tool_input: { command: 'find . -name "*.py"' } });
  if (rr.out.includes('deny') || rr.out.includes('ask')) { frhit = true; }
}
check('echo-guard v3.3: read-only find exempt (no ladder)', !frhit);

// stop-guard: task-notification boundary must not satisfy userStop ("stops" boilerplate)
const tmpN = path.join(os.tmpdir(), 'sg-notif-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpN, [
  JSON.stringify({ type: 'user', message: { content: '[SYSTEM NOTIFICATION - NOT USER INPUT]\nA task-notification fires each time this agent stops with no live background children.' } }),
  JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: '第4轮[6A]: 干净轮0/2→继' }] } })
].join('\n'), 'utf8');
r = runHook('stop-guard.js', { transcript_path: tmpN });
check('stop-guard v3.2: notification "stops" boilerplate does not disarm stall gate', r.out.includes('"block"'));
try { fs.unlinkSync(tmpN); } catch (e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
