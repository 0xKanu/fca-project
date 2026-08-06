"""Heuristic draft labels for the labelling sample.

Provides a starting point for the labelling step: each sampled document gets a
best-guess label from the taxonomy in data/labelling/TAXONOMY.md, based on
doc_type + title keywords (and the first slice of extracted text when
available). These are DRAFTS — a human must confirm/adjust them in
``data/labelling/sample.csv`` before they are used for training.

Writes ``data/labelling/draft_labels.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from typing import Any

from scraper import config

AMEND_WORDS = ("amends", "amend", "changes", "change", "updates", "update", "modifies", "modify")
NEW_WORDS = ("introduces", "introduce", "creates", "create", "establishes", "establish", "new regime", "new rules")
GUIDANCE_WORDS = ("q&a", "questions and answers", "technical note", "clarif")
NO_CHANGE_WORDS = ("withdraw", "no longer proceeds", "does not intend to proceed", "feedback statement")


def draft_label(rec: dict[str, Any], first_text: str) -> tuple[str, str]:
    """Return (label, basis). Heuristics run in priority order."""
    title = (rec.get("title") or "").lower()
    doc_type = rec.get("doc_type")

    if any(w in title for w in NO_CHANGE_WORDS):
        return "no_change", "title signals withdrawal/no-proceed"

    if "q&a" in title:
        return "guidance", "Q&A title"

    if doc_type == "FG":
        return "guidance", "doc_type=FG"

    if doc_type == "CP":
        if any(w in title for w in ("feedback", "final response", "response to")):
            return "no_change", "CP is a feedback statement"
        return "consultation", "doc_type=CP"

    if doc_type == "HN":
        return "amendment", "doc_type=HN (handbook change)"

    # PS and the generic fallback: prefer the abstract text, then the title.
    blob = " ".join((title, first_text[:600].lower()))
    if any(w in blob for w in AMEND_WORDS):
        return "amendment", "amendment keywords in title/abstract"
    if any(w in blob for w in NEW_WORDS):
        return "new_rule", "new-rule keywords in title/abstract"
    if doc_type == "PS":
        return "new_rule", "doc_type=PS default"
    return "guidance", "untyped default"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft labels for the sample.")
    parser.add_argument(
        "--sample",
        default=os.path.join(config.BASE_DIR, "data", "labelling", "sample.jsonl"),
    )
    args = parser.parse_args()

    with open(args.sample, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]

    drafts = []
    for rec in records:
        stem = (rec.get("reference") and re.sub(r"\W", "_", rec["reference"])) or ""
        text_path = os.path.join(config.TEXT_DIR, f"{stem}.txt")
        first_text = ""
        if os.path.exists(text_path):
            with open(text_path, encoding="utf-8", errors="replace") as tf:
                first_text = tf.read(1500)
        label, basis = draft_label(rec, first_text)
        drafts.append(
            {
                "stem": stem,
                "title": rec.get("title"),
                "doc_type": rec.get("doc_type"),
                "published_date": rec.get("published_date"),
                "draft_label": label,
                "basis": basis,
            }
        )

    out = os.path.join(config.BASE_DIR, "data", "labelling", "draft_labels.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for d in drafts:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    from collections import Counter

    dist = Counter(d["draft_label"] for d in drafts)
    print("\n=== DRAFT LABEL DISTRIBUTION (n=%d) ===" % len(drafts))
    for k, v in sorted(dist.items()):
        print(f"  {k}: {v}")
    print("Wrote:", out)


if __name__ == "__main__":
    main()
