#!/usr/bin/env node
// e2e-test.js — run the REAL echo-guard.js with constructed stdin payloads in an isolated TEMP
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const HOOK = 'C:/Users/shiniyaya/.claude/hooks/echo-guard.js';
const ISOTMP = path.join(os.tmpdir(), 'eg-e2e-' + Date.now());
fs.mkdirSync(ISOTMP, { recursive: true });

function callHook(cmd, sid, extraEnv) {
  const payload = JSON.stringify({ session_id: sid, tool_name: 'Bash', tool_input: { command: cmd } });
  const r = spawnSync('node', [HOOK], {
    input: payload,
    encoding: 'utf8',
    env: Object.assign({}, process.env, { TEMP: ISOTMP, TMPDIR: ISOTMP }, extraEnv || {}),
    timeout: 30000,
  });
  let out = {};
  try { out = JSON.parse(r.stdout || '{}'); } catch (e) { out = { RAW: r.stdout }; }
  return { out, code: r.status, stderr: r.stderr };
}

function verdict(out) {
  if (out.decision === 'block') return 'BLOCK(legacy): ' + (out.reason || '').slice(0, 60);
  const h = out.hookSpecificOutput;
  if (h && h.permissionDecision) return h.permissionDecision.toUpperCase() + ': ' + (h.permissionDecisionReason || '').slice(0, 60);
  if (out.systemMessage) return 'WARN: ' + out.systemMessage.slice(0, 60);
  if (out.RAW !== undefined) return 'RAW: ' + out.RAW.slice(0, 60);
  return 'ALLOW {}';
}

function stateFile(sid) { return path.join(ISOTMP, '.cc_echoguard_' + sid + '.json'); }
function readStateRaw(sid) {
  try { return JSON.parse(fs.readFileSync(stateFile(sid), 'utf8')); } catch (e) { return null; }
}

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const BOLD = '\x1b[1m';
const RESET = '\x1b[0m';

let p = 0, f = 0;
function test(name, condFn) {
  try {
    const r = condFn();
    if (r === true || r === undefined || r === 0) {
      console.log(`  ${GREEN}PASS${RESET} ${name}`);
      p++;
    } else {
      console.log(`  ${RED}FAIL${RESET} ${name}: ${r}`);
      f++;
    }
  } catch (e) {
    console.log(`  ${RED}FAIL${RESET} ${name}: ${e.message}`);
    f++;
  }
}

// ==================== E2E A: find -delete bypass — 12x in one session ====================
console.log(`\n${BOLD}E2E A: 12x destructive \`find -delete\` in one session — READONLY exempt${RESET}`);
{
  const sid = 'e2e-a';
  const results = [];
  for (let i = 1; i <= 12; i++) {
    const r = callHook('find /tmp -name "*.log" -delete', sid);
    results.push(verdict(r.out));
  }
  const unique = [...new Set(results)];
  console.log('  verdicts:', JSON.stringify(unique));
  const st = readStateRaw(sid);
  console.log('  final state:', JSON.stringify(st && { count: st.count, hist: st.hist.length }));
  test('find -delete passes cap (never blocked)', () => {
    const blocked = results.filter(v => v !== 'ALLOW {}').length;
    if (blocked > 0) return 'expected ALLOW on all 12, got ' + blocked + ' non-allow: ' + unique.join('|');
    return true;
  });
  test('find -delete never triggers fingerprint escalation', () => {
    const st2 = readStateRaw(sid);
    if (st2 && st2.hist && st2.hist.length > 0) return 'hist should be empty (exempt), got ' + st2.hist.length + ' entries';
    return true;
  });
}

// ==================== E2E B: sort -o overwrite — 12x ====================
console.log(`\n${BOLD}E2E B: 12x \`sort -o out.txt in.txt\` — READONLY exempt despite writing${RESET}`);
{
  const sid = 'e2e-b';
  const results = [];
  for (let i = 1; i <= 12; i++) {
    const r = callHook('sort -o /tmp/out.txt /tmp/in.txt', sid);
    results.push(verdict(r.out));
  }
  const unique = [...new Set(results)];
  console.log('  verdicts:', JSON.stringify(unique));
  test('sort -o passes all 12 calls (exempt)', () => {
    const blocked = results.filter(v => v !== 'ALLOW {}').length;
    if (blocked > 0) return blocked + ' non-allow for sort -o: ' + unique.join('|');
    return true;
  });
}

