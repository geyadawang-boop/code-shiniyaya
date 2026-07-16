"""
A/B 测试框架 - AB Test Runner
支持 分流 -> 对比 -> 显著性检验
版本: 1.0.0 | 演化标记: evo-2025-01-11-004
交叉利用: oracle (review quality对比) + model-usage (分组cost追踪) + prompt-optimizer (prompt变体测试)

设计参考:
- 随机分流: 基于 bvid hash 确定性分流 (可复现)
- 多维度对比: 评分/标签/文本长度/响应时间/成本
- 显著性检验: Welch's t-test / Chi-square for categorical
"""

import json
import os
import hashlib
import math
import random
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Callable, Any

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "data.db")
AB_LOG_JSONL = os.path.join(BACKEND_DIR, "ab_test_log.jsonl")


class ABExperiment:
    """
    A/B 实验定义

    用法:
        exp = ABExperiment(
            name="prompt_v2_vs_v1",
            description="测试新版 detailed prompt 对评分的影响",
            variants={
                "control": {"prompt_version": "v1.0.0", "model": "claude-sonnet-4-20250514"},
                "treatment": {"prompt_version": "v1.1.0", "model": "claude-sonnet-4-20250514"}
            },
            traffic_split={"control": 0.5, "treatment": 0.5},
            metrics=["rating", "summary_length", "response_time_ms", "cost"],
            min_sample_size=50
        )
    """

    VALID_METRICS = [
        "rating",              # 用户评分 (1-5)
        "summary_length",      # 总结文本长度 (字符数)
        "response_time_ms",    # API响应时间 (毫秒)
        "cost",                # API调用成本
        "positive_rate",       # 好评率 (4星及以上)
        "issue_rate"           # 问题频率
    ]

    def __init__(
        self,
        name: str,
        description: str,
        variants: Dict[str, dict],           # {"control": {...}, "treatment": {...}}
        traffic_split: Dict[str, float],     # {"control": 0.5, "treatment": 0.5}
        metrics: List[str],                  # 要追踪的指标
        min_sample_size: int = 30,
        significance_level: float = 0.05,
        experiment_id: str = None,
        status: str = "draft",               # draft | running | paused | completed
        created_at: str = None,
        completed_at: str = None,
        metadata: Dict = None
    ):
        self.experiment_id = experiment_id or f"ab-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{name[:20]}"
        self.name = name
        self.description = description
        self.variants = variants
        self.traffic_split = traffic_split
        self.metrics = [m for m in metrics if m in self.VALID_METRICS]
        self.min_sample_size = min_sample_size
        self.significance_level = significance_level
        self.status = status
        self.created_at = created_at or datetime.now().isoformat()
        self.completed_at = completed_at
        self.metadata = metadata or {}

        self._validate()

    def _validate(self):
        """验证实验配置"""
        # 分流比例和必须为 1.0
        total = sum(self.traffic_split.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Traffic split must sum to 1.0, got {total}")

        # 变体和分流键必须匹配
        if set(self.variants.keys()) != set(self.traffic_split.keys()):
            raise ValueError("Variants and traffic_split must have same keys")

        # 至少两个变体
        if len(self.variants) < 2:
            raise ValueError("Must have at least 2 variants")

        # 必须有指标
        if not self.metrics:
            raise ValueError("Must specify at least 1 metric")

    def assign_variant(self, bvid: str) -> str:
        """
        基于 bvid hash 确定性分流

        使用 MD5(bvid + experiment_id) 生成 [0, 1) 的随机数
        按 traffic_split 累积判断归属
        """
        seed = f"{bvid}:{self.experiment_id}"
        hash_hex = hashlib.md5(seed.encode()).hexdigest()
        hash_int = int(hash_hex[:8], 16)
        bucket = hash_int / 0xFFFFFFFF  # [0, 1)

        cumulative = 0.0
        for variant_name, fraction in sorted(self.traffic_split.items()):
            cumulative += fraction
            if bucket < cumulative:
                return variant_name

        # fallback: 返回第一个变体
        return list(self.variants.keys())[0]

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "variants": self.variants,
            "traffic_split": self.traffic_split,
            "metrics": self.metrics,
            "min_sample_size": self.min_sample_size,
            "significance_level": self.significance_level,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata
        }


