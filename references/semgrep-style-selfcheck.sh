#!/usr/bin/env bash
# ============================================================================
# semgrep-style-selfcheck.sh — Semgrep 式 Markdown 一致性检测
#
# 把 semgrep 的 pattern/pattern-not/pattern-inside 逻辑移植到 shell+grep，
# 对 .md 文件运行 5 条规则。每条规则独立成函数，返回格式统一。
#
# 用法:
#   ./semgrep-style-selfcheck.sh [--dir <path>] [--file <path>] [--current-version X.Y.Z]
#
# 默认扫描 code-shiniyaya 仓库根目录的所有 .md 文件。
# 退出码: 0 = 全部通过, 1 = 至少一条规则命中
# ============================================================================
set -euo pipefail

# --- 早期路径解析 ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- 颜色/样式 ------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- 状态累加器 ------------------------------------------------------------
TOTAL_FINDINGS=0
declare -a RULE_RESULTS

# --- 默认值 -----------------------------------------------------------------
SCAN_TARGET="$REPO_DIR"
CURRENT_VERSION=""          # 通过 --current-version 指定
SINGLE_FILE=""              # 通过 --file 指定

# --- 帮助 -------------------------------------------------------------------
usage() {
  cat <<EOF
用法: $(basename "$0") [选项]

选项:
  --dir <path>              扫描目录（默认: repo 根目录）
  --file <path>             只扫描单个文件
  --current-version X.Y.Z   声明当前版本号（规则3对比基准）
  -h, --help                显示此帮助

5 条规则:
  1. broken-refs    断裂引用   — 检测 [text](#anchor) 中 anchor 没有对应标题
  2. orphan-paragraphs 孤立段落 — 首个标题前的无主正文（排除 frontmatter）
  3. stale-version  过时版本号 — 文件内出现 != 当前版本的版本号
  4. orphan-refs    孤立引用链接 — [label]: URL 定义了但从未被 [label] 引用
  5. heading-skip   标题层级跳跃 — ### 出现在 # 之后但中间没有 ##

退出码: 0 = 干净, 1 = 至少一条命中
EOF
}

# --- 参数解析 ---------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) shift; SCAN_TARGET="$1";;
    --file) shift; SINGLE_FILE="$1";;
    --current-version) shift; CURRENT_VERSION="$1";;
    -h|--help) usage; exit 0;;
    *) echo "未知参数: $1"; usage; exit 1;;
  esac
  shift
done

# --- 文件列表生成 ----------------------------------------------------------
if [[ -n "$SINGLE_FILE" ]]; then
  if [[ ! -f "$SINGLE_FILE" ]]; then
    echo "错误: 文件不存在 — $SINGLE_FILE" >&2
    exit 1
  fi
  MD_FILES=("$SINGLE_FILE")
