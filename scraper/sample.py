"""Stratified random sampling of the corpus for labelling.

Draws a reproducible, stratified sample of ``--size`` captured documents
(those with an artifact in data/pdfs|html), stratified by doc_type (PS/CP/FG/HN)
and publication year, so the label set mirrors the corpus instead of the
classifier learning type distribution.

Writes ``data/labelling/sample.csv`` (labeller-friendly) and
``data/labelling/sample.jsonl`` (programmatic) with an empty ``label`` column.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse
from typing import Any

from scraper import config

SEED = 42


def captured_stems() -> set[str]:
    """Stems of records that have a captured artifact (pdf or html)."""
    stems: set[str] = set()
    for p in glob.glob(os.path.join(config.METADATA_DIR, "*.json")):
        try:
            sidecar = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        filename = sidecar.get("filename")
        if filename:
            stems.add(os.path.splitext(filename)[0])
    return stems


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(os.path.join(config.INDEX_DIR, "index_all.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def allocate(strata_counts: Counter, size: int) -> dict[str, int]:
    """Proportional allocation with a floor of 1 per non-empty stratum."""
    total = sum(strata_counts.values())
    result: dict[str, int] = {}
    for key, n in strata_counts.items():
        result[key] = max(1, round(size * n / total))
    over = sum(result.values()) - size
    # Trim the excess from the largest strata.
    for key in sorted(result, key=lambda k: -result[k]):
        if over <= 0:
            break
        if result[key] > 1:
            result[key] -= 1
            over -= 1
    return result


def draw_sample(
    records: list[dict[str, Any]], size: int, seed: int = SEED
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    captured = captured_stems()

    def stem(rec: dict) -> str:
        ref = rec.get("reference")
        if ref:
            return re.sub(r"\W", "_", ref)
        base = os.path.splitext(os.path.basename(urlparse(rec.get("landing_url") or "").path))[0]
        return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "doc"

    eligible = [r for r in records if stem(r) in captured]
    strata = Counter((r.get("doc_type"), (r.get("published_date") or "")[:4]) for r in eligible)
    alloc = allocate(strata, size)

    sample: list[dict[str, Any]] = []
    by_stratum: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in eligible:
        by_stratum[(r.get("doc_type"), (r.get("published_date") or "")[:4])].append(r)

    for key, count in alloc.items():
        pool = by_stratum.get(key, [])
        sample.extend(rng.sample(pool, min(count, len(pool))))

    rng.shuffle(sample)
    return sample


def write_sample(sample: list[dict[str, Any]]) -> tuple[str, str]:
    def stem(rec: dict) -> str:
        ref = rec.get("reference")
        if ref:
            return re.sub(r"\W", "_", ref)
        base = os.path.splitext(os.path.basename(urlparse(rec.get("landing_url") or "").path))[0]
        return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "doc"

    labelling_dir = os.path.join(config.BASE_DIR, "data", "labelling")
    os.makedirs(labelling_dir, exist_ok=True)
    csv_path = os.path.join(labelling_dir, "sample.csv")
    jsonl_path = os.path.join(labelling_dir, "sample.jsonl")

    fields = ["stem", "title", "reference", "doc_type", "published_date", "label", "notes"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for rec in sample:
            writer.writerow(
                {
                    "stem": stem(rec),
                    "title": rec.get("title"),
                    "reference": rec.get("reference") or "",
                    "doc_type": rec.get("doc_type"),
                    "published_date": rec.get("published_date") or "",
                    "label": "",
                    "notes": "",
                }
            )
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in sample:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return csv_path, jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a stratified labelling sample.")
    parser.add_argument("--size", type=int, default=180)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    records = load_records()
    sample = draw_sample(records, args.size, args.seed)
    csv_path, jsonl_path = write_sample(sample)

    dist = Counter((r["doc_type"], (r.get("published_date") or "")[:4]) for r in sample)
    print(f"\n=== SAMPLE SUMMARY (n={len(sample)}) ===")
    for key in sorted(dist):
        print(f"  {key[0]} {key[1]}: {dist[key]}")
    print(f"Wrote: {csv_path}\n       {jsonl_path}")


if __name__ == "__main__":
    main()
