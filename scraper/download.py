"""Levels 2+3 download: resolve each index record to an asset and capture it.

Behaviour:
- Idempotent: a file already present is skipped (resumes cleanly).
- Resilient: failures are logged per record, never fatal to the run.
- Requests go through the rate-limited FetchSession.
- Every captured document gets a JSON sidecar under data/metadata/.

Resolution order (see ``resolve_pdf_asset``):
  1. a landing URL that already ends in ``.pdf``   -> download directly
  2. a .pdf link on the landing page (same host)   -> download
  3. predictable /publication/{type}/{ref}.pdf URL (only if a real PDF)
  4. an external "Read" link (joint FCA/PRA, FCA/gov.uk) -> its PDF
  5. otherwise the page is HTML-only               -> save an .html snapshot

Non-PDF attachments (e.g. CP annex .xlsx tables) are logged as excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from scraper import config
from scraper.fetch import FetchSession
from scraper.parse_landing import (
    extract_pdf_url,
    extract_primary_pdf,
    external_read_link,
)

logger = logging.getLogger(__name__)

NON_PDF_EXT = {".xlsx", ".xls", ".csv", ".ods", ".docx", ".doc"}


def obj_stem(record: dict) -> str:
    """Stable filename stem: reference if available, else the URL slug."""
    ref = record.get("reference")
    if ref:
        return re.sub(r"\W", "_", ref)
    path = urlparse(record.get("landing_url") or "").path
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    return base or "doc"


def construct_pdf_url(record: dict) -> str | None:
    """Build the predictable /publication/{folder}/{ref}.pdf URL, if applicable."""
    from scraper.parse_landing import TYPE_PDF_PATH

    ref = record.get("reference")
    folder = TYPE_PDF_PATH.get(record.get("doc_type") or "")
    if not ref or not folder:
        return None
    slug = ref.lower().replace(" ", "")
    if "/" in slug:
        year_part, num_part = slug.split("/", 1)
        slug = f"{year_part}-{num_part}"
    return f"{config.FCA_PUBLICATION_BASE}/publication/{folder}{slug}.pdf"


def resolve_pdf_asset(session: FetchSession, record: dict) -> dict:
    """Resolve a record to a concrete, downloadable asset dict."""
    landing = record.get("landing_url") or ""
    ext = os.path.splitext(urlparse(landing).path)[1].lower()

    if ext == ".pdf":
        return {"kind": "pdf", "url": landing, "name": obj_stem(record) + ".pdf"}

    if ext in NON_PDF_EXT:
        return {"kind": "excluded", "reason": f"non-PDF attachment ({ext})"}

    page = session.get(landing)

    # PDF hosted on the same FCA site (skipping appendix/technical-notice links).
    local = extract_primary_pdf(page.text, landing, record, exclude_appendix=True)
    if local:
        return {"kind": "pdf", "url": local, "name": obj_stem(record) + ".pdf"}

    # Predictable type-folder URL, only if it really returns a PDF.
    constructed = construct_pdf_url(record)
    if constructed:
        try:
            probe = session.get(constructed)
            if probe.content.lstrip().startswith(b"%PDF"):
                return {
                    "kind": "pdf",
                    "url": constructed,
                    "name": obj_stem(record) + ".pdf",
                }
        except Exception:  # noqa: BLE001
            pass

    # External "Read" link to a joint FCA/PRA or FCA/gov.uk publication.
    ext_link = external_read_link(page.text, landing, record)
    if ext_link:
        try:
            ext_page = session.get(ext_link)
            ext_pdf = extract_primary_pdf(ext_page.text, ext_link, record, exclude_appendix=True)
            if ext_pdf:
                return {
                    "kind": "pdf",
                    "url": ext_pdf,
                    "name": obj_stem(record) + ".pdf",
                    "source": "external",
                    "external_landing": ext_link,
                }
            # BoE/gov.uk often render the main document as HTML with only
            # annexes as PDFs — capture the external page as an HTML snapshot.
            return {
                "kind": "html",
                "url": ext_link,
                "name": obj_stem(record) + ".html",
                "source": "external",
                "external_landing": ext_link,
                "page": ext_page,
            }
        except Exception:  # noqa: BLE001
            pass

    # HTML-only publication: capture the rendered page.
    return {
        "kind": "html",
        "url": landing,
        "name": obj_stem(record) + ".html",
        "page": page,
    }


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def load_index(path: str) -> list[dict]:
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_log(label: str, record: dict, message: str) -> None:
    path = os.path.join(config.LOGS_DIR, label)
    with open(path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps({"record": record, "message": message}, ensure_ascii=False)
            + "\n"
        )


def log_excluded_if_new(record: dict, message: str) -> None:
    """Append to excluded.jsonl only if this record isn't logged already.

    The log is append-mode across runs; without the guard, re-running the
    downloader duplicates exclusion entries (30 lines for 15 records).
    """
    path = os.path.join(config.LOGS_DIR, "excluded.jsonl")
    landing = record.get("landing_url")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line)["record"].get("landing_url") == landing:
                        return
                except Exception:  # noqa: BLE001
                    continue
    append_log("excluded.jsonl", record, message)


def _write_resource(
    record: dict,
    asset: dict,
    content: bytes,
    downloaded_at: str,
) -> str:
    """Write ``content`` to the right location and emit a sidecar. Returns msg."""
    filename = asset["name"]
    fmt = "html" if asset["kind"] == "html" else "pdf"
    out_dir = config.HTML_DIR if fmt == "html" else config.PDFS_DIR
    out_path = os.path.join(out_dir, filename)

    if os.path.exists(out_path):
        return f"skipped (exists): {filename}"

    with open(out_path, "wb") as f:
        f.write(content)

    stem = os.path.splitext(filename)[0]
    sidecar = {
        "title": record.get("title"),
        "reference": record.get("reference"),
        "doc_type": record.get("doc_type"),
        "published_date": record.get("published_date"),
        "last_modified": record.get("last_modified"),
        "landing_url": record.get("landing_url"),
        "source": asset.get("source", "local"),
        "external_landing": asset.get("external_landing"),
        "url": asset.get("url"),
        "format": fmt,
        "filename": filename,
        "sha256": _sha256_bytes(content),
        "downloaded_at": downloaded_at,
    }
    sidecar_path = os.path.join(config.METADATA_DIR, f"{stem}.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2, ensure_ascii=False)

    return f"downloaded ({fmt}): {filename}"


def process_record(
    session: FetchSession,
    record: dict,
    downloaded_at: str,
) -> tuple[bool, str]:
    """Resolve and capture one record. Returns (success, message)."""
    # Idempotency: a record is done once ANY artifact exists for its stem.
    # Checking here (before resolution) prevents a later run from re-resolving
    # and re-formatting an already-captured record.
    stem = obj_stem(record)
    if (
        os.path.exists(os.path.join(config.PDFS_DIR, f"{stem}.pdf"))
        or os.path.exists(os.path.join(config.HTML_DIR, f"{stem}.html"))
        or os.path.exists(os.path.join(config.METADATA_DIR, f"{stem}.json"))
    ):
        return True, f"skipped (exists): {stem}"

    try:
        asset = resolve_pdf_asset(session, record)
    except Exception as exc:  # noqa: BLE001
        return False, f"resolve failed: {exc}"

    if asset["kind"] == "excluded":
        log_excluded_if_new(record, asset["reason"])
        return False, f"excluded: {asset['reason']}"

    if asset["kind"] == "html":
        content = asset["page"].content
    else:
        try:
            content = session.get(asset["url"]).content
        except Exception as exc:  # noqa: BLE001
            return False, f"download failed: {exc}"

    if asset["kind"] == "pdf" and not content.lstrip().startswith(b"%PDF"):
        return False, "not a PDF in response"

    return True, _write_resource(record, asset, content, downloaded_at)


def run_download(records: list[dict], session: FetchSession | None = None) -> dict:
    session = session or FetchSession()
    stats = {"downloaded": 0, "html": 0, "excluded": 0, "skipped": 0, "failed": 0}
    downloaded_at = datetime.now(timezone.utc).isoformat()
    total = len(records)

    for i, rec in enumerate(records, 1):
        try:
            ok, msg = process_record(session, rec, downloaded_at)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, f"unexpected error: {exc}"

        if ok:
            if msg.startswith("skipped"):
                stats["skipped"] += 1
            elif "downloaded (html)" in msg:
                stats["html"] += 1
            else:
                stats["downloaded"] += 1
        else:
            if msg.startswith("excluded"):
                stats["excluded"] += 1
            else:
                stats["failed"] += 1
                cat = "no_pdf" if ("no PDF" in msg or "resolve failed" in msg) else "failures"
                append_log(f"{cat}.jsonl", rec, msg)
                logger.info(
                    "%d/%d [%s] %s",
                    i,
                    total,
                    rec.get("reference") or obj_stem(rec),
                    msg,
                )

        if i % 10 == 0:
            logger.info("progress %d/%d", i, total)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download FCA publications from the index."
    )
    parser.add_argument(
        "--index",
        default=os.path.join(config.INDEX_DIR, "index_all.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    records = load_index(args.index)
    if args.limit:
        records = records[: args.limit]

    summary = run_download(records)

    print("\n=== DOWNLOAD SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()