#!/usr/bin/env bash
# =============================================================================
# diagnose.sh — code-shiniyaya Git Bisect Automation + Performance Profiling
# =============================================================================
# Fills the gap: systematic-debugging skill's STEP 2 (6+Agent deep diagnosis)
# is covered, but git bisect automation + performance profiling were missing.
#
# Usage:
#   bash references/diagnose.sh [command] [options]
#
# Commands:
#   bisect <good-commit>         — Bisect to find the commit that broke hooks
#   bisect:guard                 — Bisect to find what broke echo-guard/stop-guard/bearings
#   profile:cc                   — Profile Claude Code command execution time
#   profile:hooks                — Profile hooks execution time (echo-guard, stop-guard)
#   profile:all                  — Run all profiles and produce a summary
#   survey                       — Quick system survey (disk, load, git state)
#   help                         — Show this help
#
# Output:
#   All results go to references/diagnose-out/ with timestamps
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${SCRIPT_DIR}/diagnose-out"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
mkdir -p "${OUT_DIR}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
pass()  { echo -e "${GREEN}[PASS]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
header(){ echo -e "\n${BLUE}==== $1 ====${NC}"; }

# =============================================================================
# SECTION 1: Git Bisect Automation
# =============================================================================

# ---- Test function for hook integrity ----
# Return 0 = good (bug NOT present), 1-124 = bad (bug IS present), 125 = skip
bisect_test_hooks() {
    local hooks_dir="${PROJECT_DIR}/hooks"
    local ret=0

    # 1: File existence
    for f in echo-guard.js stop-guard.js bearings.js; do
        if [[ ! -f "${hooks_dir}/${f}" ]]; then
            echo "[bisect] MISSING: ${f}"
            ret=1
        fi
    done

    # 2: Syntax check (Node.js available?)
    if command -v node &>/dev/null; then
        for f in echo-guard.js stop-guard.js bearings.js; do
            local fpath="${hooks_dir}/${f}"
            if [[ -f "${fpath}" ]]; then
                if ! node --check "${fpath}" 2>/dev/null; then
                    echo "[bisect] SYNTAX ERROR: ${f}"
                    ret=1
                fi
            fi
        done
    else
        echo "[bisect] WARN: node not available, skip syntax check"
    fi

    # 3: Version string consistency (echo-guard vX.Y present)
    if [[ -f "${hooks_dir}/echo-guard.js" ]]; then
        if grep -q 'echo-guard v[0-9]' "${hooks_dir}/echo-guard.js" 2>/dev/null; then
            echo "[bisect] echo-guard version header found"
        else
            echo "[bisect] MISSING: echo-guard version header"
            ret=1
        fi
    fi

    if [[ $ret -eq 0 ]]; then
        echo "[bisect] All hooks check PASSED — GOOD"
    else
        echo "[bisect] Hooks check FAILED — BAD"
    fi
    return $ret
}

# ---- Test function for SKILL.md integrity ----
bisect_test_skill() {
    local skill_file="${PROJECT_DIR}/SKILL.md"
    local ret=0

    if [[ ! -f "${skill_file}" ]]; then
        echo "[bisect] SKILL.md missing"
        return 125  # skip — repo structure changed
    fi

    # Must have proper frontmatter
    if head -1 "${skill_file}" | grep -q '^---$'; then
        echo "[bisect] SKILL.md frontmatter OK"
    else
        echo "[bisect] SKILL.md missing frontmatter"
        ret=1
    fi

    # Must have a reasonable size (>10KB means it's not an empty stub)
    local size
    size=$(stat -c%s "${skill_file}" 2>/dev/null || stat -f%z "${skill_file}" 2>/dev/null || echo "0")
    if [[ $size -gt 10240 ]]; then
        echo "[bisect] SKILL.md size OK (${size} bytes)"
    else
        echo "[bisect] SKILL.md too small (${size} bytes)"
        ret=1
    fi

    # References should exist
    if [[ -d "${PROJECT_DIR}/references" ]] && ls "${PROJECT_DIR}/references/"*.sh &>/dev/null 2>&1; then
        echo "[bisect] references/scripts present"
    else
        echo "[bisect] references/ missing scripts"
        warn "[bisect] (non-fatal: may predate references/ structure)"
    fi

    return $ret
}

# ---- Main bisect command ----
cmd_bisect() {
    local good_commit="${1:-}"
    if [[ -z "${good_commit}" ]]; then
        fail "Usage: bash references/diagnose.sh bisect <good-commit>"
        fail "  Example: bash references/diagnose.sh bisect HEAD~10"
        exit 1
    fi

    header "Git Bisect: hooks integrity"
    info "Good commit: ${good_commit}"
    info "Bad commit:  HEAD (current)"
    echo ""

    # Save the test function to a temp script for git bisect run
    local bisect_script="${OUT_DIR}/bisect-runner-${TIMESTAMP}.sh"
    cat > "${bisect_script}" << 'BISECTSCRIPT'
#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${PROJECT_DIR}"

# Determine which test to run from environment
TEST_MODE="${BISECT_TEST_MODE:-hooks}"

# Re-install hooks if they exist (commit may have changed them)
if [[ -f "${PROJECT_DIR}/hooks/echo-guard.js" ]]; then
    # Just check syntax — don't actually install to avoid side effects
    :
fi

case "${TEST_MODE}" in
    hooks)
        # Test hook files
        for f in hooks/echo-guard.js hooks/stop-guard.js hooks/bearings.js; do
            if [[ ! -f "${PROJECT_DIR}/${f}" ]]; then
                echo "[bisect] MISSING: ${f}"
                exit 1
            fi
            if command -v node &>/dev/null; then
                if ! node --check "${PROJECT_DIR}/${f}" 2>/dev/null; then
                    echo "[bisect] SYNTAX ERROR: ${f}"
                    exit 1
                fi
            fi
        done
        echo "[bisect] All hooks OK"
        exit 0
        ;;
    skill)
        # Test SKILL.md exists and has content
        if [[ ! -f "${PROJECT_DIR}/SKILL.md" ]]; then
            echo "[bisect] SKILL.md missing"
            exit 125
        fi
        local size
        size=$(stat -c%s "${PROJECT_DIR}/SKILL.md" 2>/dev/null || stat -f%z "${PROJECT_DIR}/SKILL.md" 2>/dev/null || echo "0")
        if [[ $size -lt 1024 ]]; then
            echo "[bisect] SKILL.md too small: ${size}"
            exit 1
        fi
        echo "[bisect] SKILL.md OK (${size} bytes)"
        exit 0
        ;;
    *)
        echo "[bisect] Unknown test mode: ${TEST_MODE}"
        exit 125
        ;;
