const DESTRUCTIVE_FLAGS = new Set([
  '-delete', '-exec', '-execdir',
  '-fprint', '-fprint0', '-fprintf', '-fls',
  '-o', '-O', '--output',
]);
const READONLY_COMMANDS = new Set(['grep', 'rg', 'cat', 'head', 'tail', 'wc', 'diff', 'uniq', 'stat']);
const READONLY_WITH_POTENTIAL_FLAGS = new Set(['find', 'sort']);

// Exact copy of isReadonly from echo-guard.js L74-L92
function isReadonly(cmd) {
  const tokens = cmd.trim().split(/\s+/);
  if (!tokens.length) return false;
  const cmd0 = tokens[0].replace(/\\/g, '/').split('/').pop();
  if (READONLY_COMMANDS.has(cmd0)) return true;
  if (READONLY_WITH_POTENTIAL_FLAGS.has(cmd0)) {
    for (let i = 1; i < tokens.length; i++) {
      const tok = tokens[i];
      if (DESTRUCTIVE_FLAGS.has(tok)) return false;
      if (/^-[oO]\S/.test(tok) && !tok.startsWith('--')) return false;
    }
    return true;
  }
  return false;
}

console.log('=== EQUALS-FORM bypass (the reported bug) ===');
console.log('sort --output=dest.txt input.txt => READONLY?', isReadonly('sort --output=dest.txt input.txt'));
const tokens1 = 'sort --output=dest.txt input.txt'.split(/\s+/);
console.log('  Tokens:', JSON.stringify(tokens1));
console.log('  tok[1] =', JSON.stringify(tokens1[1]));
console.log('  tok[1] in DESTRUCTIVE_FLAGS?', DESTRUCTIVE_FLAGS.has(tokens1[1]));
console.log('  /^-[oO]\\S/.test(tok[1])?', /^-[oO]\S/.test(tokens1[1]));
console.log('  tok[1].startsWith("--")?', tokens1[1].startsWith('--'));

console.log('');
console.log('=== SPACE-FORM (correctly caught) ===');
console.log('sort --output dest.txt input.txt => READONLY?', isReadonly('sort --output dest.txt input.txt'));
const tokens2 = 'sort --output dest.txt input.txt'.split(/\s+/);
console.log('  Tokens:', JSON.stringify(tokens2));
console.log('  tok[1] in DESTRUCTIVE_FLAGS?', DESTRUCTIVE_FLAGS.has(tokens2[1]));

console.log('');
console.log('=== -o short form ===');
console.log('sort -o dest.txt input.txt => READONLY?', isReadonly('sort -o dest.txt input.txt'));
console.log('  -o in Set?', DESTRUCTIVE_FLAGS.has('-o'));

console.log('');
console.log('=== -O flag ===');
console.log('sort -O dest.txt input.txt => READONLY?', isReadonly('sort -O dest.txt input.txt'));

console.log('');
console.log('=== CONCLUSION ===');
if (isReadonly('sort --output=dest.txt input.txt')) {
  console.log('BUG CONFIRMED: sort --output=FILE equals-form is classified READONLY (exempt)');
  console.log('Root cause: --output=dest.txt is ONE token that does NOT match --output in Set');
  console.log('  AND it starts with -- so the /^-[oO]\\S/ regex guard does NOT fire');
} else {
  console.log('BUG NOT CONFIRMED (isReadonly returns false = destructive)');
}
