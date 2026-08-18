"""Level 1 orchestrator: paginate the FCA search and build the document index.

For each document type, walks paginated search-result pages (start=1, 11, 21,
...), parses each row, filters to the configured date window, dedupes by
reference, and writes the combined index to data/index/ as both JSONL and CSV.

This module only builds the *index* — it deliberately does not download any
PDFs. The user inspects the index before the download phase runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from datetime import date, datetime
from typing import Any

from scraper import config
from scraper.fetch import FetchSession
from scraper.parse_search import in_date_range, parse_search_page

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = config.RESULTS_PER_PAGE
START_OFFSET = 1  # FCA's search pagination is 1-indexed (start=1 -> page 1)


def build_search_url(doc_type_key: str, start: int) -> str:
    """Compose a search-results URL for a doc-type category and pagination offset."""
    params = dict(config.FCA_SEARCH_PARAMS)
    params["category"] = config.DOC_TYPES[doc_type_key]
    params["start"] = str(start)
    from urllib.parse import urlencode

    return f"{config.FCA_BASE_URL}?{urlencode(params)}"


def paginate_category(
    session: FetchSession,
    doc_type: str,
    start: datetime = config.DATE_START,
    end: datetime = config.DATE_END,
) -> list[dict[str, Any]]:
    """Return all in-window records for one document type.

    Stops when a page returns no rows, or as soon as a page's earliest
    (already descending) publication date falls before ``start``.
    """
    collected: list[dict[str, Any]] = []
    start_idx = START_OFFSET

    while True:
        url = build_search_url(doc_type, start_idx)
        try:
            resp = session.get(url)
            rows = parse_search_page(resp.text, doc_type)
        except Exception as exc:  # noqa: BLE001
            # Fetch (and its retries) already made the case; don't let a single
            # flaky page kill the whole index build. Log and move on a page.
            logger.warning("page fetch failed (%s @ %s): %s", doc_type, start_idx, exc)
            break

        if not rows:
            break

        # Results are date-descending. Once an entire page is older than the
        # window, no later page can help — stop. (Rough: first row is newest.)
        first_dt = _parse_dt(rows[0].get("published_date"))
        if first_dt is not None and first_dt < start:
            break

        collected.extend(rows)
        logger.info(
            "type=%s page_start=%s rows=%s cumulative=%s",
            doc_type,
            start_idx,
            len(rows),
            len(collected),
        )
        time.sleep(session.delay)
        start_idx += RESULTS_PER_PAGE

    # Apply the date filter precisely and drop rows too old for the window.
    filtered = [
        r for r in collected if in_date_range(r, start, end)
    ]
    return filtered


def dedupe_by_reference(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate records by (reference). Records without a reference
    are flagged and kept as distinct only if title/landing differ."""
    seen: dict[str, dict] = {}
    for rec in records:
        key = rec.get("reference")
        if key:
            seen.setdefault(key, rec)
        else:
            # No reference: dedupe on landing url if we can.
            url_key = ("url", rec.get("landing_url"))
            seen.setdefault(url_key, rec)
    # Return in insertion order.
    return list(seen.values())


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def write_index(records: list[dict[str, Any]], label: str) -> tuple[str, str]:
    """Write records to JSONL and CSV. Returns (jsonl_path, csv_path)."""
    jsonl_path = os.path.join(config.INDEX_DIR, f"index_{label}.jsonl")
    csv_path = os.path.join(config.INDEX_DIR, f"index_{label}.csv")

    fields = [
        "title",
        "reference",
        "doc_type",
        "doc_type_label",
        "published_date",
        "last_modified",
        "landing_url",
    ]

    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for rec in records:
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(csv_path, "w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fields)
        writer.writeheader()
        for rec in records:
            writer.writerow({f: rec.get(f, "") for f in fields})

    return jsonl_path, csv_path


# --------------------------------------------------------------------------
# Incremental detection (--incremental)
# --------------------------------------------------------------------------

def load_index_jsonl(path: str) -> list[dict[str, Any]]:
    """Load a JSONL index (missing/empty file -> empty list)."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _pub_date(rec: dict[str, Any]) -> date | None:
    """Normalise a record's published_date to a naive date (ISO YYYY-MM-DD)."""
    value = rec.get("published_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return None


def _dedupe_key(rec: dict[str, Any]) -> tuple[str, str]:
    """Stable dedupe/seen key: reference, else landing URL."""
    ref = rec.get("reference")
    if ref:
        return ("ref", ref)
    return ("url", rec.get("landing_url", ""))


def select_incremental(
    new_records: list[dict[str, Any]], existing_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return records that are new: published after the latest existing date
    OR whose reference/URL was not previously seen. Dedupes the result.

    If there is no prior index, every record is new.
    """
    seen: set[tuple[str, str]] = set()
    latest: datetime.date | None = None
    for rec in existing_records:
        seen.add(_dedupe_key(rec))
        d = _pub_date(rec)
        if d is not None and (latest is None or d > latest):
            latest = d

    out: list[dict[str, Any]] = []
    seen_new: set[tuple[str, str]] = set()
    for rec in new_records:
        key = _dedupe_key(rec)
        if key in seen_new:
            continue
        d = _pub_date(rec)
        # New if: reference/URL never seen before, OR a seen reference has been
        # re-published with a date newer than anything we already captured.
        is_new = key not in seen or (
            d is not None and latest is not None and d > latest
        )
        if is_new:
            seen_new.add(key)
            out.append(rec)
    return out


def build_index() -> dict[str, Any]:
    """Run Level 1 for all doc types and return a summary dict."""
    session = FetchSession()
    summary: dict[str, Any] = {}
    all_records: list[dict[str, Any]] = []

    for doc_type in config.DOC_TYPES:
        records = paginate_category(session, doc_type)
        records = dedupe_by_reference(records)
        all_records.extend(records)
        summary[doc_type] = {
            "count": len(records),
            "sample": records[:5],
        }
        logger.info("type=%s -> %d records", doc_type, len(records))

    # Global dedup: a document can surface under more than one category (or
    # twice on different pages), so references must be unique across the whole
    # index, not just within each category's own list.
    all_records = dedupe_by_reference(all_records)

    jsonl_path, csv_path = write_index(all_records, "all")
    summary["_files"] = {"jsonl": jsonl_path, "csv": csv_path}
    summary["_total"] = len(all_records)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the FCA document index.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="only index records newer than the existing index_all.jsonl "
        "(or with a reference not already seen); writes data/index/index_new.* "
        "and appends to index_all.*; exits 0 with a message if nothing is new",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
    )

    if args.incremental:
        existing = load_index_jsonl(os.path.join(config.INDEX_DIR, "index_all.jsonl"))
        new_records = []
        session = FetchSession()
        for doc_type in config.DOC_TYPES:
            new_records.extend(paginate_category(session, doc_type))
        fresh = dedupe_by_reference(new_records)
        delta = select_incremental(fresh, existing)
        if not delta:
            print("No new publications.")
            return
        combined = existing + delta
        write_index(combined, "all")
        write_index(delta, "new")
        print("\n=== INCREMENTAL INDEX ===")
        print(f"existing: {len(existing)}  new: {len(delta)}  total: {len(combined)}")
        print("New:", ", ".join(r.get("reference") or r.get("landing_url", "") for r in delta))
        print("Wrote:", os.path.join(config.INDEX_DIR, "index_new.jsonl"))
        return

    summary = build_index()

    print("\n=== INDEX BUILD SUMMARY ===")
    for doc_type, info in summary.items():
        if doc_type.startswith("_"):
            continue
        print(f"{doc_type}: {info['count']} records")
    print("Total:", summary["_total"])
    print("Wrote:", summary["_files"])


if __name__ == "__main__":
    main()