esac
BISECTSCRIPT
    chmod +x "${bisect_script}"

    echo ""
    info "To start bisect, run these commands:"
    echo ""
    echo "  cd ${PROJECT_DIR}"
    echo "  git bisect start HEAD ${good_commit}"
    echo "  BISECT_TEST_MODE=hooks git bisect run ${bisect_script}"
    echo ""
    echo "  # After bisect finishes:"
    echo "  git bisect reset"
    echo ""
    echo "Log: ${OUT_DIR}/bisect-${TIMESTAMP}.log"
    echo ""
    echo "Available test modes (set via BISECT_TEST_MODE env):"
    echo "  hooks  — Test hook files existence + syntax (default)"
    echo "  skill  — Test SKILL.md existence + size"
    echo ""

    # Offer to run it directly
    warn "Not running bisect automatically — confirm intent first."
}

# ---- Bisect specifically for guard files ----
cmd_bisect_guard() {
    header "Git Bisect: Guard files (echo-guard / stop-guard / bearings)"
    info "Finding the commit that broke guard file integrity..."

    # Find the last known good commit for guard files using git log
    echo ""
    echo "Recent commits touching hooks/:"
    echo ""
    git -C "${PROJECT_DIR}" log --oneline -20 -- hooks/ 2>/dev/null || \
        echo "(no hooks/ history — may be new repo)"
    echo ""
    echo "To bisect guard regressions:"
    echo ""
    echo "  cd ${PROJECT_DIR}"
    echo "  git bisect start HEAD <known-good-commit>"
    echo "  BISECT_TEST_MODE=hooks git bisect run ${OUT_DIR}/bisect-runner-*.sh"
    echo "  git bisect reset"
    echo ""
}

