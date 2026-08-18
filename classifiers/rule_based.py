"""Rule-based baseline: keyword/taxonomy matching, no training.

Deterministic. Evaluates on all usable docs (no label leakage). Output:
data/predictions/rule_based.csv  (stem, label, confidence)
"""
from __future__ import annotations

import argparse
import re

from .data_utils import (
    PRED_DIR,
    append_predictions,
    load_meta,
    load_predictions,
    load_text,
    read_stems_file,
    usable_stems,
    write_predictions,
)
from .keywords import DOC_TYPE_DEFAULT, DOC_TYPE_PRIOR, KEYWORDS

_DEFAULT_WEIGHT = 0.8


def score_document(text: str, doc_type: str) -> dict[str, float]:
    """Weighted keyword-hit scores per label, then apply doc_type prior."""
    # Drop the "This relates to Consultation Paper X" boilerplate: it points
    # at a PRIOR CP, not the current document's change type.
    t = re.sub(r"this relates to[^\n]*", " ", text.casefold())
    t = re.sub(r"which relates to[^\n]*", " ", t)
    scores = {label: 0.0 for label in KEYWORDS}
    for label, phrases in KEYWORDS.items():
        total = 0.0
        for phrase, weight in phrases:
            if phrase.casefold() in t:
                total += weight
        scores[label] = total
    prior = DOC_TYPE_PRIOR.get(doc_type, {})
    for label in scores:
        scores[label] *= prior.get(label, 1.0)
    return scores


def classify(text: str, doc_type: str) -> tuple[str, float]:
    """Return (label, confidence) for one document."""
    scores = score_document(text, doc_type)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top, second = ordered[0], ordered[1]
    if top[1] <= 0:
        return DOC_TYPE_DEFAULT.get(doc_type, "amendment"), 0.0
    margin = top[1] - second[1]
    conf = min(1.0, margin / 3.0)
    return top[0], round(conf, 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-chars", type=int, default=2000, help="chars of text to scan")
    ap.add_argument("--out", type=str, default=str(PRED_DIR / "rule_based.csv"))
    ap.add_argument(
        "--stems-file",
        default=None,
        help="newline-separated list of stems to classify (appends to the "
        "existing rule_based.csv, skipping stems already predicted)",
    )
    args = ap.parse_args()

    meta = load_meta()
    if args.stems_file:
        stems = read_stems_file(args.stems_file)
        already = load_predictions("rule_based")
        stems = [s for s in stems if s not in already]
        if not stems:
            print("No new stems to classify (all already predicted).")
            return
    else:
        stems = usable_stems()

    preds, confs = {}, {}
    for stem in stems:
        text = load_text(stem, args.max_chars)
        doc_type = meta.get(stem, {}).get("doc_type", "PS")
        label, conf = classify(text, doc_type)
        preds[stem] = label
        confs[stem] = conf

    if args.stems_file:
        out = append_predictions("rule_based", preds, confs)
    else:
        out = write_predictions("rule_based", preds, confs)
    print(f"Wrote {len(preds)} predictions -> {out}")


if __name__ == "__main__":
    main()