const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

// echo-guard.js v4.3 — PreToolUse Bash hook: echo blocking + call cap + fingerprint escalation
// v4.2: fingerprint file-arg normalization (rm a.mp4/rm b.mp4→same fp, Scan35 P1 fix)
// v4.3: echo-block/wc-loop/cap-exceeded paths now use deny() helper (hookSpecificOutput.permissionDecision: 'deny')
//       instead of bare respond({decision:'block'}) — Scan37 P1: bare object may be ignored by CC PreToolUse handler

const TMP = process.env.TEMP || process.env.TMPDIR || os.tmpdir();
const TURN_GAP_MS = 30_000;
const FP_TTL_MS = 900_000;
const FP_MAX = 20;
const MAX_CALLS_PER_TURN = 8;

// v3.6 destruct-vet: token-array based (replaces regex flag enumeration)
// Mirrors test_security.py Set-based validation pattern:
// ALLOWED_COMMANDS and DESTRUCTIVE_FLAGS are explicit data structures,
// not regexes that grow edge cases with each new flag discovery.

const ECHO_BLOCK = [
  /^echo\s*$/,
  /^echo\s+(""|'')\s*$/,
  /^echo\s+["']?(done|ok|final|complete|verified|confirmed)["']?\s*$/i,
  /^echo\s+["']?\d+["']?\s*$/,
];

// Commands that are PURE-read-only WITH NO WRITE FLAGS -> fingerprint/cap exempt
const READONLY_COMMANDS = new Set([
  'grep', 'rg', 'cat', 'head', 'tail', 'wc',
  'uniq', 'stat',
]);

// Commands that ARE read-only by default BUT have destructive flags
// that must negate exemption. Modeled after COMMANDS_NEEDING_EXTRA_VALIDATION.
const DESTRUCTIVE_FLAGS = new Set([
  '-delete', '-exec', '-execdir', '-ok', '-okdir',
  '-fprint', '-fprint0', '-fprintf', '-fls',
  '--output',
]);

// DESTRUCTIVE flags that only apply to sort (not to find)
const SORT_ONLY_DESTRUCTIVE = new Set(['-o', '-O']);

// IDEMPOTENT commands exempt from fingerprint ladder + cap
const IDEMPOTENT_COMMANDS = new Set([
  'git', 'ls', 'pwd',
]);

// Commands that are READONLY (exempt) BUT the command itself might use
// destructive flags. We filter by checking each token against DESTRUCTIVE_FLAGS.
// find, sort, diff are commands that have both read-only and destructive modes.
const READONLY_WITH_POTENTIAL_FLAGS = new Set([
  'find', 'sort', 'diff',
]);

function respond(obj) {
  try { process.stdout.write(JSON.stringify(obj)); } catch (e) {}
  process.exit(0);
}
function deny(reason) {
  respond({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason } });
}
function ask(reason) {
  respond({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'ask', permissionDecisionReason: reason } });
}

