"""步骤 7/8：特征消融（逐个特征归零，观察 AUC 变化）。"""
from __future__ import annotations

from .. import hashing, model


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")
    outcomes = hashing.read_jsonl(ctx.run_dir / "prepare" / "outcomes.jsonl")

    base_weights = dict(ctx.cfg["model"]["weights"])
    bias = float(ctx.cfg["model"]["bias"])
    feature_list = ctx.cfg["ablation"]["features"]

    matrix = model.build_candidate_matrix(companies, cards)
    base_scores = model.score_matrix(matrix, base_weights, bias)
    labels, scores = model.flatten(companies, cards, outcomes, base_scores)
    baseline_auc = model.auc(labels, scores)

    details = {}
    for feature in feature_list:
        weights = dict(base_weights)
        weights[feature] = 0.0
        ablated_scores = model.score_matrix(matrix, weights, bias)
        ablated_labels, ablated = model.flatten(companies, cards, outcomes, ablated_scores)
        assert ablated_labels == labels
        ablated_auc = model.auc(ablated_labels, ablated)
        details[feature] = {
            "auc_without": hashing.r10(ablated_auc),
            "delta": hashing.r10(baseline_auc - ablated_auc),
        }

    ranked = sorted(details, key=lambda name: (-details[name]["delta"], name))
    payload = {
        "baseline_auc": hashing.r10(baseline_auc),
        "features": details,
        "importance_order": ranked,
    }
    path = hashing.write_canonical_json(ctx.run_dir / "ablation" / "ablation.json", payload)
    ctx.logger.info(
        "消融完成：基线 AUC=%.4f，最重要特征=%s（Δ=%.4f）",
        baseline_auc,
        ranked[0],
        details[ranked[0]]["delta"],
    )
    return {
        "inputs": [
            "prepare/companies.jsonl",
            "prepare/demand_cards.jsonl",
            "prepare/outcomes.jsonl",
        ],
        "outputs": [f"ablation/{path.name}"],
    }