# =============================================================================
# SECTION 2: Performance Profiling
# =============================================================================

# ---- Profile CC command execution ----
cmd_profile_cc() {
    header "Profile: Claude Code Command Time"

    local logfile="${OUT_DIR}/profile-cc-${TIMESTAMP}.log"
    > "${logfile}"

    echo "Command,Real,User,Sys" >> "${logfile}"

    # Test 1: CC --help (cold start measurement)
    info "1/5: cc --help (cold start)..."
    if command -v cc &>/dev/null; then
        /usr/bin/time -f "cc --help,%e,%U,%S" -a -o "${logfile}" cc --help 2>&1 >/dev/null || true
    elif command -v claude &>/dev/null; then
        /usr/bin/time -f "claude --help,%e,%U,%S" -a -o "${logfile}" claude --help 2>&1 >/dev/null || true
    else
        warn "Neither cc nor claude found — skip"
    fi

    # Test 2: Git status (repo baseline)
    info "2/5: git status..."
    /usr/bin/time -f "git status,%e,%U,%S" -a -o "${logfile}" git -C "${PROJECT_DIR}" status 2>&1 >/dev/null

    # Test 3: Git diff (file-level)
    info "3/5: git diff..."
    /usr/bin/time -f "git diff,%e,%U,%S" -a -o "${logfile}" git -C "${PROJECT_DIR}" diff 2>&1 >/dev/null

    # Test 4: Hooks count
    info "4/5: hooks file list..."
    /usr/bin/time -f "ls hooks,%e,%U,%S" -a -o "${logfile}" ls -la "${PROJECT_DIR}/hooks/" 2>&1 >/dev/null

    # Test 5: SKILL.md read (large file baseline)
    info "5/5: read SKILL.md (head -50)..."
    /usr/bin/time -f "read SKILL.md(50),%e,%U,%S" -a -o "${logfile}" head -50 "${PROJECT_DIR}/SKILL.md" 2>&1 >/dev/null

    echo ""
    echo "Results (seconds):"
    echo "────────────────────────────────────────────────"
    column -t -s',' "${logfile}" 2>/dev/null || cat "${logfile}"
    echo "────────────────────────────────────────────────"
    echo "Log: ${logfile}"
}

# ---- Profile hooks execution time ----
cmd_profile_hooks() {
    header "Profile: Hooks Execution Time"

    local logfile="${OUT_DIR}/profile-hooks-${TIMESTAMP}.log"
    > "${logfile}"

    echo "Hook,Iteration,Real,Exit" >> "${logfile}"

    for hook in echo-guard.js stop-guard.js bearings.js; do
        local hookpath="${PROJECT_DIR}/hooks/${hook}"
        if [[ ! -f "${hookpath}" ]]; then
            warn "Hook not found: ${hook}"
            continue
        fi

        info "Profiling ${hook} (3 iterations)..."
        for i in 1 2 3; do
            # Run via node with a dry input (stdin with empty command)
            local timing
            timing=$(/usr/bin/time -f "%e" bash -c "echo '' | node '${hookpath}' 2>/dev/null" 2>&1 || true)
            local real_time
            real_time=$(echo "${timing}" | tail -1)
            local exit_code=$?
            echo "${hook},${i},${real_time},${exit_code}" >> "${logfile}"
        done
    done

    echo ""
    echo "Results (seconds):"
    echo "────────────────────────────────────────────────"
    column -t -s',' "${logfile}" 2>/dev/null || cat "${logfile}"
    echo "────────────────────────────────────────────────"
    echo "Log: ${logfile}"
}

# ---- Profile everything ----
cmd_profile_all() {
    header "Full Performance Profile"

    cmd_profile_cc
    echo ""
    cmd_profile_hooks

    # Summary
    echo ""
    header "Profile Summary"
    echo "Output directory: ${OUT_DIR}"
    echo "Profile files:"
    ls -lh "${OUT_DIR}"/profile-*-"${TIMESTAMP}".log 2>/dev/null || echo "(none)"
    echo ""
    pass "Profiling complete"
}