// v3.6: token-based purity check — replaces regex metachar detection.
// A command is PURE if it has NO chain/redirect/expansion metacharacters.
function isPure(cmd) {
  return !/[;&|`$><\n]/.test(cmd);
}

// v3.6: token-based READONLY determination — replaces L115 regex.
// Steps:
//   1. Tokenize via split on whitespace
//   2. First token = command word (strip path prefix if present, e.g. /usr/bin/grep)
//   3. If command is in READONLY_COMMANDS → check remaining tokens for DESTRUCTIVE_FLAGS
//   4. If no destructive flags found → READONLY = true
//   5. Special case: node hooks.test.js is always READONLY (like before)
function isReadonly(cmd) {
  const tokens = cmd.trim().split(/\s+/);
  if (!tokens.length) return false;
  const cmd0 = tokens[0].replace(/\\/g, '/').split('/').pop(); // strip any path prefix
  if (/^node\s/.test(cmd) && /hooks\.test\.js/.test(cmd)) return true;
  // Explicit readonly commands (no destructive flags to worry about)
  if (READONLY_COMMANDS.has(cmd0)) return true;
  // Commands that CAN be readonly but need flag vetting
  if (READONLY_WITH_POTENTIAL_FLAGS.has(cmd0)) {
    for (let i = 1; i < tokens.length; i++) {
      const tok = tokens[i];
      if (DESTRUCTIVE_FLAGS.has(tok)) return false;
      // v4.1: command-context-aware flag checks — sort-only destructive flags
      if (cmd0 === 'sort' && SORT_ONLY_DESTRUCTIVE.has(tok)) return false;
      // v4.1: --flag=value equals forms (--output=file, --output file both caught)
      if (tok.startsWith('--output=')) return false;
      // Also catch -oout (no space form) — only destructive for sort
      if (cmd0 === 'sort' && /^-[oO]\S/.test(tok)) return false;
    }
    return true;
  }
  return false;
}

function isIdempotent(cmd) {
  if (!isPure(cmd)) return false;
  const tokens = cmd.trim().split(/\s+/);
  if (!tokens.length) return false;
  const cmd0 = tokens[0].replace(/\\/g, '/').split('/').pop();
  if (!IDEMPOTENT_COMMANDS.has(cmd0)) return false;
  // git subcommands: status|log|branch|diff --stat|remote — but NOT
  // branch -d/-D (destructive) or remote add/remove (mutate config)
  if (cmd0 === 'git') {
    const sub = tokens[1];
    if (!/^(status|log|branch|diff|remote)$/.test(sub)) return false;
    // git branch: only bare 'branch' (no args) is idempotent; any flag = non-idempotent
    if (sub === 'branch' && tokens[2] && tokens[2].startsWith('-')) return false;
    // git remote: only bare 'remote -v' or 'remote show' are idempotent reads
    if (sub === 'remote') {
      const sub2 = tokens[2];
      if (sub2 && !/^(-v|--verbose|show)$/.test(sub2)) return false;
    }
    return sub === 'status' || sub === 'log' || sub === 'diff' || sub === 'branch' || sub === 'remote';
  }
  return true; // ls, pwd — unconditionally idempotent
}

function run(input) {
  let payload = {};
  try { payload = JSON.parse(input.replace(/^﻿/, '') || '{}'); } catch (e) { respond({}); }

  const cmd = ((payload.tool_input && payload.tool_input.command) || '').trim();
  const sid = payload.session_id || 'default';
  const counterFile = path.join(TMP, '.cc_echoguard_' + sid + '.json');

  if (!cmd) respond({});

  let state = { count: 0, lastTs: 0, wcFiles: [], hist: [] };
  try { state = Object.assign(state, JSON.parse(fs.readFileSync(counterFile, 'utf8').replace(/^﻿/, ''))); } catch (e) {}
  if (!Array.isArray(state.hist)) state.hist = [];
  if (!Array.isArray(state.wcFiles)) state.wcFiles = [];
  if (typeof state.count !== 'number' || !isFinite(state.count)) state.count = 0;
  if (typeof state.lastTs !== 'number' || !isFinite(state.lastTs)) state.lastTs = 0;
  if (typeof state._capTs !== 'number' || !isFinite(state._capTs)) state._capTs = 0;

  const now = Date.now();
  if (now - state.lastTs > TURN_GAP_MS) { state.count = 0; state.wcFiles = []; }
  const capTs = state._capTs || state.lastTs;
  if (now - capTs > TURN_GAP_MS) { state.count = 0; }

  // Check 1: trivial echo
  for (const pattern of ECHO_BLOCK) {
    if (pattern.test(cmd)) {
      deny('echo-guard: trivial/confirmation echo wastes tokens. Do real work or end the turn.');
    }
  }

  // Check 2: wc -l same-file loop
  const wcMatch = cmd.match(/^wc\s+-l\s+(.+)$/);
  if (wcMatch) {
    const file = wcMatch[1].trim();
    if (state.wcFiles.includes(file)) {
      deny('echo-guard: wc -l on same file twice in one turn. Line count already known.');
    }
    state.wcFiles.push(file);
  }

  const PURE = isPure(cmd);
  const IDEMPOTENT = PURE && isIdempotent(cmd);
  const READONLY = PURE && isReadonly(cmd);
  const EXEMPT = IDEMPOTENT || READONLY;
  let hits = 0;
  let fp = null;
  state.hist = state.hist.filter(h => now - h.ts < FP_TTL_MS);
  if (!EXEMPT) {
    const sp = cmd.replace(/\s+/g, ' ').replace(/["']/g, '');
    // v4.2: normalize file-path args in fingerprint — rm a.mp4 / rm b.mp4 / rm c.mp4
    // all become rm <FILE>, closing the fingerprint ladder bypass (Scan35 P1).
    // Empty token after normalization (e.g. bare "/path/to/dir/" → "") is dropped.
    const norm = sp.replace(/^(\S+)/, (w) => w.toLowerCase())
      .split(' ').map(tok => {
        if (/^-[a-zA-Z]/.test(tok)) return tok;          // flags: keep
        if (/^(\.{0,2}\/|\/|[A-Za-z]:[\\/])/.test(tok)) return '<PATH>';  // absolute/relative path
        if (/\.[a-zA-Z0-9]{1,10}$/.test(tok)) return '<FILE>';            // file with extension
        if (/^[0-9]+$/.test(tok)) return tok;           // numeric arg: keep (ports, counts)
        return tok;
      }).filter(Boolean).join(' ');
    fp = crypto.createHash('md5').update(norm).digest('hex').slice(0, 12);
    hits = state.hist.filter(h => h.fp === fp).length;
  }

  const nextCount = state.count + (EXEMPT ? 0 : 1);
  if (nextCount > MAX_CALLS_PER_TURN) {
    deny('echo-guard: ' + MAX_CALLS_PER_TURN + ' non-readonly Bash calls/turn cap exceeded. Likely a loop — stop and end the turn.');
  }
  if (fp) {
    state.hist.push({ fp, ts: now });
    if (state.hist.length > FP_MAX) state.hist.shift();
  }
  state.count = nextCount;
  state.lastTs = now;
  state._capTs = EXEMPT ? (state._capTs || state.lastTs) : now;
  try {
    const tmpFile = counterFile + '.tmp';
    fs.writeFileSync(tmpFile, JSON.stringify(state), 'utf8');
    fs.renameSync(tmpFile, counterFile);
  } catch (e) {}

  try {
    const names = fs.readdirSync(TMP).filter(f => f.startsWith('.cc_echoguard_') && f !== path.basename(counterFile));
    let removed = 0;
    for (const f of names) {
      if (removed >= 20) break;
      const p = path.join(TMP, f);
      try { if (now - fs.statSync(p).mtimeMs > 86_400_000) { fs.unlinkSync(p); removed++; } } catch (e) {}
    }
  } catch (e) {}

  if (hits >= 3) {
    deny('echo-guard v3: same command ' + (hits + 1) + 'th time (cross-turn fingerprint). Loop signal — switch strategy or write snapshot and stop.');
  }
  if (hits === 2) {
    ask('echo-guard v3: same command 3rd time — confirm this is necessary?');
  }
  if (hits === 1) {
    respond({ systemMessage: 'echo-guard v3: command repeats a recent one (2nd time in 15min).' });
  }

  respond({});
}

let buf = '';
let finished = false;
function finish() { if (finished) return; finished = true; run(buf); }
process.stdin.on('data', (chunk) => { buf += chunk; });
process.stdin.on('end', finish);
process.stdin.on('error', finish);
setTimeout(finish, 1000).unref();
