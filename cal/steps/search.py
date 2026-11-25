"""步骤 6/8：权重网格搜索（按 AUC 选最优组合）。"""
from __future__ import annotations

import itertools

from .. import hashing, model


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")
    outcomes = hashing.read_jsonl(ctx.run_dir / "prepare" / "outcomes.jsonl")

    base_weights = dict(ctx.cfg["model"]["weights"])
    bias = float(ctx.cfg["model"]["bias"])
    grid = ctx.cfg["search"]["grid"]

    keys = sorted(grid)
    matrix = model.build_candidate_matrix(companies, cards)

    trials = []
    best = None
    for combo in itertools.product(*(grid[key] for key in keys)):
        weights = dict(base_weights)
        for key, value in zip(keys, combo):
            weights[key] = float(value)
        score_rows = model.score_matrix(matrix, weights, bias)
        labels, scores = model.flatten(companies, cards, outcomes, score_rows)
        value = model.auc(labels, scores)
        trial = {
            "weights": {key: hashing.r10(weights[key]) for key in model.FEATURES},
            "auc": hashing.r10(value),
        }
        trials.append(trial)
        if best is None or value > best["auc"]:
            best = trial

    payload = {
        "metric": "auc",
        "trials": len(trials),
        "best": best,
        "grid": {key: [hashing.r10(float(v)) for v in grid[key]] for key in keys},
        "all": trials,
    }
    path = hashing.write_canonical_json(ctx.run_dir / "search" / "search.json", payload)
    ctx.logger.info(
        "权重搜索完成 %d 组：最优 AUC=%.4f，权重=%s",
        len(trials),
        best["auc"],
        best["weights"],
    )
    return {
        "inputs": [
            "prepare/companies.jsonl",
            "prepare/demand_cards.jsonl",
            "prepare/outcomes.jsonl",
        ],
        "outputs": [f"search/{path.name}"],
    }