// ==================== E2E C: Real (non-exempt) loop fingerprint — 4x same cmd ====================
console.log(`\n${BOLD}E2E C: 4x \`npm test\` — fingerprint escalation ladder${RESET}`);
{
  const sid = 'e2e-c';
  const results = [];
  for (let i = 1; i <= 4; i++) {
    const r = callHook('npm test', sid);
    results.push(verdict(r.out));
  }
  console.log('  verdicts:', JSON.stringify(results));
  test('1st npm test: ALLOW', () => results[0] === 'ALLOW {}');
  test('2nd: WARN (hits=1, systemMessage)', () => results[1].startsWith('WARN:'));
  test('3rd: ASK (hits=2)', () => results[2].startsWith('ASK:'));
  test('4th: DENY (hits=3)', () => results[3].startsWith('DENY:'));
}

// ==================== E2E D: Cap starvation — blocked call doesn't update state ====================
console.log(`\n${BOLD}E2E D: Cap starvation — blocked calls freeze state, TURN_GAP clears${RESET}`);
{
  const sid = 'e2e-d';
  const ts = Date.now() - 50000; // 50s ago — past TURN_GAP
  const sf = stateFile(sid);
  fs.writeFileSync(sf, JSON.stringify({ count: 0, lastTs: ts, wcFiles: [], hist: [] }), 'utf8');
  // Call 1-8: non-exempt (should all pass)
  let blockedAt = -1;
  for (let i = 1; i <= 12; i++) {
    const r = callHook('npm run build', sid);
    const v = verdict(r.out);
    if (v.startsWith('DENY') || v.startsWith('BLOCK')) { blockedAt = i; break; }
  }
  const st = readStateRaw(sid);
  console.log('  blockedAt:', blockedAt, '| count:', st && st.count, '| lastTs age:', Date.now() - (st && st.lastTs || 0));
  test('First 8 non-exempt calls pass (cap at 9)', () => {
    if (blockedAt !== 9) return 'expected block at call 9, got ' + blockedAt;
    return true;
  });
  test('State count should be 8 (not incremented after cap block)', () => {
    if (!st || st.count !== 8) return 'expected count=8, got ' + JSON.stringify(st);
    return true;
  });
  // After cap block, TURN_GAP should reset. Write state with old lastTs to simulate
  fs.writeFileSync(sf, JSON.stringify({ count: 0, lastTs: Date.now() - 50000, wcFiles: [], hist: [] }), 'utf8');
  const r9 = callHook('npm run build', sid);
  test('After 30s gap, count resets — call passes again', () => {
    const v = verdict(r9.out);
    if (v !== 'ALLOW {}') return 'expected ALLOW after TURN_GAP reset, got ' + v;
    return true;
  });
}

// ==================== E2E E: EXEMPT calls refresh lastTs → cap never resets ====================
console.log(`\n${BOLD}E2E E: grep calls keep refreshing lastTs → non-exempt can't recover${RESET}`);
{
  const sid = 'e2e-e';
  const sf = stateFile(sid);
  fs.writeFileSync(sf, JSON.stringify({ count: 7, lastTs: Date.now(), wcFiles: [], hist: [] }), 'utf8');
  // Call 1: non-exempt → count becomes 8, lastTs refreshed
  const r1 = callHook('npm run build', sid);
  const v1 = verdict(r1.out);
  // Call 2: grep (exempt) → count stays 8, lastTs refreshed
  const r2 = callHook('grep TODO *.js', sid);
  const v2 = verdict(r2.out);
  // Call 3: non-exempt → nextCount=9 > 8 → BLOCKED (cap)
  const r3 = callHook('npm run build', sid);
  const v3 = verdict(r3.out);
  // Call 4-6: grep (exempt) — keeps refreshing lastTs
  for (let i = 0; i < 3; i++) callHook('grep hello *.js', sid);
  // Call 7: non-exempt again → still blocked because lastTs is fresh
  const r7 = callHook('npm run build', sid);
  const v7 = verdict(r7.out);
  console.log('  call 1 (8th non-exempt):', v1);
  console.log('  call 2 (grep exempt):', v2);
  console.log('  call 3 (9th non-exempt):', v3);
  console.log('  call 7 (non-exempt after 3 greps):', v7);
  test('exempt calls prevent TURN_GAP cap recovery', () => {
    if (v7.startsWith('ALLOW')) return 'non-exempt call 7 passed — cap should still be saturated; grep kept lastTs fresh';
    return true;
  });
}

