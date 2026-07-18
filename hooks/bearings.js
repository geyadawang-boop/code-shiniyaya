#!/usr/bin/env node
// bearings.js — SessionStart hook: 自动GET-BEARINGS (SKILL.md §一字恢复 步骤1-6)
// v3.0 — matcher: startup|resume|clear|compact → session/compact start context injection
//        v2: NEXT ACTION注入; v3: STATE-json + 兄弟hook自检(hookWarn, 含JSON合法性/缺失/空文件检测)
//        v3.0-r9: journal路径UUID嵌套层修复 + cwd-scoped journal scan (projects/{pd}/{uuid}/subagents/workflows/)
// 清偿 L178 ponytail:debt (upgrade条件: CC支持SessionStart) + L187-193 三道防线零成本增强
// Follows SKILL.md §Hook Infrastructure: silent-fail, BOM stripping, always exit 0

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function git(cwd, args) {
  try {
    return execFileSync('git', ['-C', cwd].concat(args), { timeout: 5000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '(n/a)';
  }
}

let input = '';
try { input = fs.readFileSync(0, 'utf8'); } catch (e) {}

let cwd = process.cwd();
try {
  const payload = JSON.parse(input.replace(/^﻿/, '') || '{}');
  cwd = payload.cwd || cwd;
} catch (e) {}

try {
  // Guard: only activate in code-shiniyaya repos. CHANGELOG.md alone is too common
  // (every reference repo has one) — require memory/snapshot-*.md, or SKILL.md whose
  // frontmatter names code-shiniyaya (cold start before first snapshot).
  let snaps = [];
  try {
    const memDir = path.join(cwd, 'memory');
    if (fs.existsSync(memDir)) {
      snaps = fs.readdirSync(memDir).filter(f => /^snapshot-.*\.md$/.test(f)).sort();
    }
  } catch (e) {}
  if (snaps.length === 0) {
    let isSkill = false;
    try {
      const head = fs.readFileSync(path.join(cwd, 'SKILL.md'), 'utf8').slice(0, 300);
      isSkill = /name:\s*code-shiniyaya/.test(head);
    } catch (e) {}
    if (!isSkill) process.exit(0); // not a code-shiniyaya repo → silent
  }

  let chlog = '(no CHANGELOG)';
  try {
    chlog = fs.readFileSync(path.join(cwd, 'CHANGELOG.md'), 'utf8').split('\n').slice(0, 15).join('\n');
  } catch (e) {}
  let memCount = 0;
  try { memCount = fs.readdirSync(path.join(cwd, 'memory')).length; } catch (e) {}

  // v2 (v4.7.8): NEXT ACTION first-line injection — read nextAction from latest snapshot,
  // put it at the highest-attention position so recovery is machine-prompted, not model-recalled.
  let next = '';
  let stateJson = '';
  try {
    if (snaps.length) {
      const body = fs.readFileSync(path.join(cwd, 'memory', snaps[snaps.length - 1]), 'utf8');
      const m = body.match(/nextAction\*{0,2}\s*[:=：]\s*\*{0,2}(scan|await|fix|verify)/);
      if (m) {
        const hints = {
          scan: ' — launch next scan Agents immediately (rule 24 decision ②; check saturation/budget/in-flight gates first)',
          await: ' — agents in flight: process arrived results FIRST, do not re-launch (decision ①)',
          fix: ' — resume from first pending item (decision ③)',
          verify: ' — run rule-24 final 50-Agent verification before declaring convergence (decision ④)'
        };
        next = 'NEXT ACTION: ' + m[1] + (hints[m[1]] || '');
      }
      // v3: STATE-json — machine-readable snapshot digest (Scan 4 carry-forward)
      const ver = (body.match(/\*{0,2}版本\*{0,2}\s*[:：]\s*\*{0,2}(v[\d.]+(?:-r\d+)?)/) || [])[1] || '';
      const rounds = (body.match(/干净轮(?:计数)?\*{0,2}\s*[:：]?\s*\*{0,2}\s*(\d\s*\/\s*2)/) || [])[1] || '';
      const complete = /SNAPSHOT-COMPLETE/.test(body);
      stateJson = 'STATE: ' + JSON.stringify({ version: ver, nextAction: m ? m[1] : '', cleanRounds: rounds.replace(/\s/g, ''), snapshotComplete: complete, snapshotFile: snaps[snaps.length - 1] });
    }
  } catch (e) {}

  // v3: sibling-hook self-check (Scan 4 carry-forward) — detect settings.json truncation
  // (2026-07-18 ×2: external tool wiped hooks block, then left trailing comma = invalid JSON)
  let hookWarn = '';
  try {
    const sp = path.join(process.env.USERPROFILE || 'C:/Users/shiniyaya', '.claude', 'settings.json');
    let st = '';
    try { st = fs.readFileSync(sp, 'utf8'); } catch (e) {
      hookWarn = '⚠ settings.json MISSING/unreadable (' + (e.code || 'error') + ') — all hooks offline; restore from settings.json.full-bak.';
    }
    if (!hookWarn) {
      if (!st.trim()) {
        hookWarn = '⚠ settings.json EMPTY (truncated to 0 bytes?) — CC rejects it, hooks offline; restore from settings.json.full-bak.';
      } else {
        try { JSON.parse(st); } catch (e) {
          hookWarn = '⚠ settings.json UNPARSEABLE (invalid JSON) — CC rejects whole file, hooks/env/threshold offline; fix syntax, compare settings.json.full-bak.';
        }
      }
      if (!hookWarn) {
        const missing = ['echo-guard.js', 'stop-guard.js'].filter(h => !st.includes(h));
        if (missing.length) hookWarn = '⚠ HOOK REGISTRATION LOST: ' + missing.join(', ') + ' absent from settings.json — restore from settings.json.full-bak before continuing.';
      }
    }
  } catch (e) {}

  process.stdout.write([
    hookWarn,
    next,
    stateJson,
    `[BEARINGS] cwd=${cwd} | memory files=${memCount}`,
    `snapshots (latest last): ${snaps.slice(-3).join(', ') || 'none'}`,
    `git HEAD:\n${git(cwd, ['log', '--oneline', '-5'])}`,
    `git status: ${git(cwd, ['status', '--short']) || 'clean'}`,
    `CHANGELOG head:\n${chlog}`,
    'recovery: user sends "继" → read latest snapshot → step 7 (cross-compare snapshot version vs git HEAD above) → continue',
    // Step 8 (v4.7.8): recover background agent results that arrived after last snapshot.
    // v4.7.9-r8 (Scan 10 P0): CC writes journals to ~/.claude/projects/{pd}/{uuid}/subagents/workflows/wf_*/,
    // NOT flat under projects/{pd}/subagents/ — there is an extra UUID layer between project dir and subagents.
    // Original r6 fix assumed flat structure and found 0 journals on disk (L127 always false → '').
    // v4.7.9-r9 (Scan 12 P1): filter to current project only — cwd encodes to project-dir naming convention.
    // Global scan would inject other projects' journal data, violating Step 8 recovery semantics.
    (() => {
      try {
        const home = process.env.USERPROFILE || 'C:/Users/shiniyaya';
        const projDir = path.join(home, '.claude', 'projects');
        if (!fs.existsSync(projDir)) return '';
        // Encode cwd to match CC project-dir naming: C:\Users\...\code-shiniyaya → C--Users-...-code-shiniyaya
        const cwdEncoded = (cwd || process.cwd()).replace(/^([A-Z]):/, '$1').replace(/[\\:]/g, '-').replace(/^([A-Z])-/, '$1--');
        const entries = [];
        for (const pd of fs.readdirSync(projDir)) {
          // Only scan the project directory matching current cwd (v3.0-r9)
          if (pd !== cwdEncoded) continue;
          const pdPath = path.join(projDir, pd);
          for (const uuid of fs.readdirSync(pdPath)) {
            const wfDir = path.join(pdPath, uuid, 'subagents', 'workflows');
            if (!fs.existsSync(wfDir)) continue;
            for (const wf of fs.readdirSync(wfDir)) {
              const jp = path.join(wfDir, wf, 'journal.jsonl');
              try {
                const st = fs.statSync(jp);
                if (st.isFile()) entries.push({ path: jp, mtime: st.mtimeMs });
              } catch (e) {}
            }
          }
        }
        if (!entries.length) return '';
        entries.sort((a, b) => b.mtime - a.mtime);
        const latest = entries[0];
        const lines = fs.readFileSync(latest.path, 'utf8').trim().split('\n');
        const recent = lines.slice(-8).join('\n');
        return 'journal (' + path.basename(path.dirname(latest.path)) + ', mtime ' + new Date(latest.mtime).toISOString() + ', last 8 entries):\n' + (recent || '(empty)');
      } catch (e) { return ''; }
    })()
  ].filter(Boolean).join('\n'));
} catch (e) { /* silent — never block session start */ }

process.exit(0);
