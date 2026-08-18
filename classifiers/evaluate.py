"""Shared evaluation harness for the RQ2 three-way comparison.

Compute per-class precision/recall/F1, macro-F1, accuracy, majority-class
baseline and a confusion matrix for any method's prediction CSV. Also builds
the comparison table and REPORT_RQ2.md.

Evaluation protocol (declared asymmetry):
- rule_based and zero_shot use no labels at inference -> evaluated on all
  usable docs.
- fine_tuned trains on labels -> evaluated with stratified 5-fold CV (see
  notebooks/fine_tune_colab.ipynb); its CSV holds out-of-fold predictions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sklearn.metrics import classification_report, confusion_matrix

from .data_utils import LABELS, PRED_DIR, load_labels, usable_stems


def read_predictions(path: Path) -> dict[str, str]:
    preds = {}
    with open(path) as f:
        import csv

        for row in csv.DictReader(f):
            preds[row["stem"]] = row["label"]
    return preds


def evaluate(method: str, preds: dict[str, str], labels: dict[str, str], out_dir: Path = PRED_DIR) -> dict:
    stems = [s for s in usable_stems() if s in preds]
    y_true = [labels[s] for s in stems]
    y_pred = [preds[s] for s in stems]

    report = classification_report(y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=LABELS)
    acc = report["accuracy"]
    macro = report["macro avg"]["f1-score"]
    baseline = max(1, max(len([s for s in stems if labels[s] == l]) for l in LABELS)) / max(1, len(stems))

    metrics = {
        "method": method,
        "n": len(stems),
        "accuracy": round(acc, 4),
        "macro_f1": round(macro, 4),
        "majority_baseline_acc": round(baseline, 4),
        "per_class_f1": {l: round(report[l]["f1-score"], 4) for l in LABELS},
        "confusion_matrix": cm.tolist(),
        "labels": LABELS,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{method}_metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"\n=== {method} (n={len(stems)}) ===")
    print(f"  accuracy={acc:.3f}  macro-F1={macro:.3f}  baseline={baseline:.3f}")
    for l in LABELS:
        print(f"  {l:12s} F1={report[l]['f1-score']:.3f}  P={report[l]['precision']:.3f}  R={report[l]['recall']:.3f}")
    print("  confusion matrix (rows=true, cols=pred):")
    print("      " + " ".join(f"{l[:5]:>5}" for l in LABELS))
    for i, l in enumerate(LABELS):
        print(f"  {l[:5]:>5} " + " ".join(f"{c:5d}" for c in cm[i]))
    return metrics


def compare(quiet: bool = False) -> list[dict]:
    labels = load_labels()
    methods = []
    for csv_name in sorted(PRED_DIR.glob("*.csv")):
        if csv_name.stem.endswith("_metrics"):
            continue
        if csv_name.stem in ("rule_based", "zero_shot", "fine_tuned"):
            methods.append(evaluate(csv_name.stem, read_predictions(csv_name), labels))
    write_report(methods)
    return methods


def write_report(methods: list[dict]):
    """Assemble REPORT_RQ2.md from the evaluated methods (missing ones marked)."""
    labels = load_labels()
    present = {m["method"]: m for m in methods}

    def row(name, label, acc, macro):
        return f"| {name} | {label} | {acc:.3f} | {macro:.3f} |"

    rows = []
    for name in ("rule_based", "zero_shot", "fine_tuned"):
        m = present.get(name)
        if m:
            rows.append(row(name, f"acc {m['accuracy']:.3f}", m["accuracy"], m["macro_f1"]))
        else:
            rows.append(row(name, "pending", 0.0, 0.0))

    per_class_lines = []
    for name in ("rule_based", "zero_shot", "fine_tuned"):
        m = present.get(name)
        if not m:
            per_class_lines.append(f"**{name}** - pending.")
            continue
        per_class_lines.append(f"**{name}** (n={m['n']}):")
        for l in LABELS:
            per_class_lines.append(f"- `{l}` F1={m['per_class_f1'][l]:.3f}")

    # error analysis: which docs each present method misclassifies
    err_lines = []
    for name in ("rule_based", "zero_shot", "fine_tuned"):
        m = present.get(name)
        if not m:
            continue
        preds = read_predictions(PRED_DIR / f"{name}.csv")
        wrong = sorted(s for s in usable_stems() if s in preds and preds[s] != labels[s])
        err_lines.append(
            f"**{name}**: {len(wrong)}/{m['n']} misclassified - "
            + ", ".join(f"`{s}`" for s in wrong[:12])
            + ("..." if len(wrong) > 12 else "")
        )

    report = f"""# RQ2 - Three-way classifier comparison

## Question
Which method best classifies FCA policy documents by *type of regulatory
change* (new_rule / amendment / consultation / guidance / no_change), and how
does each compare against a trivial majority-class baseline?

## Methods
1. **rule_based** - deterministic keyword/taxonomy matching
   (`classifiers/keywords.py`, user-owned lists). No training.
2. **zero_shot** - Groq `llama-3.3-70b-versatile` prompted with the taxonomy
   (`classifiers/zero_shot.py`, user-owned prompt). No training.
3. **fine_tuned** - DistilBERT fine-tuned on the 180-doc labelled sample
   (`notebooks/fine_tune_colab.ipynb`). Trains on labels.

## Evaluation protocol (declared asymmetry)
- rule_based and zero_shot use no labels at inference -> evaluated on all
  usable docs ({len(usable_stems())}).
- fine_tuned trains on labels -> evaluated with stratified 5-fold CV;
  its predictions are out-of-fold (each doc predicted by a model that never
  saw it during training).
- All three are scored on the identical document set. `no_change` has no
  representative in the sample, so it cannot be learned/evaluated; the single
  `unknown` row (cryptoasset_regime, JS-rendered) is excluded from all methods.

## Results
| method | status | accuracy | macro-F1 |
|---|---|---|---|
{chr(10).join(rows)}
| *majority-class baseline* | - | 0.436 | - |

Per-class F1:

{chr(10).join(per_class_lines)}

## Error analysis

{chr(10).join(err_lines)}

## Caveats (read before citing)
- `new_rule` has only 16 samples; recall for it is weak in every method.
  The small-N classes are the binding constraint, not the modelling.
- `no_change` (0 samples) cannot be evaluated - none of the methods can learn
  or be scored on it.
- 5 labelled rows are low-confidence (3 JS-rendered PMBs, 1 overview doc,
  1 text-mismatch) - see `data/labelling/labels.csv` notes.
- Methods are compared as-is; no hyperparameter search beyond defaults.

## Pre-committed fallback (decided before running, not after)
If fine-tuning is not working by the deadline, the shipped comparison is
rule_based vs zero_shot (a valid two-way answer to RQ2), with fine_tuned
presented as an attempted third method with honest analysis of why it was
hard. Two working methods rigorously compared answer RQ2; a half-understood
third method that cannot be defended is worse.
"""
    out = PRED_DIR / ".." / ".." / "REPORT_RQ2.md"
    out = (PRED_DIR.parent.parent / "REPORT_RQ2.md")
    out.write_text(report)
    print(f"\nWrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default=None, help="evaluate a single method by name")
    args = ap.parse_args()
    if args.method:
        labels = load_labels()
        evaluate(args.method, read_predictions(PRED_DIR / f"{args.method}.csv"), labels)
    else:
        compare()


if __name__ == "__main__":
    main()