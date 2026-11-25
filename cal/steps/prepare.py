"""步骤 1/8：数据准备（generate 虚构数据 或 extract 脱敏抽取）。"""
from __future__ import annotations

import json
import shutil

from .. import dataset, hashing


def run(ctx) -> dict:
    out = ctx.run_dir / "prepare"
    out.mkdir(parents=True, exist_ok=True)

    source = ctx.cfg["data"]["source"]
    inputs: list = []
    if source == "generate":
        companies, cards, outcomes = dataset.generate(ctx.cfg, ctx.seed)
    else:
        companies, cards, outcomes = dataset.extract(ctx.cfg, ctx.run_dir)
        # 把原始表快照进运行目录：运行自包含、可异地回验，不依赖绝对路径
        raw_dir = dataset.resolve_raw_dir(ctx.cfg)
        snap_dir = out / "raw"
        snap_dir.mkdir(parents=True, exist_ok=True)
        inputs = []
        for name in dataset.RAW_TABLES:
            shutil.copyfile(raw_dir / name, snap_dir / name)
            inputs.append(f"prepare/raw/{name}")

    files = []
    for name, rows in (
        ("companies", companies),
        ("demand_cards", cards),
        ("outcomes", outcomes),
    ):
        path = hashing.write_jsonl(out / f"{name}.jsonl", rows)
        files.append(f"prepare/{path.name}")

    stats = dataset.dataset_stats(companies, cards, outcomes)
    stats_path = hashing.write_canonical_json(out / "stats.json", stats)
    files.append(f"prepare/{stats_path.name}")

    ctx.logger.info(
        "数据源=%s 企业=%d 月数=%d 需求卡=%d 候选对=%d 正样本率=%.4f",
        source,
        stats["companies"],
        stats["months"],
        stats["demand_cards"],
        stats["candidate_pairs"],
        stats["positive_rate"],
    )
    return {"inputs": inputs, "outputs": files}