class ABTestResult:
    """单次分配的结果记录"""

    def __init__(
        self,
        experiment_id: str,
        bvid: str,
        variant: str,
        history_id: int = 0,
        rating: int = 0,
        summary_length: int = 0,
        response_time_ms: int = 0,
        cost: float = 0.0,
        positive: bool = False,
        issues: List[str] = None,
        model: str = "",
        prompt_version: str = "",
        timestamp: str = None
    ):
        self.experiment_id = experiment_id
        self.bvid = bvid
        self.variant = variant
        self.history_id = history_id
        self.rating = rating
        self.summary_length = summary_length
        self.response_time_ms = response_time_ms
        self.cost = cost
        self.positive = positive  # rating >= 4
        self.issues = issues or []
        self.model = model
        self.prompt_version = prompt_version
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "bvid": self.bvid,
            "variant": self.variant,
            "history_id": self.history_id,
            "rating": self.rating,
            "summary_length": self.summary_length,
            "response_time_ms": self.response_time_ms,
            "cost": self.cost,
            "positive": self.positive,
            "issues": self.issues,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "timestamp": self.timestamp
        }


class ABTestRunner:
    """
    A/B 测试运行器

    用法:
        runner = ABTestRunner()

        # 1. 创建实验
        exp = ABExperiment(...)
        runner.create(exp)

        # 2. 分流
        variant = runner.assign("BVxxx", "ab-xxx")

        # 3. 记录结果
        result = ABTestResult(experiment_id="ab-xxx", bvid="BVxxx", variant="control", rating=4)
        runner.record(result)

        # 4. 分析
        report = runner.analyze("ab-xxx")
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._ensure_tables()

    # ==================== 实验管理 ====================

    def create(self, experiment: ABExperiment) -> str:
        """创建并启动一个实验"""
        conn = sqlite3.connect(self.db_path)
        d = experiment.to_dict()
        conn.execute("""
            INSERT OR REPLACE INTO ab_experiments (
                experiment_id, name, description, config_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            d["experiment_id"], d["name"], d["description"],
            json.dumps(d, ensure_ascii=False),
            d["status"], d["created_at"]
        ))
        conn.commit()
        conn.close()
        return experiment.experiment_id

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        """获取实验详情"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ab_experiments WHERE experiment_id=?",
            (experiment_id,)
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["config"] = json.loads(d.get("config_json", "{}"))
            return d
        return None

    def list_experiments(self, status: str = None) -> List[dict]:
        """列出实验"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM ab_experiments WHERE status=? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ab_experiments ORDER BY created_at DESC"
            ).fetchall()
        conn.close()
        return [_ab_deserialize(dict(r)) for r in rows]

    def update_status(self, experiment_id: str, status: str):
        """更新实验状态"""
        conn = sqlite3.connect(self.db_path)
        if status == "completed":
            conn.execute(
                "UPDATE ab_experiments SET status=?, completed_at=? WHERE experiment_id=?",
                (status, datetime.now().isoformat(), experiment_id)
            )
        else:
            conn.execute(
                "UPDATE ab_experiments SET status=? WHERE experiment_id=?",
                (status, experiment_id)
            )
        conn.commit()
        conn.close()

    # ==================== 分流 ====================

    def assign(self, bvid: str, experiment_id: str) -> Optional[str]:
        """为给定 bvid 分配变体"""
        exp_data = self.get_experiment(experiment_id)
        if not exp_data:
            return None

        config = exp_data.get("config", {})
        variants = config.get("variants", {})
        traffic = config.get("traffic_split", {})

        seed = f"{bvid}:{experiment_id}"
        hash_hex = hashlib.md5(seed.encode()).hexdigest()
        hash_int = int(hash_hex[:8], 16)
        bucket = hash_int / 0xFFFFFFFF

        cumulative = 0.0
        for variant_name, fraction in sorted(traffic.items()):
            cumulative += fraction
            if bucket < cumulative:
                return variant_name

        return list(variants.keys())[0] if variants else None

    def assign_and_record(self, bvid: str, experiment_id: str, **metrics) -> Optional[str]:
        """分流并立即记录 (便捷方法)"""
        variant = self.assign(bvid, experiment_id)
        if not variant:
            return None

        result = ABTestResult(
            experiment_id=experiment_id,
            bvid=bvid,
            variant=variant,
            positive=metrics.get("rating", 0) >= 4,
            **{k: metrics.get(k, 0) for k in ["rating", "summary_length", "response_time_ms", "cost", "history_id"]}
        )
        self.record(result)
        return variant

    # ==================== 结果记录 ====================

    def record(self, result: ABTestResult):
        """记录一次实验结果"""
        # JSONL 追加
        os.makedirs(os.path.dirname(AB_LOG_JSONL) or BACKEND_DIR, exist_ok=True)
        with open(AB_LOG_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

        # SQLite 写入
        conn = sqlite3.connect(self.db_path)
        d = result.to_dict()
        conn.execute("""
            INSERT INTO ab_results (
                experiment_id, bvid, variant, history_id,
                rating, summary_length, response_time_ms, cost,
                positive, issues, model, prompt_version, timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            d["experiment_id"], d["bvid"], d["variant"], d["history_id"],
            d["rating"], d["summary_length"], d["response_time_ms"], d["cost"],
            1 if d["positive"] else 0, json.dumps(d["issues"]),
            d["model"], d["prompt_version"], d["timestamp"]
        ))
        conn.commit()
        conn.close()

    # ==================== 分析 (核心) ====================

    def analyze(self, experiment_id: str) -> dict:
        """
        分析 A/B 实验结果
        返回:
        {
            "experiment_id": "ab-xxx",
            "status": "completed",
            "total_samples": {variant: count, ...},
            "metrics": {
                "rating": {
                    "control": {"mean": 4.2, "std": 0.8, "n": 50},
                    "treatment": {"mean": 4.5, "std": 0.6, "n": 50},
                    "p_value": 0.03,
                    "significant": true,
                    "effect_size": 0.3,
                    "winner": "treatment"
                },
                ...
            },
            "recommendation": "treatment variant significantly better"
        }
        """
        exp_data = self.get_experiment(experiment_id)
        if not exp_data:
            return {"error": "Experiment not found"}

        config = exp_data.get("config", {})
        metrics_to_check = config.get("metrics", ["rating"])
        variants = list(config.get("variants", {}).keys())

        # 读取所有结果
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM ab_results WHERE experiment_id=?",
            (experiment_id,)
        ).fetchall()
        conn.close()

        results = [_ab_result_deserialize(dict(r)) for r in rows]

        # 按 variant 分组
        groups = {v: [] for v in variants}
        for r in results:
            if r["variant"] in groups:
                groups[r["variant"]].append(r)

        # 样本量检查
        total_samples = {v: len(data) for v, data in groups.items()}
        has_sufficient_samples = all(
            n >= config.get("min_sample_size", 30)
            for n in total_samples.values()
        )

        # 逐指标分析
        metrics_report = {}
        winners = {}

        for metric in metrics_to_check:
            metric_data = {}
            for variant in variants:
                values = self._extract_metric_values(groups[variant], metric)
                if values:
                    metric_data[variant] = {
                        "mean": round(sum(values) / len(values), 3),
                        "std": round(_sample_std(values), 3),
                        "n": len(values),
                        "values": values  # 保留用于后续计算
                    }

            if len(metric_data) < 2:
                continue

            # 进行显著性检验
            v_names = list(metric_data.keys())
            v_a, v_b = v_names[0], v_names[1]

            if metric in ("rating", "summary_length", "response_time_ms", "cost"):
                # 连续变量: Welch's t-test
                test_result = _welch_ttest(
                    metric_data[v_a]["values"],
                    metric_data[v_b]["values"]
                )
            elif metric in ("positive_rate", "issue_rate"):
                # 二分类: Chi-square test
                test_result = _chi_square_test(
                    groups[v_a], groups[v_b], metric
                )
            else:
                test_result = {"p_value": 1.0, "significant": False, "test": "unknown"}

            # 效应量 (Cohen's d)
            effect_size = _cohens_d(
                metric_data[v_a]["values"],
                metric_data[v_b]["values"]
            ) if metric in ("rating", "summary_length", "response_time_ms", "cost") else 0

            # 决定赢家
            winner = None
            if test_result.get("significant"):
                # 对于 rating/positive_rate: 越大越好
                if metric in ("rating", "positive_rate"):
                    winner = v_a if metric_data[v_a]["mean"] > metric_data[v_b]["mean"] else v_b
                # 对于 response_time_ms/cost/issue_rate: 越小越好
                elif metric in ("response_time_ms", "cost", "issue_rate"):
                    winner = v_a if metric_data[v_a]["mean"] < metric_data[v_b]["mean"] else v_b
                # 对于 summary_length: 取决于实验目标, 默认看哪个更接近最优范围(200-600字)
                elif metric == "summary_length":
                    # 中文总结理想长度 200-600 字
                    dist_a = abs(metric_data[v_a]["mean"] - 400)
                    dist_b = abs(metric_data[v_b]["mean"] - 400)
                    winner = v_a if dist_a < dist_b else v_b

            # 清理 values, 不返回原始数据
            clean_data = {}
            for v_name, v_data in metric_data.items():
                clean_data[v_name] = {
                    "mean": v_data["mean"],
                    "std": v_data["std"],
                    "n": v_data["n"]
                }

            metrics_report[metric] = {
                **clean_data,
                "p_value": test_result.get("p_value", 1.0),
                "significant": test_result.get("significant", False),
                "effect_size": round(effect_size, 3),
                "test": test_result.get("test", "unknown"),
                "winner": winner
            }

            if winner:
                winners[metric] = winner

        # 综合推荐
        recommendation = self._build_recommendation(metrics_report, winners, total_samples, has_sufficient_samples)

        return {
            "experiment_id": experiment_id,
            "experiment_name": config.get("name", ""),
            "status": exp_data.get("status", ""),
            "total_samples": total_samples,
            "sufficient_samples": has_sufficient_samples,
            "metrics": metrics_report,
            "per_metric_winners": winners,
            "recommendation": recommendation,
            "analyzed_at": datetime.now().isoformat()
        }

    def _extract_metric_values(self, group_results: List[dict], metric: str) -> List[float]:
        """从分组结果中提取指标值"""
        values = []
        for r in group_results:
            if metric == "rating":
                val = r.get("rating", 0)
            elif metric == "summary_length":
                val = r.get("summary_length", 0)
            elif metric == "response_time_ms":
                val = r.get("response_time_ms", 0)
            elif metric == "cost":
                val = r.get("cost", 0)
            elif metric == "positive_rate":
                val = 1 if r.get("positive") else 0
            elif metric == "issue_rate":
                val = 1 if r.get("issues") and len(r.get("issues", [])) > 0 else 0
            else:
                val = 0
            if val > 0 or metric in ("rating", "positive_rate", "issue_rate", "summary_length", "response_time_ms", "cost"):
                values.append(float(val))
        return values

    def _build_recommendation(
        self,
        metrics_report: dict,
        winners: dict,
        total_samples: dict,
        has_sufficient: bool
    ) -> str:
        """构建推荐建议"""
        if not has_sufficient:
            return f"样本量不足，需要继续收集数据。当前样本: {total_samples}"

        if not winners:
            return "所有指标无显著差异，建议保持当前版本。"

        # 计算每个变体的赢面
        variant_wins = {}
        for metric, winner in winners.items():
            variant_wins[winner] = variant_wins.get(winner, 0) + 1

        total_metrics = len(metrics_report)
        dominant = max(variant_wins, key=variant_wins.get)
        dominant_win_rate = variant_wins[dominant] / total_metrics

        if dominant_win_rate > 0.6:
            return (
                f"强力推荐采用 {dominant} 变体: "
                f"在 {variant_wins[dominant]}/{total_metrics} 个指标上表现更好"
            )
        elif dominant_win_rate > 0.4:
            return (
                f"建议采用 {dominant} 变体: "
                f"在 {variant_wins[dominant]}/{total_metrics} 个指标上有优势"
            )
        else:
            return "各变体表现相当，需要更多数据或考虑其他优化方向。"

    # ==================== 持久化 ====================

    def _ensure_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ab_experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                config_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ab_exp_status ON ab_experiments(status);

            CREATE TABLE IF NOT EXISTS ab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                bvid TEXT NOT NULL,
                variant TEXT NOT NULL,
                history_id INTEGER DEFAULT 0,
                rating INTEGER DEFAULT 0,
                summary_length INTEGER DEFAULT 0,
                response_time_ms INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                positive INTEGER DEFAULT 0,
                issues TEXT DEFAULT '[]',
                model TEXT DEFAULT '',
                prompt_version TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ab_result_exp ON ab_results(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_ab_result_variant ON ab_results(experiment_id, variant);
            CREATE INDEX IF NOT EXISTS idx_ab_result_bvid ON ab_results(bvid);
        """)
        conn.commit()
        conn.close()


# ==================== 统计检验函数 ====================

def _welch_ttest(sample_a: List[float], sample_b: List[float]) -> dict:
    """
    Welch's t-test (不等方差 t 检验)
    适用于连续变量: rating, length, time, cost
    返回: {p_value, significant, t_statistic, df, test}
    """
    n_a, n_b = len(sample_a), len(sample_b)
    if n_a < 2 or n_b < 2:
        return {"p_value": 1.0, "significant": False, "t_statistic": 0, "df": 0, "test": "welch_ttest"}

    mean_a = sum(sample_a) / n_a
    mean_b = sum(sample_b) / n_b

    var_a = _sample_variance(sample_a, mean_a)
    var_b = _sample_variance(sample_b, mean_b)

    if var_a == 0 and var_b == 0:
        return {"p_value": 1.0, "significant": False, "t_statistic": 0, "df": n_a + n_b - 2, "test": "welch_ttest"}

    se = math.sqrt(var_a / n_a + var_b / n_b)
    if se == 0:
        return {"p_value": 1.0, "significant": False, "t_statistic": 0, "df": n_a + n_b - 2, "test": "welch_ttest"}

    t_stat = (mean_a - mean_b) / se

    # Welch-Satterthwaite 自由度
    term_a = var_a / n_a
    term_b = var_b / n_b
    if term_a == 0 and term_b == 0:
        df = n_a + n_b - 2
    else:
        df_num = (term_a + term_b) ** 2
        df_den = (term_a ** 2) / (n_a - 1) + (term_b ** 2) / (n_b - 1)
        df = df_num / df_den if df_den > 0 else n_a + n_b - 2

    # p-value from t-distribution (使用正态近似)
    p_value = _t_distribution_p_value(abs(t_stat), df)

    return {
        "p_value": round(p_value, 4),
        "significant": p_value < 0.05,
        "t_statistic": round(t_stat, 3),
        "df": round(df, 1),
        "test": "welch_ttest"
    }


def _chi_square_test(group_a: List[dict], group_b: List[dict], metric: str) -> dict:
    """
    Chi-square 独立性检验
    适用于二分类变量: positive_rate, issue_rate
    """
    if metric == "positive_rate":
        a_yes = sum(1 for r in group_a if r.get("positive"))
        a_no = len(group_a) - a_yes
        b_yes = sum(1 for r in group_b if r.get("positive"))
        b_no = len(group_b) - b_yes
    elif metric == "issue_rate":
        a_yes = sum(1 for r in group_a if r.get("issues"))
        a_no = len(group_a) - a_yes
        b_yes = sum(1 for r in group_b if r.get("issues"))
        b_no = len(group_b) - b_yes
    else:
        return {"p_value": 1.0, "significant": False, "test": "chi_square"}

    total = len(group_a) + len(group_b)
    if total < 5:
        return {"p_value": 1.0, "significant": False, "test": "chi_square"}

    # 期望值
    total_yes = a_yes + b_yes
    total_no = a_no + b_no

    e_a_yes = len(group_a) * total_yes / total if total > 0 else 0
    e_a_no = len(group_a) * total_no / total if total > 0 else 0
    e_b_yes = len(group_b) * total_yes / total if total > 0 else 0
    e_b_no = len(group_b) * total_no / total if total > 0 else 0

    chi2 = 0
    for obs, exp in [(a_yes, e_a_yes), (a_no, e_a_no), (b_yes, e_b_yes), (b_no, e_b_no)]:
        if exp > 0:
            chi2 += (obs - exp) ** 2 / exp

    # Chi-square with df=1, p-value approximation
    p_value = _chi_square_p_value(chi2, 1)

    return {
        "p_value": round(p_value, 4),
        "significant": p_value < 0.05,
        "chi2_statistic": round(chi2, 3),
        "test": "chi_square"
    }


def _cohens_d(sample_a: List[float], sample_b: List[float]) -> float:
    """计算效应量 Cohen's d"""
    n_a, n_b = len(sample_a), len(sample_b)
    if n_a < 2 or n_b < 2:
        return 0.0

    mean_a = sum(sample_a) / n_a
    mean_b = sum(sample_b) / n_b

    var_a = _sample_variance(sample_a, mean_a)
    var_b = _sample_variance(sample_b, mean_b)

    pooled_sd = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))
    if pooled_sd == 0:
        return 0.0

    return (mean_a - mean_b) / pooled_sd