elif [[ -d "$SCAN_TARGET" ]]; then
  mapfile -t MD_FILES < <(find "$SCAN_TARGET" -name '*.md' -type f 2>/dev/null | sort)
  if [[ ${#MD_FILES[@]} -eq 0 ]]; then
    echo "错误: 在 $SCAN_TARGET 下未发现 .md 文件" >&2
    exit 1
  fi
else
  echo "错误: 路径不存在 — $SCAN_TARGET" >&2
  exit 1
fi

# ============================================================================
# 工具函数
# ============================================================================

# 从 Markdown 文件中提取标题行并计算其 HTML anchor ID
# 输入: 文件路径
# 输出: "LEVEL:ANCHOR:TITLE" 每行
# 处理规则:
#   - 去除前导 # 和空格得到级别和标题文本
#   - anchor = 小写 + 去除非单词字符(保留中日韩等字母) + 空格转连字符 + 连字符压缩
extract_headings() {
  local file="$1"
  grep -n '^#' "$file" 2>/dev/null | while IFS=: read -r line_no line; do
    # 跳过 frontmatter
    [[ "$line" == '#'* ]] || continue
    local level text anchor
    # 去掉前导 # 和空格
    text="${line##*(#)}"
    text="${text## }"
    # 确定级别（数 # 个数）
    level=$(echo "$line" | grep -o '^#*' | wc -c)
    level=$((level - 1))
    # 生成 anchor: 小写 + 去除非单词字符(保留Unicode字母) + 空格→连字符
    anchor=$(echo "$text" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -e 's/[^a-z0-9一-鿿぀-ゟ゠-ヿ가-힯-]/-/g' \
            -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')
    echo "$level:$anchor:$text"
  done
}

# 提取 frontmatter 结束行号（--- 关闭标签的行号），0 表示无 frontmatter
frontmatter_end() {
  local file="$1"
  # 第一行是 ---，找到第二行 ---
  local first
  first=$(head -1 "$file" 2>/dev/null || true)
  if [[ "$first" == "---" ]]; then
    awk '/^---$/ && ++c==2 {print NR; exit}' "$file"
  else
    echo 0
  fi
}

# 判断是否在代码块/围栏内（简单实现：看行号是否在 ``` 对之间）
# 返回 0 = 在围栏内, 1 = 不在
inside_fence() {
  local file="$1" target_ln="$2"
  local in=1
  while IFS= read -r line; do
    if echo "$line" | grep -qE '^```'; then
      if [[ $in -eq 0 ]]; then in=1; else in=0; fi
    fi
  done < <(head -n "$target_ln" "$file")
  return $in
}

# --- 报告输出 --------------------------------------------------------------
report_rule_header() {
  local num="$1" name="$2" desc="$3"
  printf "${CYAN}${BOLD}[Rule %d | %s]${NC} %s\n" "$num" "$name" "$desc"
}

report_finding() {
  local file="$1" line="$2" msg="$3"
  TOTAL_FINDINGS=$((TOTAL_FINDINGS + 1))
  printf "  ${YELLOW}%s${NC} L${line}: ${RED}%s${NC}\n" "$file" "$msg"
}

report_rule_footer() {
  local count="$1"
  if [[ "$count" -eq 0 ]]; then
    printf "  ${GREEN}✓ 通过${NC}\n\n"
  else
    printf "  ${RED}✗ 命中 %d 个${NC}\n\n" "$count"
  fi
}

# ============================================================================
# 规则 1: 断裂引用 (broken-refs)
# Semgrep 等价:
#   pattern: [text](#anchor)
#   pattern-not: anchor 在 extract_headings 能找到
# ============================================================================
rule_broken_refs() {
  local files=("$@")
  local count=0

  for f in "${files[@]}"; do
    # 收集本文件标题 anchor
    local -A anchors
    while IFS=: read -r lvl anc title; do
      [[ -z "$anc" ]] || anchors["$anc"]=1
    done < <(extract_headings "$f")

    # 查找 [text](#xxx) 模式，提取 anchor
    grep -noE '\[([^]]*)\]\(#([^)]+)\)' "$f" 2>/dev/null | while IFS=: read -r line_no rest; do
      # 跳过围栏内
      inside_fence "$f" "$line_no" && continue

      local text anchor
      anchor=$(echo "$rest" | sed -nE 's/\[([^]]*)\]\(#([^)]+)\)/\2/p')
      local refline
      refline=$(echo "$rest" | sed -nE 's/\[([^]]*)\]\(#([^)]+)\)/\1/p')

      # 处理不了空 anchor
      [[ -z "$anchor" ]] && continue

      # 匹配：grep 找到的 anchor 可能在 Markdown 渲染时有字符差异
      # 统一小写+连字符化再匹配
      local normalized
      normalized=$(echo "$anchor" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9一-鿿぀-ゟ゠-ヿ가-힯-]/-/g' \
              -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')

      if [[ -z "${anchors[$normalized]:-}" ]] && [[ -z "${anchors[$anchor]:-}" ]]; then
        report_finding "$f" "$line_no" "断裂引用: [${refline}](#${anchor}) — 无匹配标题 '${normalized}'"
        # 使用文件描述符绕过管道 subshell 问题
        echo "." >> "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
      fi
    done
  done

  # 通过临时文件计数
  if [[ -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp" ]]; then
    count=$(wc -l < "$SCRIPT_DIR/.semgrep_selfcheck_tmp")
    rm -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
  fi
  report_rule_footer "$count"
  RULE_RESULTS[0]=$count
}

# ============================================================================
# 规则 2: 孤立段落 (orphan-paragraphs)
# Semgrep 等价:
#   pattern: ^\S 开头内容行（非 frontmatter，非空行，非标题）
#   pattern-not-inside: ^# 标题之后
# ============================================================================
rule_orphan_paragraphs() {
  local files=("$@")
  local count=0

  for f in "${files[@]}"; do
    # 找到 frontmatter 结束
    local fm_end
    fm_end=$(frontmatter_end "$f")

    # 找第一个 # 标题（非 frontmatter）
    local first_heading=999999
    while IFS=: read -r ln lvl anc title; do
      if [[ "$ln" -gt "$fm_end" ]]; then
        first_heading=$ln
        break
      fi
    done < <(grep -n '^#' "$f" 2>/dev/null || true)

    # 如果没有标题则跳过（可能是纯 frontmatter 或不属于正文规则）
    [[ "$first_heading" -eq 999999 ]] && continue

    # 检查 frontmatter 结束之后、第一个标题之前的内容行
    local start=$((fm_end + 1))
    local end=$((first_heading - 1))
    [[ "$start" -ge "$end" ]] && continue

    # 读取这些行，找非空行
    sed -n "${start},${end}p" "$f" 2>/dev/null | while IFS= read -r line; do
      # 空行或纯空白跳过
      [[ -z "${line// }" ]] && continue
      # 围栏结束标记不算
      echo "$line" | grep -qE '^```' && continue
      # 这是孤立内容行
      report_finding "$f" "$((start + ${LINENO:-0} - 1))" "孤立段落: 在第一个标题前出现未归属文本"
      echo "." >> "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
    done
  done

  if [[ -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp" ]]; then
    count=$(wc -l < "$SCRIPT_DIR/.semgrep_selfcheck_tmp")
    rm -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
  fi
  report_rule_footer "$count"
  RULE_RESULTS[1]=$count
}

# ============================================================================
# 规则 3: 过时版本号 (stale-version)
# Semgrep 等价:
#   pattern: vX.Y.Z
#   pattern-not: v${CURRENT_VERSION}
#   上下文: 只在正文中匹配，yaml frontmatter 中的 version 字段跳过
# ============================================================================
rule_stale_version() {
  local files=("$@")
  local count=0

  if [[ -z "$CURRENT_VERSION" ]]; then
    echo "  ${YELLOW}跳过: 未指定 --current-version${NC}"
    echo
    return
  fi

  local escaped_current
  escaped_current=$(echo "$CURRENT_VERSION" | sed 's/\./\\./g')

  for f in "${files[@]}"; do
    local fm_end
    fm_end=$(frontmatter_end "$f")

    grep -noE '[vV][0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.-]*' "$f" 2>/dev/null \
      | while IFS=: read -r line_no ver_str; do
        # 跳过 frontmatter
        [[ "$line_no" -le "$fm_end" ]] && continue
        # 跳过围栏内
        inside_fence "$f" "$line_no" && continue

        # 提取纯版本号
        local version
        version=$(echo "$ver_str" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.-]*' | head -1)

        # 如果与当前版本一致则跳过
        if echo "$version" | grep -qE "^${escaped_current}([^0-9]|$)"; then
          continue
        fi

        report_finding "$f" "$line_no" "过时版本: 引用 '$ver_str' (当前版本: v${CURRENT_VERSION})"
        echo "." >> "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
      done
  done

  if [[ -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp" ]]; then
    count=$(wc -l < "$SCRIPT_DIR/.semgrep_selfcheck_tmp")
    rm -f "$SCRIPT_DIR/.semgrep_selfcheck_tmp"
  fi
  report_rule_footer "$count"
  RULE_RESULTS[2]=$count
}

# ============================================================================
# 规则 4: 孤立引用链接 (orphan-refs)
# Semgrep 等价:
#   pattern: ^[label]:\s+url$
#   pattern-not: 正文中出现 [label]
# ============================================================================
rule_orphan_refs() {
  local files=("$@")
  local count=0

  for f in "${files[@]}"; do
    local fm_end
    fm_end=$(frontmatter_end "$f")

    # 提取所有引用链接定义 [label]: URL
    # 忽略 frontmatter 和围栏内
    local -A refs_defined
    local -A refs_lines
    while IFS=: read -r ln rest; do
      [[ "$ln" -le "$fm_end" ]] && continue
      inside_fence "$f" "$ln" && continue
      local label
      label=$(echo "$rest" | sed -nE 's/^\[([^]]+)\]:\s*//p' | head -1)
      [[ -z "$label" ]] && continue
      refs_defined["$label"]=1
      refs_lines["$label"]=$ln
    done < <(grep -nE '^\[[^]]+\]:\s+' "$f" 2>/dev/null || true)

    [[ ${#refs_defined[@]} -eq 0 ]] && continue

    # 检查每个定义是否在正文中被引用
    for label in "${!refs_defined[@]}"; do
      # 在正文中搜索 [label] 但不包括 [label]: 定义行
      if ! grep -qE "\[${label}\]" "$f" 2>/dev/null; then
        report_finding "$f" "${refs_lines[$label]}" "孤立引用链接: [${label}]: 定义了 URL 但正文从未引用"
        count=$((count + 1))
      fi
    done
  done

  report_rule_footer "$count"
  RULE_RESULTS[3]=$count
}

# ============================================================================
# 规则 5: 标题层级跳跃 (heading-skip)
# Semgrep 等价:
#   pattern: ^### (level-N heading)
#   pattern-where-python: 前面的标题层级 != N-1
# ============================================================================
rule_heading_skip() {
  local files=("$@")
  local count=0

  for f in "${files[@]}"; do
    local fm_end
    fm_end=$(frontmatter_end "$f")
    local prev_level=0

    while IFS=: read -r ln line; do
      [[ "$ln" -le "$fm_end" ]] && continue
      inside_fence "$f" "$ln" && continue

      # 提取级别
      local level text
      level=$(echo "$line" | grep -o '^#*' | wc -c)
      level=$((level - 1))
      text="${line##*(#)}"
      text="${text## }"

      # level-1 标题重置 prev_level
      if [[ "$level" -eq 1 ]]; then
        prev_level=1
        continue
      fi

      # 检查跳跃: 当前级别 > 前一个级别 + 1
      if [[ "$level" -gt $((prev_level + 1)) ]] && [[ "$prev_level" -ge 1 ]]; then
        # 特殊情况: 如果是文件第一个非 level-1 标题，且 prev_level=0，不报
        # prev_level >= 1 时才认为跳跃
        local prev_display
        case "$prev_level" in
          1) prev_display="h1 (#)" ;;
          2) prev_display="h2 (##)" ;;
          3) prev_display="h3 (###)" ;;
          4) prev_display="h4 (####)" ;;
          *) prev_display="h${prev_level}" ;;
        esac
        local curr_display
        case "$level" in
          1) curr_display="h1 (#)" ;;
          2) curr_display="h2 (##)" ;;
          3) curr_display="h3 (###)" ;;
          4) curr_display="h4 (####)" ;;
          *) curr_display="h${level}" ;;
        esac
        report_finding "$f" "$ln" "标题层级跳跃: '${text}' 为 ${curr_display}，但前一个标题为 ${prev_display}"
        count=$((count + 1))
      fi

      prev_level=$level
    done < <(grep -n '^#' "$f" 2>/dev/null || true)
  done

  report_rule_footer "$count"
  RULE_RESULTS[4]=$count
}

# ============================================================================
# 主流程
# ============================================================================
main() {
  echo ""
  printf "${BOLD}📋 semgrep-style-selfcheck.sh — Markdown 一致性检测${NC}\n"
  printf "目标: %s\n" "$SCAN_TARGET"
  printf "文件数: ${#MD_FILES[@]} 个 .md\n"
  [[ -n "$CURRENT_VERSION" ]] && printf "当前版本: v%s\n" "$CURRENT_VERSION"
  echo "────────────────────────────────────────────────────"
  echo ""

  # --- 规则 1: 断裂引用 ---
  report_rule_header 1 "broken-refs" "检测 [text](#anchor) 中 anchor 无对应标题"
  rule_broken_refs "${MD_FILES[@]}"

  # --- 规则 2: 孤立段落 ---
  report_rule_header 2 "orphan-paragraphs" "首个标题前出现的无主正文"
  rule_orphan_paragraphs "${MD_FILES[@]}"

  # --- 规则 3: 过时版本号 ---
  report_rule_header 3 "stale-version" "文件内 != 当前版本的版本号"
  rule_stale_version "${MD_FILES[@]}"

  # --- 规则 4: 孤立引用链接 ---
  report_rule_header 4 "orphan-refs" "[label]: URL 定义了但从未被引用"
  rule_orphan_refs "${MD_FILES[@]}"

  # --- 规则 5: 标题层级跳跃 ---
  report_rule_header 5 "heading-skip" "标题级别跳过中间层级 (如 # → ###)"
  rule_heading_skip "${MD_FILES[@]}"

  # --- 汇总 ---
  echo "────────────────────────────────────────────────────"
  if [[ "$TOTAL_FINDINGS" -eq 0 ]]; then
    printf "🟢 ${GREEN}${BOLD}全部通过${NC} — 0 个命中\n"
    exit 0
  else
    printf "🔴 ${RED}${BOLD}检测完成${NC} — 总计 ${TOTAL_FINDINGS} 个命中\n"
    printf "  规则1(broken-refs):      %d\n" "${RULE_RESULTS[0]:-0}"
    printf "  规则2(orphan-paragraphs): %d\n" "${RULE_RESULTS[1]:-0}"
    printf "  规则3(stale-version):    %d\n" "${RULE_RESULTS[2]:-0}"
    printf "  规则4(orphan-refs):      %d\n" "${RULE_RESULTS[3]:-0}"
    printf "  规则5(heading-skip):     %d\n" "${RULE_RESULTS[4]:-0}"
    exit 1
  fi
}

main "$@"
