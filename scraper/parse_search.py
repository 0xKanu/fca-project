"""Level 1 parser for the FCA publications search-results page.

Converts a paginated search page into structured records
``{title, reference, doc_type, published_date, last_modified, landing_url}``.

Selectors were derived by inspecting the live page on 2026-08-05. The result
list is a flat <li class="search-item"> sequence; the reference number is
embedded at the start of the title (e.g. "PS25/20").
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ITEM_SELECTOR = "li.search-item"
TITLE_SELECTOR = "h3.search-item__title a.search-item__clickthrough"
TYPE_SELECTOR = "p.meta-item.type"
PUBLISHED_SELECTOR = "p.meta-item.published-date"
MODIFIED_SELECTOR = "p.meta-item.modified-date"

# Ref like "PS25/20" or "CP 26/11" embedded at the start of the title. The
# optional space matches titles that print "CP 26/11: ...".
_REF_RE = re.compile(r"\b(?P<ref>(?:PS|CP|FG|HN)\s?\d{2}/\d+)\b")

# Date-bearing meta line: "Published: 29/04/2026"
_DMY_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def parse_search_page(html: str, doc_type: str) -> list[dict[str, Any]]:
    """Parse a single search-results page into a list of record dicts."""
    soup = BeautifulSoup(html, "lxml")
    records: list[dict[str, Any]] = []

    for item in soup.select(ITEM_SELECTOR):
        title_el = item.select_one(TITLE_SELECTOR)
        title = title_el.get_text(strip=True) if title_el else ""
        landing_url = title_el.get("href") if title_el else None

        match = _REF_RE.search(title)
        raw_ref = match.group("ref") if match else None
        # Normalise "CP 26/11" -> "CP26/11" so it dedupes and names files
        # consistently.
        reference = raw_ref.replace(" ", "") if raw_ref else None
        # Annex/sub-document records (e.g. "CP26/6: Annex 2 ...") legitimately
        # begin with the *parent* reference but are separate files (often .xlsx
        # or an annex PDF). Without this guard they'd collide with the parent
        # doc and dedupe it out of the index. Treat them as reference-less so
        # they get a stable URL-slug key instead.
        if raw_ref and _is_sub_document(title, landing_url):
            reference = None

        published_el = item.select_one(PUBLISHED_SELECTOR)
        modified_el = item.select_one(MODIFIED_SELECTOR)
        published_date = (
            _parse_date(published_el.get_text()) if published_el else None
        )
        last_modified = _parse_date(modified_el.get_text()) if modified_el else None

        type_label_el = item.select_one(TYPE_SELECTOR)
        doc_type_label = (
            type_label_el.get_text(strip=True) if type_label_el else ""
        )

        records.append(
            {
                "title": title,
                "reference": reference,
                "doc_type": doc_type,
                "doc_type_label": doc_type_label,
                "published_date": (
                    published_date.isoformat() if published_date else None
                ),
                "last_modified": (
                    last_modified.isoformat() if last_modified else None
                ),
                "landing_url": landing_url,
            }
        )

    return records


def _parse_date(cell: str) -> date | None:
    """Parse a string like 'Published: 29/04/2026' into a date."""
    match = _DMY_RE.search(cell)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _is_sub_document(title: str, landing_url: str | None) -> bool:
    """True if a record is an annex/appendix/attachment rather than the main
    document (they share the parent's reference prefix but are separate files)."""
    if not landing_url:
        return False
    path = landing_url.rsplit("/", 1)[-1].lower()
    ext = os.path.splitext(path)[1]
    if ext and ext != ".pdf":
        return True
    if re.search(r"(annex|appendix|template)", path, re.I):
        return True
    if re.search(r"\b(annex|appendix|technical annex)\b", title, re.I):
        return True
    return False


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def in_date_range(
    record: dict[str, Any],
    start: datetime,
    end: datetime,
) -> bool:
    """True if the record's publication date falls within [start, end]."""
    dt = _parse_dt(record.get("published_date"))
    if dt is None:
        # No reliable date: drop and count separately so nothing sneaks in.
        return False
    return start <= dt <= end