# ==================== 统计工具函数 ====================

def _sample_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_variance(values: List[float], mean: float = None) -> float:
    if len(values) < 2:
        return 0.0
    if mean is None:
        mean = _sample_mean(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)


def _sample_std(values: List[float]) -> float:
    return math.sqrt(_sample_variance(values))


def _t_distribution_p_value(t: float, df: float) -> float:
    """
    t 分布的 p 值 (双侧)
    使用正态近似 (当 df > 30 时与正态几乎相同)
    """
    if df <= 0:
        return 1.0

    # 使用 Abramowitz and Stegun 26.7.1 的近似公式
    # 当 df > 30: 用正态近似
    if df > 30:
        return 2 * (1 - _normal_cdf(t))

    # 对小 df 使用更精确的 t 分布公式
    z = t * (1 - 1 / (4 * df)) / math.sqrt(1 + t * t / (2 * df))
    return 2 * (1 - _normal_cdf(z))


def _normal_cdf(x: float) -> float:
    """标准正态分布CDF (Abramowitz and Stegun 26.2.17)"""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0

    # Hart's algorithm
    a = abs(x)
    y = 1 / (1 + 0.2316419 * a)
    p = 0.3989422804014327 * math.exp(-a * a / 2)
    q = y * (0.319381530 + y * (-0.356563782 + y * (1.781477937 + y * (-1.821255978 + y * 1.330274429))))

    cdf = 1 - p * q
    return cdf if x >= 0 else 1 - cdf


def _chi_square_p_value(chi2: float, df: int) -> float:
    """Chi-square 分布的 p 值 (使用 Wilson-Hilferty 近似)"""
    if df <= 0 or chi2 <= 0:
        return 1.0

    # Wilson-Hilferty: (chi2/df)^(1/3) ~ N(1-2/(9df), sqrt(2/(9df)))
    z = ((chi2 / df) ** (1/3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    # 卡方检验是单侧检验: 只关心右侧尾部
    return 1 - _normal_cdf(z) if z >= 0 else _normal_cdf(-z)


# ==================== JSON 反序列化 ====================

def _ab_deserialize(row: dict) -> dict:
    if "config_json" in row and isinstance(row["config_json"], str):
        try:
            row["config"] = json.loads(row["config_json"])
        except (json.JSONDecodeError, TypeError):
            row["config"] = {}
    return row


def _ab_result_deserialize(row: dict) -> dict:
    if "issues" in row and isinstance(row["issues"], str):
        try:
            row["issues"] = json.loads(row["issues"])
        except (json.JSONDecodeError, TypeError):
            row["issues"] = []
    row["positive"] = bool(row.get("positive", 0))
    return row
