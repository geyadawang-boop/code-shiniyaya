const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOOK = fs.existsSync(path.join(__dirname, '..', 'hooks', 'echo-guard.js')) ? path.join(__dirname, '..', 'hooks', 'echo-guard.js') : path.join(os.homedir(), '.claude', 'hooks', 'echo-guard.js');
let pass = 0, fail = 0;

function runHook(payload) {
  const r = spawnSync('node', [HOOK], {
    input: JSON.stringify(payload), encoding: 'utf8', timeout: 10000,
    env: process.env
  });
  let out = '';
  try { out = (r.stdout || '').trim(); } catch(e) {}
  return { out: out, code: r.status === null ? 1 : r.status };
}

function check(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

const sid = 'interleave-' + Date.now();
const stateFile = path.join(os.tmpdir(), '.cc_echoguard_' + sid + '.json');

// Phase 1: destruct-vet confirmation
// find -delete is destruct -> NOT exempt
const sidFD = sid + '-fd';
for (let i = 0; i < 5; i++) { runHook({ session_id: sidFD, tool_input: { command: 'find . -name "*.tmp" -delete' } }); }
let r = runHook({ session_id: sidFD, tool_input: { command: 'find . -name "*.tmp" -delete' } });
check('echo-guard i1: find -delete escalates (destruct-vet)', r.out.includes('deny') || r.out.includes('ask'));

// sort -o is destruct -> NOT exempt
const sidSO = sid + '-so';
for (let i = 0; i < 5; i++) { runHook({ session_id: sidSO, tool_input: { command: 'sort data.txt -o output.txt' } }); }
r = runHook({ session_id: sidSO, tool_input: { command: 'sort data.txt -o output.txt' } });
check('echo-guard i2: sort -o escalates', r.out.includes('deny') || r.out.includes('ask'));

// grep is READONLY -> exempt forever
const sidGR = sid + '-gr';
for (let i = 0; i < 8; i++) { r = runHook({ session_id: sidGR, tool_input: { command: 'grep -n TODO CHANGELOG.md' } }); }
check('echo-guard i3: grep 8x exempt from ladder+cap', r.code === 0 && r.out === '{}');

// Phase 2: dual-timestamp cap freeze with interleaving
const capSid = sid + '-cap';
const capStateFile = path.join(os.tmpdir(), '.cc_echoguard_' + capSid + '.json');

// Write state with count=7, _capTs frozen at old, lastTs now
const frozenState = { count: 7, lastTs: Date.now(), _capTs: Date.now() - 7200000, wcFiles: [], hist: [] };
fs.writeFileSync(capStateFile, JSON.stringify(frozenState), 'utf8');

// Fire 2 exempt calls -> should NOT refresh _capTs or increment count
for (let i = 0; i < 2; i++) {
  r = runHook({ session_id: capSid, tool_input: { command: 'ls' } });
  check('echo-guard i4: exempt ls interleave ' + (i+1) + ' passes clean', r.code === 0 && r.out === '{}');
}

// Fire 1 non-exempt -> count=8 -> should hit cap
r = runHook({ session_id: capSid, tool_input: { command: 'python build.py' } });
check('echo-guard i5: cap freezes after exempt interleave, 8th non-exempt blocked', r.out.includes('block') && r.out.includes('cap exceeded'));

// Cleanup
try {
  const tmpDir = os.tmpdir();
  fs.readdirSync(tmpDir).filter(f => f.startsWith('.cc_echoguard_interleave-') || f.startsWith('.cc_echoguard_' + sid.replace(/\d+$/, ''))).forEach(f => {
    try { fs.unlinkSync(path.join(tmpDir, f)); } catch (e) {}
  });
} catch (e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
