#!/usr/bin/env bash
# variant-analysis.sh — 检测SKILL.md版本历史中的规则漂移
# 用法: ./variant-analysis.sh [<从提交> <到提交>]
# 默认: HEAD~1..HEAD (最近一次变更)

set -euo pipefail

FROM="${1:-HEAD~1}"
TO="${2:-HEAD}"
FILE="SKILL.md"

echo "=== 版本漂移分析: $FROM → $TO ==="

# --- 规则/版本号提取与比对 ---
extract_versions() {
    local ref="$1"
    echo "--- [$ref] 规则/版本/计数快照 ---"
    git show "$ref:$FILE" 2>/dev/null | grep -oP '(规则\d+|自检#\d+|v\d+\.\d+\.\d+(-r\d[\dp]*)?|hooks\.test.*\d+/\d+)' | sort | uniq -c | sort -rn
}

echo ""
extract_versions "$FROM"
echo ""
extract_versions "$TO"

# --- diff中版本号变更行 ---
echo ""
echo "--- 版本号漂排行 (grep: v/d+ → v/d+, 规则X, 自检#X) ---"
git diff "$FROM..$TO" -- "$FILE" 2>/dev/null \
    | grep -E '^[+-].*(规则\d+|自检#\d+|v\d+\.\d+)' \
    | head -40

# --- 交叉引用行号偏移(LXXX) ---
echo ""
echo "--- 行号引用偏移(LXXX) ---"
git diff "$FROM..$TO" -- "$FILE" 2>/dev/null \
    | grep -E '^[+-].*L[0-9]{3,4}' \
    | head -20

# --- 关键计数一致性(规则总数/自检总数/hooks.test) ---
echo ""
echo "--- 关键计数声明 ---"
for ref in "$FROM" "$TO"; do
    echo "[$ref]"
    git show "$ref:$FILE" 2>/dev/null \
        | grep -oP '\d+条硬规则|\d+项自检|hooks\.test.*\d+' \
        | sort | uniq
done

echo ""
echo "=== 结论: diff中标记+-的行为潜在漂移点 ==="
