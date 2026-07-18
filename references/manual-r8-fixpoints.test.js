#!/usr/bin/env node
// manual-r8-fixpoints.test.js — v4.1 r8 精确定点验证 (7个修复点)
// 只测试 r8 中实际编辑的修复点，防止回归
const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOOKS = 'C:/Users/shiniyaya/.claude/hooks';
let pass = 0, fail = 0;

function runHook(hook, payload) {
  const r = spawnSync('node', [path.join(HOOKS, hook)], {
    input: JSON.stringify(payload), encoding: 'utf8', timeout: 10000,
  });
  return { out: (r.stdout || '').trim(), code: r.status === null ? 1 : r.status };
}

function check(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name + ' <<< REGRESSION'); }
}

// Helper: test that a command is READONLY (never escalates across 6 calls)
function testReadonlyExempt(cmd, desc) {
  const sid = 'ro-' + desc.replace(/[^a-z0-9]/gi, '') + '-' + Date.now();
  let escalated = false;
  for (let i = 0; i < 6; i++) {
    const r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: cmd } });
    if (r.out.includes('deny') || r.out.includes('ask') || r.out.includes('systemMessage')) {
      escalated = true;
    }
  }
  check(desc + ': EXEMPT (no ladder)', !escalated);
}

// Helper: test that a command IS destruct (escalates after repeated calls)
function testDestructVet(cmd, desc) {
  const sid = 'dv-' + desc.replace(/[^a-z0-9]/gi, '') + '-' + Date.now();
  for (let i = 0; i < 5; i++) {
    runHook('echo-guard.js', { session_id: sid, tool_input: { command: cmd } });
  }
  const r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: cmd } });
  check(desc + ': NOT EXEMPT (destruct-vet caught)',
    r.out.includes('deny') || r.out.includes('ask') || r.out.includes('systemMessage'));
}

// Helper: test that a git command is NON-idempotent (escalates)
function testGitNonIdempotent(cmd, desc) {
  const sid = 'git-' + desc.replace(/[^a-z0-9]/gi, '') + '-' + Date.now();
  for (let i = 0; i < 5; i++) {
    runHook('echo-guard.js', { session_id: sid, tool_input: { command: cmd } });
  }
  const r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: cmd } });
  check(desc + ': NON-IDEMPOTENT (escalated)',
    r.out.includes('deny') || r.out.includes('ask') || r.out.includes('systemMessage'));
}

console.log('=== v4.1 r8 精确定点验证 ===\n');

// ============ (i) find -o (logic OR) — should be exempt (readonly find) ============
testReadonlyExempt('find . -name "*.js" -o -name "*.ts"', '(i) find -o logic OR exempt');

// ============ (i') find -delete still NOT exempt ============
testDestructVet('find . -name "*.tmp" -delete', '(i) find -delete still NOT exempt');

// ============ (ii) sort -o out in (flag-last) still NOT exempt ============
testDestructVet('sort data.txt -o output.txt', '(ii) sort -o flag-last NOT exempt');

// ============ (iii) sort --output=out in (equals-form) NOT exempt ============
testDestructVet('sort --output=out.txt input.txt', '(iii) sort --output=file (equals-form) NOT exempt');

// ============ (iii') sort --output=out in (space-form) also NOT exempt ============
testDestructVet('sort --output out2.txt input.txt', '(iii) sort --output file (space-form) NOT exempt');

// ============ (iv) diff --output=patch file1 file2 NOT exempt ============
testDestructVet('diff --output=mypatch.diff old.txt new.txt', '(iv) diff --output=patch NOT exempt');

// ============ (iv') plain diff (no --output) IS exempt (readonly) ============
testReadonlyExempt('diff old.txt new.txt', '(iv) plain diff IS exempt');

// ============ (v) git remote add origin url — non-idempotent ============
testGitNonIdempotent('git remote add origin https://example.com/repo.git', '(v) git remote add NON-idempotent');

// ============ (v') git remote -v (bare verbose) — idempotent (baseline) ============
// Test: should pass all 6 calls without escalation
(function() {
  const sid = 'gitrv-' + Date.now();
  let esc = false;
  for (let i = 0; i < 6; i++) {
    const r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'git remote -v' } });
    if (r.out.includes('deny') || r.out.includes('ask') || r.out.includes('systemMessage')) esc = true;
  }
  check('(v) git remote -v still IDEMPOTENT (baseline)', !esc);
})();

// ============ (vi) git branch -d main — non-idempotent ============
testGitNonIdempotent('git branch -d main', '(vi) git branch -d NON-idempotent');

// ============ (vi') git branch (bare) — idempotent (baseline) ============
(function() {
  const sid = 'gitbr-' + Date.now();
  let esc = false;
  for (let i = 0; i < 6; i++) {
    const r = runHook('echo-guard.js', { session_id: sid, tool_input: { command: 'git branch' } });
    if (r.out.includes('deny') || r.out.includes('ask') || r.out.includes('systemMessage')) esc = true;
  }
  check('(vi) git branch bare still IDEMPOTENT (baseline)', !esc);
})();

// ============ (vi'') git branch -D — also non-idempotent ============
testGitNonIdempotent('git branch -D main', '(vi) git branch -D NON-idempotent');

// ============ (vii) -ok 在 DESTRUCTIVE_FLAGS Set 中被捕获 ============
testDestructVet('find . -ok rm {} \\;', '(vii) find -ok in DESTRUCTIVE_FLAGS caught');

// ============ (vii') -okdir 在 DESTRUCTIVE_FLAGS Set 中被捕获 ============
testDestructVet('find . -okdir rm {} \\;', '(vii) find -okdir in DESTRUCTIVE_FLAGS caught');

// ============ Bonus: sort -o file in (flag-last, no-space form -oout) ============
testDestructVet('sort -oout.txt input.txt', 'sort -ofile (no-space form) NOT exempt');

// ============ Bonus: find with CMD_AND logic but no destructive flag ============
testReadonlyExempt('find . -name "*.js" -print', '(bonus) find -print IS exempt');

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
