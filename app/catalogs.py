from __future__ import annotations

import csv
import io
from typing import Iterable


def parse_icd_csv(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    for row in reader:
        code = (row.get("code") or "").strip().upper()
        title = (row.get("title") or "").strip()
        if code and title:
            rows.append({"code": code, "title": title})
    return rows


def search_icd_rows(rows: Iterable[dict[str, str]], query: str) -> list[dict[str, str]]:
    q = query.strip().casefold()
    if not q:
        return []
    return [r for r in rows if q in r["code"].casefold() or q in r["title"].casefold()]
