// cwd-encoding-test.js — verify bearings.js cwd encoding matches CC project directories
const path = require('path');
const fs = require('fs');

// Exact encoding from bearings.js line 128
function encode(cwd) {
  return (cwd || '').replace(/^([A-Z]):/, '$1').replace(/[\\:]/g, '-').replace(/^([A-Z])-/, '$1--');
}

// Case 1: Windows backslash path (likely what CC actually sends)
const backslash = 'C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya';
console.log('Case 1 (backslash):', JSON.stringify(encode(backslash)));
console.log('  match:', encode(backslash) === 'C--Users-shiniyaya-Desktop-code-shiniyaya');

// Case 2: Forward slash path (alternate representation)
const forwardslash = 'C:/Users/shiniyaya/Desktop/code-shiniyaya';
console.log('Case 2 (forwardslash):', JSON.stringify(encode(forwardslash)));
console.log('  match:', encode(forwardslash) === 'C--Users-shiniyaya-Desktop-code-shiniyaya');

// Verify actual dirs exist
const projDir = 'C:/Users/shiniyaya/.claude/projects';
console.log('\nActual dirs in projects/:');
const dirs = fs.readdirSync(projDir).filter(d => d.includes('code-shiniyaya'));
console.log(dirs);

// Check if the encoded_backslash dir exists
const bsEncoded = encode(backslash);
console.log('\nBackslash-encoded dir exists:', fs.existsSync(path.join(projDir, bsEncoded)));
console.log('Forward-slash encoded dir exists:', fs.existsSync(path.join(projDir, encode(forwardslash))));
