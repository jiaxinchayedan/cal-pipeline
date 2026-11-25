"""步骤 2/8：数据画像（字段完整率、分布、活跃度基线）。"""
from __future__ import annotations

from .. import hashing


def _null_rate(rows: list, field: str) -> float:
    if not rows:
        return 0.0
    missing = sum(1 for row in rows if row.get(field) in (None, "", [], {}))
    return round(missing / len(rows), 10)


def run(ctx) -> dict:
    companies = hashing.read_jsonl(ctx.run_dir / "prepare" / "companies.jsonl")
    cards = hashing.read_jsonl(ctx.run_dir / "prepare" / "demand_cards.jsonl")

    industry_dist: dict[str, int] = {}
    region_dist: dict[str, int] = {}
    for company in companies:
        industry_dist[company["industry"]] = industry_dist.get(company["industry"], 0) + 1
        region_dist[company["region"]] = region_dist.get(company["region"], 0) + 1

    latest_activity = [company["monthly"][-1]["activity"] for company in companies]
    mean_activity = round(sum(latest_activity) / len(latest_activity), 10) if latest_activity else 0.0
    variance = (
        round(sum((value - mean_activity) ** 2 for value in latest_activity) / len(latest_activity), 10)
        if latest_activity
        else 0.0
    )

    card_industries: dict[str, int] = {}
    for card in cards:
        card_industries[card["industry"]] = card_industries.get(card["industry"], 0) + 1

    profile = {
        "companies": {
            "rows": len(companies),
            "null_rate": {
                field: _null_rate(companies, field)
                for field in ("id", "industry", "region", "employees", "resources", "monthly")
            },
            "industry_distribution": dict(sorted(industry_dist.items())),
            "region_distribution": dict(sorted(region_dist.items())),
            "latest_month_activity_mean": mean_activity,
            "latest_month_activity_variance": variance,
            "avg_resources": round(
                sum(len(company["resources"]) for company in companies) / len(companies), 10
            )
            if companies
            else 0.0,
        },
        "demand_cards": {
            "rows": len(cards),
            "null_rate": {
                field: _null_rate(cards, field)
                for field in ("id", "industry", "region", "budget_cents", "needed_resources")
            },
            "industry_distribution": dict(sorted(card_industries.items())),
            "avg_budget_cents": round(
                sum(card["budget_cents"] for card in cards) / len(cards), 10
            )
            if cards
            else 0.0,
        },
    }

    path = hashing.write_canonical_json(ctx.run_dir / "profile" / "profile.json", profile)
    ctx.logger.info(
        "画像完成：企业 %d 行（活跃度均值 %.4f），需求卡 %d 行",
        profile["companies"]["rows"],
        mean_activity,
        profile["demand_cards"]["rows"],
    )
    return {
        "inputs": ["prepare/companies.jsonl", "prepare/demand_cards.jsonl"],
        "outputs": [f"profile/{path.name}"],
    }
