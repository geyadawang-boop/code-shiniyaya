#!/usr/bin/env node
// hooks.test.js — zero-dep runnable check for the 3 defense hooks (ponytail "one runnable check" rule)
// Run: node references/hooks.test.js
// History: v1.0 shipped argv-vs-stdin bug (all regexes dead), v3.0 shipped ReferenceError in deny
// tier (fail-open). Both broke in paths manual testing skipped. This file closes that class.
// v1.1: spawnSync with input option — no shell, no quoting hazards.

const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOOKS = 'C:/Users/shiniyaya/.claude/hooks';
let pass = 0, fail = 0;

function runHook(hook, payload) {
  const r = spawnSync('node', [path.join(HOOKS, hook)], {
    input: JSON.stringify(payload), encoding: 'utf8', timeout: 10000
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

r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'wc -l SKILL.md' } });
check('echo-guard: first wc -l passes', r.code === 0 && !r.out.includes('"block"'));
r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'wc -l SKILL.md' } });
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

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
