"""虚构数据生成与脱敏抽取。

数据源二选一（cal.yaml 的 data.source）：
  generate —— 按 seed 确定性生成 300 家企业 / 24 个月快照 / 200 张需求卡；
  extract  —— 从 data/raw/*.jsonl 读取并做正则脱敏（手机号、邮箱、身份证号）。

全程只用虚构数据，不涉及任何真实个人信息或企业信息。
"""
from __future__ import annotations

import math
import random
import re
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

from .model import FEATURES, TRUE_BIAS, TRUE_WEIGHTS, features

NAMESPACE = uuid.UUID("6f1c4a7e-2d5b-4e43-9c1a-7b8d3f0e5a21")

INDUSTRIES = [
    "智能制造",
    "新材料",
    "生物医药",
    "跨境电商",
    "现代物流",
    "软件信息",
    "节能环保",
    "文旅会展",
]
REGIONS = ["思明区", "湖里区", "集美区", "海沧区", "同安区", "翔安区"]
RESOURCES = ["产线", "实验室", "仓储", "会议室", "展厅", "检测设备", "冷链", "直播间"]
SCALES = [20, 50, 80, 120, 200, 350, 600, 900, 1500]
CARD_SCALES = [30, 60, 100, 200, 400, 800, 1200]

PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IDCARD_RE = re.compile(r"\b\d{17}[\dXx]\b")


def month_label(index: int, start_year: int = 2025) -> str:
    return f"{start_year + index // 12:04d}-{index % 12 + 1:02d}"


def generate(cfg: dict, seed: int) -> Tuple[List[dict], List[dict], List[dict]]:
    data = cfg["data"]
    n_companies = int(data["companies"])
    n_months = int(data["months"])
    n_cards = int(data["demand_cards"])

    rng = random.Random(seed * 7919 + 11)

    companies: List[dict] = []
    for i in range(n_companies):
        cid = str(uuid.uuid5(NAMESPACE, f"{seed}:company:{i}"))
        industry = INDUSTRIES[rng.randrange(len(INDUSTRIES))]
        region = REGIONS[rng.randrange(len(REGIONS))]
        employees = int(rng.choice(SCALES))
        resources = sorted(rng.sample(RESOURCES, rng.randint(1, 4)))
        level = rng.uniform(0.15, 0.85)
        monthly = []
        for m in range(n_months):
            level = min(0.99, max(0.01, level + rng.gauss(0.0, 0.04)))
            monthly.append(
                {
                    "month": month_label(m),
                    "activity": round(level, 6),
                    "deals": int(rng.randint(0, 6)),
                }
            )
        companies.append(
            {
                "id": cid,
                "org_id": str(uuid.uuid5(NAMESPACE, f"{seed}:org:{i % 12}")),
                "site_id": str(uuid.uuid5(NAMESPACE, f"{seed}:site:{i % 5}")),
                "industry": industry,
                "region": region,
                "employees": employees,
                "resources": resources,
                "monthly": monthly,
            }
        )

    cards: List[dict] = []
    for j in range(n_cards):
        sid = str(uuid.uuid5(NAMESPACE, f"{seed}:card:{j}"))
        cards.append(
            {
                "id": sid,
                "org_id": str(uuid.uuid5(NAMESPACE, f"{seed}:org:{j % 12}")),
                "site_id": str(uuid.uuid5(NAMESPACE, f"{seed}:site:{j % 5}")),
                "industry": INDUSTRIES[rng.randrange(len(INDUSTRIES))],
                "region": REGIONS[rng.randrange(len(REGIONS))],
                "budget_cents": int(rng.randrange(2000, 60000)),
                "needed_resources": sorted(rng.sample(RESOURCES, rng.randint(1, 3))),
                "company_scale": int(rng.choice(CARD_SCALES)),
                "urgency": rng.choice(["low", "normal", "high"]),
            }
        )

    # 历史决策标签：由内置"真实"偏好 + 确定性噪声生成，模拟已发生的接受/拒绝记录
    lrng = random.Random(seed * 7919 + 12)
    outcomes: List[dict] = []
    for card in cards:
        for company in companies:
            feat = features(company, card)
            z = TRUE_BIAS + sum(TRUE_WEIGHTS[name] * value for name, value in zip(FEATURES, feat))
            z += lrng.gauss(0.0, 0.25)
            prob = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))
            label = 1 if lrng.random() < prob else 0
            outcomes.append({"card_id": card["id"], "company_id": company["id"], "label": label})

    return companies, cards, outcomes


def _mask(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = PHONE_RE.sub("1**********", text)
    text = EMAIL_RE.sub("***@masked.invalid", text)
    text = IDCARD_RE.sub("******************", text)
    return text


def _mask_obj(obj):
    if isinstance(obj, dict):
        return {key: _mask_obj(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_mask_obj(item) for item in obj]
    return _mask(value)


def extract(cfg: dict, run_dir: Path) -> Tuple[List[dict], List[dict], List[dict]]:
    """脱敏抽取：读取 data/raw 下的三家原始表，做字段级脱敏后归一为同一结构。"""
    raw_dir = Path(cfg["data"]["raw_dir"])
    if not raw_dir.is_absolute():
        raw_dir = Path.cwd() / raw_dir
    required = {"companies.jsonl": (None,), "demand_cards.jsonl": (None,), "outcomes.jsonl": (None,)}
    missing = [name for name in required if not (raw_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"extract 模式缺少原始表：{missing}（目录 {raw_dir}）")

    def load(name: str) -> List[dict]:
        rows = []
        with (raw_dir / name).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(_mask_obj(__import__("json").loads(line)))
        return rows

    return load("companies.jsonl"), load("demand_cards.jsonl"), load("outcomes.jsonl")


def dataset_stats(companies: List[dict], cards: List[dict], outcomes: List[dict]) -> Dict[str, object]:
    positives = sum(1 for row in outcomes if row["label"] == 1)
    industry_dist: Dict[str, int] = {}
    for company in companies:
        industry_dist[company["industry"]] = industry_dist.get(company["industry"], 0) + 1
    resource_hits = 0
    for company in companies:
        resource_hits += len(company["resources"])
    return {
        "companies": len(companies),
        "months": len(companies[0]["monthly"]) if companies else 0,
        "demand_cards": len(cards),
        "candidate_pairs": len(outcomes),
        "positives": positives,
        "positive_rate": round(positives / len(outcomes), 10) if outcomes else 0.0,
        "industry_distribution": industry_dist,
        "avg_resources_per_company": round(resource_hits / len(companies), 10) if companies else 0.0,
    }
