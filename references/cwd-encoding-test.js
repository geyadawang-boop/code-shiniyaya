// cwd-encoding-test.js — verify bearings.js cwd encoding matches CC project directories
const path = require('path');
const os = require('os');
const fs = require('fs');

// Exact encoding from bearings.js line 128
function encode(cwd) {
  return (cwd || '').replace(/^([A-Z]):/, '$1').replace(/[\\:]/g, '-').replace(/^([A-Z])-/, '$1--');
}

const HOME = os.homedir();
const BACKSLASH_PATH = path.join(HOME, 'Desktop', 'code-shiniyaya');
const FORWARDSLASH_PATH = path.join(HOME, 'Desktop', 'code-shiniyaya').replace(/\\/g, '/');
const EXPECTED = 'C--Users-shiniyaya-Desktop-code-shiniyaya';

// Case 1: Windows backslash path (likely what CC actually sends)
const backslash = BACKSLASH_PATH;
console.log('Case 1 (backslash):', JSON.stringify(encode(backslash)));
console.log('  match:', encode(backslash) === EXPECTED);

// Case 2: Forward slash path (alternate representation)
const forwardslash = FORWARDSLASH_PATH;
console.log('Case 2 (forwardslash):', JSON.stringify(encode(forwardslash)));
console.log('  match:', encode(forwardslash) === 'C--Users-shiniyaya-Desktop-code-shiniyaya');

// Verify actual dirs exist
const projDir = path.join(HOME, '.claude', 'projects');
console.log('\nActual dirs in projects/:');
const dirs = fs.readdirSync(projDir).filter(d => d.includes('code-shiniyaya'));
console.log(dirs);

// Check if the encoded_backslash dir exists
const bsEncoded = encode(backslash);
console.log('\nBackslash-encoded dir exists:', fs.existsSync(path.join(projDir, bsEncoded)));
console.log('Forward-slash encoded dir exists:', fs.existsSync(path.join(projDir, encode(forwardslash))));