# =============================================================================
# SECTION 3: Quick System Survey
# =============================================================================

cmd_survey() {
    header "code-shiniyaya System Survey"

    # Git state
    echo ""
    info "Git state:"
    git -C "${PROJECT_DIR}" log --oneline -3 2>/dev/null || echo "(no git history)"
    git -C "${PROJECT_DIR}" status --short 2>/dev/null | head -10 || true

    # Repository size
    echo ""
    info "Repository size:"
    du -sh "${PROJECT_DIR}" 2>/dev/null || echo "(du not available)"
    echo "  Files: $(find "${PROJECT_DIR}" -type f -not -path '*/.git/*' 2>/dev/null | wc -l)"
    echo "  Dirs:  $(find "${PROJECT_DIR}" -type d -not -path '*/.git/*' 2>/dev/null | wc -l)"

    # Hooks info
    echo ""
    info "Hooks:"
    for f in echo-guard.js stop-guard.js bearings.js; do
        local fpath="${PROJECT_DIR}/hooks/${f}"
        if [[ -f "${fpath}" ]]; then
            local lines
            lines=$(wc -l < "${fpath}")
            echo "  ${f}: ${lines} lines"
        else
            echo "  ${f}: MISSING"
        fi
    done

    # SKILL.md
    echo ""
    info "SKILL.md:"
    if [[ -f "${PROJECT_DIR}/SKILL.md" ]]; then
        local skill_lines skill_size
        skill_lines=$(wc -l < "${PROJECT_DIR}/SKILL.md")
        skill_size=$(stat -c%s "${PROJECT_DIR}/SKILL.md" 2>/dev/null || stat -f%z "${PROJECT_DIR}/SKILL.md" 2>/dev/null || echo "?")
        echo "  Lines: ${skill_lines}, Size: ${skill_size} bytes"
    else
        echo "  MISSING"
    fi

    # References
    echo ""
    info "References:"
    echo "  Scripts: $(ls "${PROJECT_DIR}/references/"*.sh 2>/dev/null | wc -l)"
    echo "  Files:   $(ls "${PROJECT_DIR}/references/"* 2>/dev/null | wc -l)"

    # System resources
    echo ""
    info "System resources:"
    if command -v free &>/dev/null; then
        free -h 2>/dev/null | head -2 || true
    fi
    if command -v uptime &>/dev/null; then
        uptime
    fi
    if command -v df &>/dev/null; then
        df -h "${PROJECT_DIR}" 2>/dev/null | tail -1 || true
    fi

    echo ""
    pass "Survey complete — see above"
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    local cmd="${1:-help}"
    shift 2>/dev/null || true

    case "${cmd}" in
        bisect)
            cmd_bisect "${@}"
            ;;
        bisect:guard)
            cmd_bisect_guard
            ;;
        profile:cc)
            cmd_profile_cc
            ;;
        profile:hooks)
            cmd_profile_hooks
            ;;
        profile:all)
            cmd_profile_all
            ;;
        survey)
            cmd_survey
            ;;
        help|--help|-h)
            header "diagnose.sh — code-shiniyaya Debug Automation"
            echo ""
            echo "  Fill the gap between diagnosing-bugs STEP 2 (agent diagnosis)"
            echo "  and the missing git bisect automation + performance profiling."
            echo ""
            echo "  Commands:"
            echo "    bisect <good-commit>       Bisect hooks/SKILL integrity"
            echo "    bisect:guard                Bisect specifically for guard files"
            echo "    profile:cc                  Measure CC/git/filesystem times"
            echo "    profile:hooks               Measure hook execution times"
            echo "    profile:all                 Run all profiles"
            echo "    survey                      Quick system survey"
            echo "    help                        This help"
            echo ""
            echo "  Output dir: ${OUT_DIR}"
            echo ""
            ;;
        *)
            fail "Unknown command: ${cmd}"
            echo "Try: bash references/diagnose.sh help"
            exit 1
            ;;
    esac
}

main "$@"
