const {spawnSync} = require('child_process');
const os = require('os');
const fs = require('fs');
const path = require('path');
const H = 'C:/Users/shiniyaya/.claude/hooks/stop-guard.js';

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

// (a) pre-launch gate blocks: transcript with  pre-launch claim but no Workflow/Agent/Task call
const tmpA = path.join(os.tmpdir(), 'sg-prelaunch-a-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpA, [
  JSON.stringify({ type: 'user', message: { content: '继续' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '第5轮[3A]: 干净轮候选扫描在飞→继\n\n继续执行扫描任务。' }
  ] } })
].join('\n'), 'utf8');
let r = runHook({ transcript_path: tmpA });
check('(a) pre-launch claim "第5轮[3A]:  干净轮候选扫描在飞→继" blocked (no Agent/Workflow/Task)', r.out.includes('"block"'));

// (b) saturation exemption: transcript with  ⚡ line -> /compact +   继 -> pre-launch gate passes
const tmpB = path.join(os.tmpdir(), 'sg-prelaunch-b-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpB, [
  JSON.stringify({ type: 'user', message: { content: '继续' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: '⚡ 第5轮:  干净轮0/2 — /compact + 继\n\n饱和优先线: 放弃发射Agent。' }
  ] } })
].join('\n'), 'utf8');
r = runHook({ transcript_path: tmpB });
check('(b) saturation "⚡ 第5轮: 干净轮0/2 — /compact + 继" passes (exempt)', r.code === 0 && r.out === '{}');

// (c) pre-launch with actual Agent call -> passes
const tmpC = path.join(os.tmpdir(), 'sg-prelaunch-c-' + Date.now() + '.jsonl');
fs.writeFileSync(tmpC, [
  JSON.stringify({ type: 'user', message: { content: '继续' } }),
  JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'tool_use', name: 'Agent', input: { prompt: 'scan for bugs' } },
    { type: 'text', text: '第6轮[4A]: 干净轮0/2→继' }
  ] } })
].join('\n'), 'utf8');
r = runHook({ transcript_path: tmpC });
check('(c) pre-launch with Agent call -> passes', r.code === 0 && r.out === '{}');

// cleanup
try { fs.unlinkSync(tmpA); } catch (e) {}
try { fs.unlinkSync(tmpB); } catch (e) {}
try { fs.unlinkSync(tmpC); } catch (e) {}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
