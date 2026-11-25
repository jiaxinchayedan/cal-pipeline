"""步骤 5/8：阈值扫描（在网格上找 F1 最优阈值）。"""
from __future__ import annotations

from .. import hashing, model


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")
    outcomes = hashing.read_jsonl(ctx.run_dir / "prepare" / "outcomes.jsonl")

    weights = ctx.cfg["model"]["weights"]
    bias = float(ctx.cfg["model"]["bias"])
    metric_name = ctx.cfg["scan_thresholds"].get("metric", "f1")

    matrix = model.build_candidate_matrix(companies, cards)
    score_rows = model.score_matrix(matrix, weights, bias)
    labels, scores = model.flatten(companies, cards, outcomes, score_rows)

    curve = []
    for threshold in model.threshold_grid(ctx.cfg["scan_thresholds"]):
        result = model.metrics_at(labels, scores, threshold)
        curve.append(
            {
                "threshold": hashing.r10(threshold),
                "f1": hashing.r10(result["f1"]),
                "precision": hashing.r10(result["precision"]),
                "recall": hashing.r10(result["recall"]),
            }
        )

    best = max(curve, key=lambda row: (row[metric_name], -row["threshold"]))
    payload = {
        "metric": metric_name,
        "grid_size": len(curve),
        "best": best,
        "curve": curve,
    }
    path = hashing.write_canonical_json(ctx.run_dir / "scan-thresholds" / "thresholds.json", payload)
    ctx.logger.info(
        "阈值扫描完成 %d 个点：最优 %s=%.4f @ thr=%.2f",
        len(curve),
        metric_name,
        best[metric_name],
        best["threshold"],
    )
    return {
        "inputs": [
            "prepare/companies.jsonl",
            "prepare/demand_cards.jsonl",
            "prepare/outcomes.jsonl",
        ],
        "outputs": [f"scan-thresholds/{path.name}"],
    }
