"""Liddell-Scott-Jones lexicon lookup by Strong's number."""
import json
from functools import lru_cache
from pathlib import Path

_LSJ_PATH = Path(__file__).parent / "lsj.json"


@lru_cache(maxsize=1)
def _load_lsj() -> dict:
    if not _LSJ_PATH.exists():
        return {}
    return json.loads(_LSJ_PATH.read_text(encoding="utf-8"))


def get_lsj_entry(strongs_num: str) -> str | None:
    """Return LSJ entry text for a Strong's number, or None if not found."""
    return _load_lsj().get(strongs_num, {}).get("entry")
