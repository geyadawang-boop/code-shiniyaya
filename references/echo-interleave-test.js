const {spawnSync} = require('child_process');
const os = require('os');
const fs = require('fs');
const path = require('path');
const H = 'C:/Users/shiniyaya/.claude/hooks/echo-guard.js';

function runHook(payload) {
  const x = spawnSync('node', [H], {
    input: JSON.stringify(payload), encoding: 'utf8', timeout: 10000
  });
  return {out: (x.stdout || '').trim(), code: x.status === null ? 1 : x.status};
}

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

const sid = 'ii' + Date.now();

// (a) find -delete destruct-vet: NOT exempt
const s1 = sid + 'a';
for (let i = 0; i < 5; i++) runHook({session_id: s1, tool_input: {command: 'find . -name "*.tmp" -delete'}});
let r = runHook({session_id: s1, tool_input: {command: 'find . -name "*.tmp" -delete'}});
check('(a) find -delete destruct-vet NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// (b) sort -o destruct-vet: NOT exempt
const s2 = sid + 'b';
for (let i = 0; i < 5; i++) runHook({session_id: s2, tool_input: {command: 'sort data.txt -o output.txt'}});
r = runHook({session_id: s2, tool_input: {command: 'sort data.txt -o output.txt'}});
check('(b) sort -o destruct-vet NOT exempt', r.out.includes('deny') || r.out.includes('ask'));

// (c) grep READONLY exempt forever
const s3 = sid + 'c';
for (let i = 0; i < 8; i++) r = runHook({session_id: s3, tool_input: {command: 'grep -n TODO CHANGELOG.md'}});
check('(c) grep 8x exempt from ladder+cap', r.code === 0 && r.out === '{}');

// (d) dual-timestamp cap freeze with exempt interleave
const s4 = sid + 'd';
const sf = path.join(os.tmpdir(), '.cc_echoguard_' + s4 + '.json');
// count=8 means next non-exempt → nextCount=9 → 9 > 8 (MAX_CALLS_PER_TURN) → cap fires
// _capTs=now-5s: close enough to avoid cap-reset window (now-capTs=5s < 30s TURN_GAP_MS)
// dual-timestamp: exempt calls don't refresh _capTs, non-exempt does
fs.writeFileSync(sf, JSON.stringify({count: 8, lastTs: Date.now(), _capTs: Date.now() - 5000, wcFiles: [], hist: []}));
// exempt call: must NOT refresh _capTs or count
r = runHook({session_id: s4, tool_input: {command: 'ls'}});
check('(d1) exempt ls interleave passes', r.code === 0 && r.out === '{}');
// non-exempt call: count 7+1=8 -> cap blocks
r = runHook({session_id: s4, tool_input: {command: 'python build.py'}});
check('(d2) cap fires after exempt interleave (dual-timestamp)', r.out.includes('block') && r.out.includes('cap exceeded'));

// cleanup
try {
  const tmp = os.tmpdir();
  const prefix = '.cc_echoguard_' + sid;
  fs.readdirSync(tmp).filter(f => f.startsWith('.cc_echoguard_ii')).forEach(f => {
    try { fs.unlinkSync(path.join(tmp, f)); } catch (e) {}
  });
} catch (e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
