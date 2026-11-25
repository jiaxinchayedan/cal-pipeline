"""步骤 4/8：指标评估（在指定阈值下计算混淆矩阵与分类指标）。"""
from __future__ import annotations

from .. import hashing, model


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")
    outcomes = hashing.read_jsonl(ctx.run_dir / "prepare" / "outcomes.jsonl")

    weights = ctx.cfg["model"]["weights"]
    bias = float(ctx.cfg["model"]["bias"])
    threshold = float(ctx.cfg["eval"]["threshold"])

    matrix = model.build_candidate_matrix(companies, cards)
    score_rows = model.score_matrix(matrix, weights, bias)
    labels, scores = model.flatten(companies, cards, outcomes, score_rows)

    result = model.metrics_at(labels, scores, threshold)
    result = {key: (hashing.r10(value) if isinstance(value, float) else value) for key, value in result.items()}
    result["positives"] = sum(labels)
    result["negatives"] = len(labels) - sum(labels)

    path = hashing.write_canonical_json(ctx.run_dir / "eval" / "eval.json", result)
    ctx.logger.info(
        "评估完成 thr=%.2f：precision=%.4f recall=%.4f f1=%.4f auc=%.4f",
        threshold,
        result["precision"],
        result["recall"],
        result["f1"],
        result["auc"],
    )
    return {
        "inputs": [
            "prepare/companies.jsonl",
            "prepare/demand_cards.jsonl",
            "prepare/outcomes.jsonl",
        ],
        "outputs": [f"eval/{path.name}"],
    }
