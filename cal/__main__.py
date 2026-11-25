"""允许 `python -m cal ...`。"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
