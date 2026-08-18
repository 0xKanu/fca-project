"""Shared data loading for the classifier comparison."""
from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
TEXT_DIR = DATA / "text"
LABELS_CSV = DATA / "labelling" / "labels.csv"
PRED_DIR = DATA / "predictions"

LABELS = ["new_rule", "amendment", "consultation", "guidance", "no_change"]

# Rows that cannot be reliably labelled/learned from (flagged during labelling).
EXCLUDE_STEMS = {"cryptoasset_regime"}


def load_labels(path: Path = LABELS_CSV) -> dict[str, str]:
    """stem -> label from the canonical labels.csv."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {r["stem"]: r["label"] for r in rows}


def load_meta(path: Path = LABELS_CSV) -> dict[str, dict]:
    """stem -> full record (title, reference, doc_type, label, confidence, ...)."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {r["stem"]: r for r in rows}


def load_text(stem: str, max_chars: int = 2000) -> str:
    """First `max_chars` chars of a document's extracted text (the labelling region)."""
    p = TEXT_DIR / f"{stem}.txt"
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8", errors="replace")
    return t[:max_chars]


def usable_stems() -> list[str]:
    """Stems with both a label and non-empty text, excluding unlearnable rows."""
    labels = load_labels()
    stems = []
    for stem, label in labels.items():
        if stem in EXCLUDE_STEMS:
            continue
        if label not in LABELS:
            continue
        if not load_text(stem):
            continue
        stems.append(stem)
    return stems


def write_predictions(method: str, preds: dict[str, str], conf: dict[str, float] | None = None):
    """Write stem,label[,confidence] CSV to data/predictions/{method}.csv."""
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    out = PRED_DIR / f"{method}.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        if conf:
            w.writerow(["stem", "label", "confidence"])
            for stem in preds:
                w.writerow([stem, preds[stem], f"{conf.get(stem, 0.0):.4f}"])
        else:
            w.writerow(["stem", "label"])
            for stem in preds:
                w.writerow([stem, preds[stem]])
    return out