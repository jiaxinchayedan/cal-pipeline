"""回归测试：配置哈希必须与行尾、缩进、注释无关，只与语义内容有关。

背景：本仓库首轮 CI 曾因本地 cal.yaml 为 CRLF、CI 检出为 LF，
导致 config_sha256 不同、黄金值比对失败。现在改为对解析后的配置做语义哈希。
"""
from __future__ import annotations

from pathlib import Path

from cal.config import load_config
from cal.hashing import canonical_json, sha256_json

BASE = "seed: 1\ndata:\n  companies: 3\n"


def _cfg(tmp_path: Path, name: str, text: str, newline: str = "\n"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline=newline)
    return load_config(path)


def test_semantic_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf = _cfg(tmp_path, "lf.yaml", BASE, "\n")
    crlf = _cfg(tmp_path, "crlf.yaml", BASE.replace("\n", "\r\n"), "")
    assert sha256_json(lf) == sha256_json(crlf)


def test_semantic_hash_ignores_comments_and_indentation(tmp_path: Path) -> None:
    plain = _cfg(tmp_path, "plain.yaml", BASE)
    annotated = _cfg(
        tmp_path,
        "annotated.yaml",
        "# 这是一行注释\nseed: 1\ndata:\n    companies: 3   # 缩进与注释都不应影响哈希\n",
    )
    assert sha256_json(plain) == sha256_json(annotated)


def test_semantic_hash_detects_value_changes(tmp_path: Path) -> None:
    base = _cfg(tmp_path, "a.yaml", BASE)
    changed = _cfg(tmp_path, "b.yaml", BASE.replace("companies: 3", "companies: 4"))
    assert sha256_json(base) != sha256_json(changed)


def test_canonical_json_is_key_order_independent() -> None:
    first = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    second = canonical_json({"a": {"c": 3, "d": 2}, "b": 1})
    assert first == second
    assert first.endswith("\n")
