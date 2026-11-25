"""SHA-256 与确定性 JSON 序列化。

确定性规则：键排序、固定缩进、UTF-8、LF 换行、浮点统一保留 10 位小数。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CHUNK = 1024 * 1024


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text_normalized(path: str | Path) -> str:
    """按规范化文本哈希（CRLF/CR → LF，UTF-8）。

    避免同一份配置在 Windows（CRLF）与 Linux CI（LF）下哈希不同，
    保证"配置哈希"跨平台一致。
    """
    text = Path(path).read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_json(obj: Any, indent: int = 2) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=indent) + "\n"


def write_canonical_json(path: str | Path, obj: Any, indent: int = 2) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(canonical_json(obj, indent), encoding="utf-8", newline="\n")
    return p


def write_jsonl(path: str | Path, rows) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            fh.write("\n")
    return p


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list:
    out = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def r10(value: float) -> float:
    """统一浮点精度，消除末位噪声（保证跨运行逐字节一致）。"""
    return round(float(value), 10)
