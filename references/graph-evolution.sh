#!/usr/bin/env bash
# graph-evolution.sh — 仓库文件结构演变追踪
# 对比两个git提交之间SKILL.md引用文件的变更
# 用法: bash references/graph-evolution.sh [旧提交] [新提交]
# 默认: HEAD~1..HEAD
# 产出: 报告/graph-evol-{ts}.md

OLD=${1:-HEAD~1}
NEW=${2:-HEAD}
REPO=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FATAL: not in a git repo"; exit 1; }
TS=$(date +%Y%m%d_%H%M%S)
OUTDIR="$REPO/报告"
mkdir -p "$OUTDIR"
REPORT="$OUTDIR/graph-evol-$TS.md"

echo "# 仓库结构演变: $OLD → $NEW" > "$REPORT"
echo "生成时间: $(date)" >> "$REPORT"
echo "" >> "$REPORT"

echo "## 整体变更统计" >> "$REPORT"
echo '```' >> "$REPORT"
git diff --stat "$OLD..$NEW" 2>/dev/null >> "$REPORT"
echo '```' >> "$REPORT"
echo "" >> "$REPORT"

echo "## 新增文件" >> "$REPORT"
echo '```' >> "$REPORT"
git diff --diff-filter=A --name-only "$OLD..$NEW" 2>/dev/null >> "$REPORT"
echo '```' >> "$REPORT"
echo "" >> "$REPORT"

echo "## 删除文件" >> "$REPORT"
echo '```' >> "$REPORT"
git diff --diff-filter=D --name-only "$OLD..$NEW" 2>/dev/null >> "$REPORT"
echo '```' >> "$REPORT"
echo "" >> "$REPORT"

echo "## 引用完整性检查" >> "$REPORT"
MISSING=0
while IFS= read -r ref; do
  f=$(echo "$ref" | grep -oP 'references/[^\s)`]+')
  if [ -n "$f" ] && [ ! -f "$REPO/$f" ]; then
    echo "- MISSING: $f (from: $ref)" >> "$REPORT"
    MISSING=$((MISSING+1))
  fi
done < <(grep -oP '`references/[^`]+`' "$REPO/SKILL.md" 2>/dev/null)
echo "缺失引用数: $MISSING" >> "$REPORT"
echo "" >> "$REPORT"

echo "报告已写入: $REPORT"
echo "Done: $REPORT"
