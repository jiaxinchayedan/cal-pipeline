"""步骤 3/8：历史回放（用当前权重给每张需求卡重排候选企业）。"""
from __future__ import annotations

from .. import hashing, model


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")

    weights = ctx.cfg["model"]["weights"]
    bias = float(ctx.cfg["model"]["bias"])
    top_k = int(ctx.cfg.get("replay", {}).get("top_k", 5))

    matrix = model.build_candidate_matrix(companies, cards)
    score_rows = model.score_matrix(matrix, weights, bias)

    samples = []
    top1_total = 0.0
    covered = 0
    for card, scores in zip(cards, score_rows):
        ranked = sorted(
            range(len(companies)), key=lambda i: (-scores[i], companies[i]["id"])
        )[:top_k]
        top1_total += scores[ranked[0]]
        if scores[ranked[0]] >= 0.5:
            covered += 1
        samples.append(
            {
                "card_id": card["id"],
                "ranked": [
                    {
                        "company_id": companies[i]["id"],
                        "score": hashing.r10(scores[i]),
                    }
                    for i in ranked
                ],
            }
        )

    replay = {
        "cards": len(cards),
        "candidates_per_card": len(companies),
        "top_k": top_k,
        "mean_top1_score": hashing.r10(top1_total / len(cards)) if cards else 0.0,
        "top1_ge_0_5_ratio": hashing.r10(covered / len(cards)) if cards else 0.0,
        "samples": samples,
    }
    path = hashing.write_canonical_json(ctx.run_dir / "replay" / "replay.json", replay)
    ctx.logger.info(
        "回放完成：%d 张卡 × %d 家企业，top1 均分 %.4f，top1≥0.5 占比 %.4f",
        replay["cards"],
        replay["candidates_per_card"],
        replay["mean_top1_score"],
        replay["top1_ge_0_5_ratio"],
    )
    return {
        "inputs": ["prepare/companies.jsonl", "prepare/demand_cards.jsonl"],
        "outputs": [f"replay/{path.name}"],
    }
