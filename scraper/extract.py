"""Text extraction: PDF + HTML captures -> plain-text files.

Reads each sidecar in data/metadata/ (the join key is the file stem, identical
to data/pdf|html), extracts clean text and writes data/text/<stem>.txt.

PDFs use pypdf with an empty-password decrypt (the FCA encrypts its PDFs with
AES; ``cryptography`` is required). HTML snapshots are cleaned of navigation,
header/footer and boilerplate before text is pulled.

Idempotent: existing .txt files are skipped. Low-character PDFs (possible
scanned/image-only pages) are flagged in the run summary, not silently dropped.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup

from scraper import config

logger = logging.getLogger(__name__)

# Below this many chars a PDF text layer is suspicious (scanned/image-only).
LOW_TEXT_CHARS = 500
# Tags that carry chrome, not document content.
NOISE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "button"}
NOISE_CLASS_RE = re.compile(r"\b(region|navigation|breadcrumb|skip|social|share)\b", re.I)


def extract_pdf_text(path: str) -> str:
    """Return the full text of ``path``, decrypting empty-password PDFs."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted:
        reader.decrypt("")
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n".join(pages)


def extract_html_text(path: str) -> str:
    """Return the readable text of an HTML snapshot, minus page chrome."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return html_to_text(f.read())


def html_to_text(html: str) -> str:
    """Clean an HTML string down to readable text, removing page chrome."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for el in soup.select("[class]"):
        classes = (el.attrs or {}).get("class", [])
        if NOISE_CLASS_RE.search(" ".join(classes)):
            el.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_file(sidecar: dict) -> tuple[bool, str]:
    """Extract text for one sidecar. Returns (ok, message)."""
    filename = sidecar.get("filename") or ""
    stem = os.path.splitext(filename)[0]
    out_path = os.path.join(config.TEXT_DIR, f"{stem}.txt")
    if os.path.exists(out_path):
        return True, f"skipped (exists): {stem}.txt"

    fmt = sidecar.get("format") or ("html" if filename.endswith(".html") else "pdf")
    src_dir = config.HTML_DIR if fmt == "html" else config.PDFS_DIR
    src_path = os.path.join(src_dir, filename)
    if not os.path.exists(src_path):
        return False, f"source missing: {filename}"

    text = extract_html_text(src_path) if fmt == "html" else extract_pdf_text(src_path)
    if not text:
        return False, f"no text extracted: {filename}"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return True, f"{len(text):,} chars -> {stem}.txt"


def run_extract() -> dict[str, Any]:
    stats = {"extracted": 0, "skipped": 0, "failed": 0, "low_text": []}
    sidecars = sorted(
        glob.glob(os.path.join(config.METADATA_DIR, "*.json")),
        key=lambda p: os.path.basename(p),
    )
    for sidecar_path in sidecars:
        try:
            sidecar = json.load(open(sidecar_path, encoding="utf-8"))
            ok, msg = extract_file(sidecar)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, f"unexpected error: {exc}"

        if ok:
            if msg.startswith("skipped"):
                stats["skipped"] += 1
            else:
                stats["extracted"] += 1
                m = re.match(r"([\d,]+) chars", msg)
                if m and int(m.group(1).replace(",", "")) < LOW_TEXT_CHARS:
                    stats["low_text"].append(os.path.splitext(sidecar.get("filename", ""))[0])
        else:
            stats["failed"] += 1
            logger.warning("extract failed: %s", msg)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract plain text from captures.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    stats = run_extract()
    print("\n=== EXTRACT SUMMARY ===")
    for k, v in stats.items():
        if k == "low_text":
            print(f"low_text (scanned?): {len(v)} {v[:10]}")
        else:
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
