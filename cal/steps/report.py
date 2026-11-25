"""步骤 8/8：汇总报告（唯一产出 metrics.json 的步骤）。

metrics.json 是黄金值比对的唯一对象：不含时间戳、不含 run_id，
同配置同数据重复运行必须逐字节一致。
"""
from __future__ import annotations

from .. import hashing


def _md_table(header, rows) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def run(ctx) -> dict:
    stats = hashing.read_json(ctx.run_dir / "prepare" / "stats.json")
    profile = hashing.read_json(ctx.run_dir / "profile" / "profile.json")
    replay = hashing.read_json(ctx.run_dir / "replay" / "replay.json")
    eval_result = hashing.read_json(ctx.run_dir / "eval" / "eval.json")
    thresholds = hashing.read_json(ctx.run_dir / "scan-thresholds" / "thresholds.json")
    search = hashing.read_json(ctx.run_dir / "search" / "search.json")
    ablation = hashing.read_json(ctx.run_dir / "ablation" / "ablation.json")

    metrics = {
        "schema_version": "1.0",
        "pipeline": {
            "steps": 8,
            "seed": int(ctx.cfg["seed"]),
            "config_sha256": ctx.config_sha256,
        },
        "dataset": {
            "companies": stats["companies"],
            "months": stats["months"],
            "demand_cards": stats["demand_cards"],
            "candidate_pairs": stats["candidate_pairs"],
            "positives": stats["positives"],
            "positive_rate": stats["positive_rate"],
        },
        "eval": eval_result,
        "best_threshold": thresholds["best"],
        "search": {
            "best_weights": search["best"]["weights"],
            "best_auc": search["best"]["auc"],
            "trials": search["trials"],
        },
        "ablation": {
            "baseline_auc": ablation["baseline_auc"],
            "deltas": {name: value["delta"] for name, value in ablation["features"].items()},
            "importance_order": ablation["importance_order"],
        },
        "profile": {
            "latest_month_activity_mean": profile["companies"]["latest_month_activity_mean"],
            "avg_resources": profile["companies"]["avg_resources"],
        },
    }
    metrics_path = hashing.write_canonical_json(ctx.run_dir / "report" / "metrics.json", metrics)

    eval_rows = [
        ["precision", eval_result["precision"]],
        ["recall", eval_result["recall"]],
        ["f1", eval_result["f1"]],
        ["accuracy", eval_result["accuracy"]],
        ["auc", eval_result["auc"]],
        ["TP / FP / TN / FN", f"{eval_result['tp']} / {eval_result['fp']} / {eval_result['tn']} / {eval_result['fn']}"],
    ]
    ablation_rows = [
        [name, value["auc_without"], value["delta"]]
        for name, value in ablation["features"].items()
    ]

    report = "\n".join(
        [
            "# 校准流水线运行报告",
            "",
            "> 本报告由 `cal run` 生成，内容不含时间戳与运行 id，可逐字节复现。",
            "",
            "## 1. 数据规模",
            "",
            _md_table(
                ["企业数", "月度数", "需求卡数", "候选对数", "正样本数", "正样本率"],
                [[
                    stats["companies"],
                    stats["months"],
                    stats["demand_cards"],
                    stats["candidate_pairs"],
                    stats["positives"],
                    stats["positive_rate"],
                ]],
            ),
            "",
            "## 2. 基线权重评估",
            "",
            f"阈值 = {eval_result['threshold']}",
            "",
            _md_table(["指标", "值"], eval_rows),
            "",
            "## 3. 阈值扫描",
            "",
            f"扫描 {thresholds['grid_size']} 个阈值点，目标指标 `{thresholds['metric']}`。"
            f"最优阈值 **{thresholds['best']['threshold']}**，{thresholds['metric']} = "
            f"**{thresholds['best'][thresholds['metric']]}**。",
            "",
            "## 4. 权重网格搜索",
            "",
            f"共 {search['trials']} 组组合，按 AUC 选优。最优 AUC = **{search['best']['auc']}**：",
            "",
            _md_table(
                ["特征", "权重"],
                [[name, search["best"]["weights"][name]] for name in search["best"]["weights"]],
            ),
            "",
            "## 5. 特征消融",
            "",
            f"基线 AUC = {ablation['baseline_auc']}（去掉某特征后 AUC 下降越多，该特征越重要）。",
            "",
            _md_table(["特征", "去掉后 AUC", "ΔAUC"], ablation_rows),
            "",
            "## 6. 回放摘要",
            "",
            f"- 需求卡 {replay['cards']} 张，每张候选 {replay['candidates_per_card']} 家，取前 {replay['top_k']} 名",
            f"- top1 平均分 {replay['mean_top1_score']}，top1 ≥ 0.5 的卡片占比 {replay['top1_ge_0_5_ratio']}",
            "",
        ]
    )
    report_path = ctx.run_dir / "report" / "report.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")

    ctx.logger.info(
        "报告完成：f1=%.4f auc=%.4f（metrics.json 已生成）",
        eval_result["f1"],
        eval_result["auc"],
    )
    return {
        "inputs": [
            "prepare/stats.json",
            "profile/profile.json",
            "replay/replay.json",
            "eval/eval.json",
            "scan-thresholds/thresholds.json",
            "search/search.json",
            "ablation/ablation.json",
        ],
        "outputs": ["report/metrics.json", "report/report.md"],
    }
