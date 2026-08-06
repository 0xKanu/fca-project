"""Level 2 parser: given a document landing page, extract its primary asset URL.

The FCA renders a "Read <REF> (PDF)" link on article landing pages. Some
landing pages are *collection* pages (multiple linked PDFs); for those we
prioritise the link whose text matches the record's reference, and otherwise
fall back to the first PDF that lives under the folder matching the document
type.

Joint publications (FCA/PRA, or FCA/gov.uk) carry the PDF on an *external*
host and link to it with a "Read <REF>" anchor (e.g.
https://www.bankofengland.co.uk/...). ``external_read_link`` surfaces that
outbound URL so the downloader can follow it.

Selectors were derived by inspecting live pages on 2026-08-05.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Folder under /publication/ that hosts each document type's PDFs.
TYPE_PDF_PATH = {
    "PS": "policy/",
    "CP": "consultation/",
    "FG": "finalised-guidance/",
    "HN": "handbook/",
}


def _normalise_ref(text: str, reference: str | None) -> bool:
    """True if ``reference`` (no spaces) appears in ``text`` (spaces folded)."""
    if not reference:
        return False
    compact = re.sub(r"\s+", "", text)
    return reference.lower() in compact.lower()


def extract_pdf_url(html: str, base_url: str, record: dict) -> str | None:
    """Return a PDF URL hosted on the source site, or None.

    ``exclude_appendix`` drops links that look like annex/appendix files
    (e.g. BoE "ps826app1.pdf"), so the *main* document is preferred.
    """
    return _extract_pdf(html, base_url, record, exclude_appendix=False)


def extract_primary_pdf(
    html: str, base_url: str, record: dict, exclude_appendix: bool = False
) -> str | None:
    """Return the *definitive* PDF for a page, or None if it is ambiguous.

    A PDF is only treated as the page's document when it is clearly primary:
    either a link whose text carries the reference (e.g. "Read PS25/20 (PDF)"),
    or the *only* non-appendix/annex PDF on the page. Multi-document round-up
    pages (Primary Market Bulletins, collection overviews) yield None so the caller
    falls back to an HTML snapshot rather than an arbitrary PDF.
    """
    soup = BeautifulSoup(html, "lxml")
    reference = record.get("reference")
    doc_type = record.get("doc_type")
    folder = TYPE_PDF_PATH.get(doc_type, "")

    candidates: list[tuple[str, str]] = []  # (text, href)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        if not _is_localhost(base_url, href):
            continue
        if exclude_appendix and re.search(
            r"(appendix|/annex|_annex|/app\d|technical notice|/tn-|/technical-)",
            href,
            re.I,
        ):
            continue
        candidates.append((a.get_text(" ", strip=True), href))

    if not candidates:
        return None

    if reference:
        for text, href in candidates:
            if _normalise_ref(text, reference):
                return urljoin(base_url, href)

    if len(candidates) == 1:
        return urljoin(base_url, candidates[0][1])

    if not folder:
        return None

    # Single PDF that lives under the type's publication folder.
    folder_matches = [href for text, href in candidates if f"/{folder}" in href]
    if len(folder_matches) == 1:
        return urljoin(base_url, folder_matches[0])

    return None


def _extract_pdf(html, base_url, record, exclude_appendix):
    soup = BeautifulSoup(html, "lxml")
    reference = record.get("reference")
    doc_type = record.get("doc_type")
    folder = TYPE_PDF_PATH.get(doc_type, "")

    pdf_links: list[tuple[str, str]] = []  # (text, href)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        if not _is_localhost(base_url, href):
            continue
        if exclude_appendix and re.search(
            r"(appendix|/annex|_annex|/app\d|technical notice|/tn-|/technical-)",
            href,
            re.I,
        ):
            continue
        text = a.get_text(" ", strip=True)
        pdf_links.append((text, href))

    if not pdf_links:
        return None

    if reference:
        for text, href in pdf_links:
            if _normalise_ref(text, reference):
                return urljoin(base_url, href)

    if folder:
        for text, href in pdf_links:
            if f"/{folder}" in href:
                return urljoin(base_url, href)

    return urljoin(base_url, pdf_links[0][1])


def external_read_link(html: str, base_url: str, record: dict) -> str | None:
    """Return an external (off-FCA) URL pointed to by a 'Read ...' anchor.

    Strictly prefers a reference-titled or consultation-titled "Read" link
    (e.g. "Read PS26/4", "Read the consultation"). Cross-numbered joint docs
    (e.g. FCA PS24/13 == PRA "Read PS17/24") won't match the FCA reference, so
    we fall back to the first external "Read ..." anchor.
    """
    soup = BeautifulSoup(html, "lxml")
    reference = record.get("reference")
    external_reads: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if _is_localhost(base_url, href):
            continue
        text = a.get_text(" ", strip=True)
        if not text.strip().lower().startswith("read"):
            continue
        low = text.lower()
        external_reads.append(urljoin(base_url, href))
        if "consultation" in low or _normalise_ref(text, reference):
            return external_reads[-1]
    return external_reads[0] if external_reads else None


def _is_localhost(base_url: str, href: str) -> bool:
    """True if ``href`` targets the same site as ``base_url``."""
    parsed = urlparse(href)
    if not parsed.netloc:
        return True  # relative link -> same host
    return parsed.netloc == urlparse(base_url).netloc