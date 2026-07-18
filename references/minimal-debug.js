// minimal-debug.js — test exact regex matching in stop-guard context
const s1 = JSON.stringify([
  { type: 'tool_use', name: 'Workflow', input: {} },
  { type: 'text', text: '第5轮[8A]: 干净轮1/2→继' }
]);
console.log('s1:', s1);
console.log('workflow regex match:', /"name":"(Workflow|Agent|Task)"/.test(s1));
console.log('preLaunchClaim match:', /第\d+轮[^"]{0,80}→继/.test(s1));

// Also test: does the stall regex also match? (第4轮完成，干净轮1/2)
const s2 = '第4轮完成，干净轮1/2';
console.log('\ns2:', s2);
console.log('stall match:', /第\d+轮[^"]{0,20}干净轮\s*[01]\s*\/\s*2/.test(s2));
console.log('preLaunchClaim match:', /第\d+轮[^"]{0,80}→继/.test(s2));
