from __future__ import annotations

from cal import model


def test_auc_perfect_separation() -> None:
    labels = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]
    assert model.auc(labels, scores) == 1.0


def test_auc_reversed_separation() -> None:
    labels = [0, 0, 1, 1]
    scores = [0.9, 0.8, 0.2, 0.1]
    assert model.auc(labels, scores) == 0.0


def test_auc_handles_ties() -> None:
    labels = [0, 1, 0, 1]
    scores = [0.5, 0.5, 0.5, 0.5]
    assert model.auc(labels, scores) == 0.5


def test_metrics_at_threshold() -> None:
    labels = [1, 0, 1, 0]
    scores = [0.9, 0.6, 0.2, 0.1]
    result = model.metrics_at(labels, scores, 0.5)
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["tn"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_threshold_grid_is_inclusive() -> None:
    grid = model.threshold_grid({"min": 0.05, "max": 0.95, "step": 0.05})
    assert len(grid) == 19
    assert grid[0] == 0.05
    assert grid[-1] == 0.95


def test_features_are_deterministic() -> None:
    company = {
        "id": "c1",
        "industry": "智能制造",
        "region": "思明区",
        "employees": 200,
        "resources": ["产线", "仓储"],
        "monthly": [
            {"month": "2025-01", "activity": 0.5, "deals": 1},
            {"month": "2025-02", "activity": 0.7, "deals": 2},
        ],
    }
    card = {
        "id": "s1",
        "industry": "智能制造",
        "region": "湖里区",
        "needed_resources": ["产线"],
        "company_scale": 200,
        "budget_cents": 10000,
    }
    first = model.features(company, card)
    second = model.features(company, card)
    assert first == second
    assert first[0] == 1.0  # industry_match
    assert first[1] == 0.0  # region_match
    assert first[4] == 1.0  # resource_overlap
