"""回归测试：配置哈希必须与行尾无关（Windows CRLF vs Linux CI LF）。

背景：本仓库首轮 CI 曾因本地 cal.yaml 为 CRLF、CI 检出为 LF，
导致 config_sha256 不同、黄金值比对失败。修复方式为规范化文本哈希。
"""
from __future__ import annotations

from pathlib import Path

from cal.hashing import canonical_json, sha256_file, sha256_text_normalized

LF_TEXT = "seed: 1\ndata:\n  companies: 3\n"


def _write(path: Path, text: str, newline: str) -> Path:
    path.write_text(text, encoding="utf-8", newline=newline)
    return path


def test_raw_hash_differs_between_lf_and_crlf(tmp_path: Path) -> None:
    lf = _write(tmp_path / "lf.yaml", LF_TEXT, "\n")
    crlf = _write(tmp_path / "crlf.yaml", LF_TEXT.replace("\n", "\r\n"), "")
    assert sha256_file(lf) != sha256_file(crlf)


def test_normalized_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf = _write(tmp_path / "lf.yaml", LF_TEXT, "\n")
    crlf = _write(tmp_path / "crlf.yaml", LF_TEXT.replace("\n", "\r\n"), "")
    cr_only = _write(tmp_path / "cr.yaml", LF_TEXT.replace("\n", "\r"), "")
    assert sha256_text_normalized(lf) == sha256_text_normalized(crlf)
    assert sha256_text_normalized(lf) == sha256_text_normalized(cr_only)


def test_normalized_hash_still_detects_real_changes(tmp_path: Path) -> None:
    base = _write(tmp_path / "a.yaml", LF_TEXT, "\n")
    changed = _write(tmp_path / "b.yaml", LF_TEXT.replace("companies: 3", "companies: 4"), "\n")
    assert sha256_text_normalized(base) != sha256_text_normalized(changed)


def test_canonical_json_is_key_order_independent() -> None:
    first = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    second = canonical_json({"a": {"c": 3, "d": 2}, "b": 1})
    assert first == second
    assert first.endswith("\n")
