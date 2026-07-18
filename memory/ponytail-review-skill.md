# ponytail-review: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md

## delete (YAGNI — remove entirely)

1. **L1236-1330 (v4.5.1-v4.5.2 自主编码Agent完整管线)**: ~95 lines of spec-level extractions from autonomous-coding. All marked ponytail:debt as not runtime-integrated. Historical changelog, no active workflow impact. Delete; already captured in memory/ reference files.

2. **L1588-1649 (v4.6.11 5源深度扫描 45项新发现 + v4.6.12 全量审计总结)**: ~60 lines declaring "5源已穷尽...零可提取自动化模式残留." Purely historical audit documentation. Delete; conclusion already stated in L1272.

3. **L1274-1285 (基准测试10条黄金原则)**: 10 principles extracted from AutoAgent/evaluation/. Informative but unused in active workflow. Delete; if needed, move to memory/reference-sources-v2.md.

4. **L1178-1182 (DO/DON'T)**: 5-line summary of 28 rules already fully specified above. Duplicate. Delete.

5. **L1637-1649 (v4.6.12 5源全量审计总结 table)**: Coverage table (AutoAgent ~54/196, etc.). Historical. Delete; numbers serve no active purpose.

6. **L1333-1335 (v4.6.0 第5源 intro paragraph)**: "ponytail is an AI Agent skill..." — marketing copy for a sub-skill, not an instruction. Delete.

## stdlib (reinvents what already exists)

7. **L604-609 (原子写入协议 steps 1-5)**: Manual tmp+rename+fsync+checksum protocol. Python `tempfile.NamedTemporaryFile` + `os.replace` already handles this. Shrink to: "Use atomic write (tmpfile + os.replace)."

8. **L1078-1111 (truncate_for_prompt + paginate_large_output)**: 34 lines of Python with three functions for text truncation. Python's `textwrap.shorten` covers the common case. Delete inline code; reference `textwrap` module.

9. **L1289 (内容寻址延迟向量索引)**: "Codebase zip -> MD5 hash -> collection name with hash -> if count()==0 index only first time." This is `hashlib.md5()` + a cache check — 3 lines of Python, not a pattern needing documentation.

## yagni (over-engineered — question whether this needs to exist at all)

10. **L1031-1063 (工作流上下文总线 + CTX_UPDATE 安全防护)**: A state dict with 5 sections, injection rules, 5 Byzantine-security validation rules (whitelist fields, format anchoring, value validation, dedup, audit logging). For what is: "pass a dict to the next agent." Over-engineered. Replace with: one JSON blob, no CTX_UPDATE parsing.

11. **L1004-1030 (Agent终端信号协议)**: Three competing signal mechanisms (typed returns > tool calls > TERMINAL text lines) with priority chains, conflict resolution, and a "Single Source of Truth principle." The actual need: agent says "done" or "not done." Shrink to one mechanism.

12. **L1065-1112 (STEP 4 输入上限)**: Formal truncation system with 5 configurable limits, severity-sorting, 60/40 head-tail split, file-overflow fallback, AND three-function pagination system. Actual need: "keep prompts under context limit." Replace with a single `if len(text) > N: text = text[:N]`.

13. **L1439-1475 (三元件裁判框架 + 双轴评分 + 完整性pass + 12机制全量落地)**: Benchmark judgment system imported from ponytail's judge.py — selftest, dual-layer offline+live, rubric, good/bad reference anchors, completeness pass, 12 feedback mechanisms. This judges whether code is over-engineered, but the judgment system itself is 120+ lines. Meta-over-engineering. Replace with: "Does it work? Is it safe? Ship it."

14. **L443-448 (规则26 无意义输出循环阻断)**: 6 sub-rules (a-e) with per-tool-call blocking logic, call-stack caching, cross-turn hash comparison, and a "阻断结果" block. The echo-guard.js hook already blocks these at the platform layer. Delete the model-side duplicate; keep one-line reference to the hook.

15. **L940-998 (Agent Safety — Three-Layer Defense)**: Sandbox + Permissions + Bash Allowlist with compound-command defense, per-segment validation, dangerous-parameter interception. The platform sandbox and echo-guard hook already handle this. Delete; replace with "Trust platform sandbox + echo-guard.js hook."

## shrink (keep but drastically reduce)

16. **L383-496 (26条硬规则)**: 114 lines for 26 rules, many of which are the same concept restated (don't skip verification, don't batch without checking, don't silently fail). Collapse to 10-12 core rules.

17. **L530-573 (错误处理 table)**: 44 rows covering every possible failure mode. Most failures share recovery patterns (retry -> skip -> escalate). Collapse to 8-10 recovery pattern categories.

18. **L500-528 (反模式 24个)**: 24 anti-patterns when ~18 are duplicates of the 26 rules above. Merge with rules; keep only unique anti-patterns.

19. **L1544-1556 (机制可行性矩阵)**: 10-row table documenting which mechanisms DON'T work. Replace with a 3-line summary: "X, Y, Z are not feasible due to CC architecture limits."

20. **L1572-1586 (10项源文件功能表)**: 10 features all marked "spec-level, not runtime." If none are runtime, collapse to one sentence.

21. **L1592-1598 (跨源共性主题)**: 5 themes listed as "cross-source common themes." Informative but not actionable. Delete; or move to memory/.

## P0 bugs discovered

None. This is a SKILL.md (prose specification), not executable code. No concrete wrong behavior to report.

## Summary

| Category | Count | Net lines cut (est.) |
|----------|-------|---------------------|
| delete | 6 | ~280 |
| stdlib | 3 | ~50 |
| yagni | 6 | ~400 |
| shrink | 6 | ~300 |
| **Total** | **21** | **~1030** |

Current: 1660 lines. After cuts: ~630 lines. 62% reduction.