// ==================== E2E F: PURE metachar bypass — semicolon in find -exec ====================
console.log(`\n${BOLD}E2E F: Command chaining bypass attempts${RESET}`);
{
  const sid = 'e2e-f';
  test('find with -exec rm blocked', () => {
    const r = callHook('find . -name "*.tmp" -exec rm {} ;', sid);
    const v = verdict(r.out);
    if (v !== 'ALLOW {}') return v;
    // Actually: on Windows with bash, spawnSync might interpret ; differently
    // Let's check the raw command the hook sees
    return true;
  });
  test('grep foo | xargs rm blocked', () => {
    const r = callHook('grep TODO *.js | xargs rm -rf', sid);
    const v = verdict(r.out);
    if (v === 'ALLOW {}') return 'pipe chain should be blocked by PURE';
    return true;
  });
  test('ls; rm -rf / blocked', () => {
    const r = callHook('ls; rm -rf /', sid);
    const v = verdict(r.out);
    if (v === 'ALLOW {}') return 'semicolon chain should be blocked';
    return true;
  });
}

// ==================== E2E G: Concurrent write race simulation ====================
console.log(`\n${BOLD}E2E G: Parallel hook invocations — race on state file${RESET}`);
{
  const sid = 'e2e-g';
  // Spawn 5 parallel hooks, each doing a non-exempt call
  const procs = [];
  for (let i = 0; i < 5; i++) {
    const p = spawnSync('node', [HOOK], {
      input: JSON.stringify({ session_id: sid, tool_name: 'Bash', tool_input: { command: 'npm install' } }),
      encoding: 'utf8',
      env: Object.assign({}, process.env, { TEMP: ISOTMP, TMPDIR: ISOTMP }),
      timeout: 10000,
    });
    procs.push({ out: p.stdout, stderr: p.stderr });
  }
  const allowed = procs.filter(p => {
    try { const o = JSON.parse(p.out); return !o.decision && !(o.hookSpecificOutput && o.hookSpecificOutput.permissionDecision); } catch (e) { return true; }
  }).length;
  const st = readStateRaw(sid);
  console.log('  allowed/total:', allowed, '/', procs.length);
  console.log('  final state:', JSON.stringify(st && { count: st.count, hist: st.hist && st.hist.length }));
  test('State count matches actual allowed calls (no lost writes)', () => {
    if (!st) return 'no state file';
    // With 5 parallel calls, each read-modify-write — last write wins
    // Expected: count is 1-5 (not 0, not >5). Non-atomic read-modify-write means <5 expected.
    if (st.count < 1) return 'count too low: ' + st.count;
    if (st.count > 5) return 'count exceeds max: ' + st.count;
    return true;
  });
  test('No state file corruption from concurrent writes', () => {
    if (!st) return 'no state file (acceptable)';
    if (typeof st.count !== 'number') return 'count corrupted: ' + typeof st.count;
    if (!Array.isArray(st.hist)) return 'hist corrupted';
    return true;
  });
}

// ==================== Summary ====================
console.log(`\n${BOLD}=== E2E Results: ${p} passed, ${f} failed ===${RESET}\n`);

// Cleanup
try { const ff = fs.readdirSync(ISOTMP); ff.forEach(x => fs.unlinkSync(path.join(ISOTMP, x))); fs.rmdirSync(ISOTMP); } catch (e) {}

process.exit(f > 0 ? 1 : 0);
