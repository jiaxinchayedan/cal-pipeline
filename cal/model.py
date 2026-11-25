"""匹配校准模型：特征工程、打分、阈值扫描与指标计算。

全部为纯 Python 确定性实现（不依赖 numpy），保证同配置同数据可逐字节复现。
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

FEATURES: Tuple[str, ...] = (
    "industry_match",
    "region_match",
    "size_fit",
    "activity",
    "resource_overlap",
)

# 虚构数据生成器内置的"真实"权重（模拟历史决策偏好），仅用于合成标签
TRUE_WEIGHTS: Dict[str, float] = {
    "industry_match": 0.80,
    "region_match": 0.35,
    "size_fit": 0.60,
    "activity": 1.00,
    "resource_overlap": 1.40,
}
TRUE_BIAS = -2.20


def _sigmoid(z: float) -> float:
    z = max(-60.0, min(60.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def activity_score(company: dict, window: int = 6) -> float:
    monthly = company["monthly"][-window:]
    return sum(item["activity"] for item in monthly) / len(monthly)


def features(company: dict, card: dict) -> Tuple[float, ...]:
    """返回固定顺序的五维特征，与 FEATURES 一一对应。"""
    industry_match = 1.0 if company["industry"] == card["industry"] else 0.0
    region_match = 1.0 if company["region"] == card["region"] else 0.0

    ratio = float(card["company_scale"]) / max(1, int(company["employees"]))
    size_fit = 1.0 / (1.0 + abs(math.log(ratio)))

    needed = set(card["needed_resources"])
    have = set(company["resources"])
    resource_overlap = (len(needed & have) / len(needed)) if needed else 0.0

    return (
        industry_match,
        region_match,
        round(size_fit, 10),
        round(activity_score(company), 10),
        round(resource_overlap, 10),
    )


def build_candidate_matrix(companies: Sequence[dict], cards: Sequence[dict]) -> List[List[Tuple[float, ...]]]:
    """按卡片顺序生成候选特征矩阵（cards × companies）。"""
    return [[features(c, card) for c in companies] for card in cards]


def score(feat: Sequence[float], weights: Dict[str, float], bias: float) -> float:
    z = bias
    for name, value in zip(FEATURES, feat):
        z += float(weights[name]) * value
    return _sigmoid(z)


def score_matrix(matrix: List[List[Tuple[float, ...]]], weights: Dict[str, float], bias: float) -> List[List[float]]:
    return [[score(feat, weights, bias) for feat in row] for row in matrix]


def _rankdata(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    n1 = sum(1 for y in labels if y == 1)
    n0 = len(labels) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    ranks = _rankdata(scores)
    rank_sum = sum(ranks[i] for i, y in enumerate(labels) if y == 1)
    return (rank_sum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def confusion(labels: Sequence[int], scores: Sequence[float], threshold: float) -> Dict[str, int]:
    tp = fp = tn = fn = 0
    for y, s in zip(labels, scores):
        pred = 1 if s >= threshold else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def metrics_at(labels: Sequence[int], scores: Sequence[float], threshold: float) -> Dict[str, float | int]:
    cm = confusion(labels, scores, threshold)
    tp, fp, tn, fn = cm["tp"], cm["fp"], cm["tn"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(labels) if labels else 0.0
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "auc": auc(labels, scores),
    }


def threshold_grid(scan_cfg: Dict[str, float]) -> List[float]:
    lo, hi, step = float(scan_cfg["min"]), float(scan_cfg["max"]), float(scan_cfg["step"])
    n = int(round((hi - lo) / step)) + 1
    return [round(lo + i * step, 10) for i in range(n)]


def flatten(
    companies: Sequence[dict],
    cards: Sequence[dict],
    outcomes: Sequence[dict],
    score_rows: Sequence[Sequence[float]],
) -> Tuple[List[int], List[float]]:
    """把 (卡片 × 公司) 的标签与分数按固定顺序摊平成两个等长列表。

    outcomes 为 prepare 步骤产出的历史决策记录，键为 (card_id, company_id)。
    """
    label_map = {(row["card_id"], row["company_id"]): int(row["label"]) for row in outcomes}
    cidx = {c["id"]: i for i, c in enumerate(companies)}
    y: List[int] = []
    s: List[float] = []
    for card_pos, card in enumerate(cards):
        row = score_rows[card_pos]
        for company in companies:
            y.append(label_map[(card["id"], company["id"])])
            s.append(row[cidx[company["id"]]])
    return y, s
