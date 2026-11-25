from __future__ import annotations

from pathlib import Path

import pytest

from cal.config import DEFAULTS, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_are_merged(tmp_path: Path) -> None:
    config = tmp_path / "c.yaml"
    config.write_text("seed: 7\n", encoding="utf-8")
    cfg = load_config(config)
    assert cfg["seed"] == 7
    assert cfg["data"]["companies"] == DEFAULTS["data"]["companies"]
    assert cfg["data"]["months"] == DEFAULTS["data"]["months"]


def test_invalid_seed_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text("seed: not-a-number\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config)


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text("eval:\n  threshold: 1.5\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config)


def test_repository_config_is_valid() -> None:
    cfg = load_config(ROOT / "cal.yaml")
    assert cfg["data"]["companies"] == 300
    assert cfg["data"]["months"] == 24
    assert cfg["data"]["demand_cards"] == 200
    assert sorted(cfg["model"]["weights"]) == [
        "activity",
        "industry_match",
        "region_match",
        "resource_overlap",
        "size_fit",
    ]
