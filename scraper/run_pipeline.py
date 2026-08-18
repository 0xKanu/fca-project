"""One-command pipeline: detect -> capture -> extract -> classify new FCA docs.

Chains the existing CLI stages as subprocesses (each keeps its own per-record
error handling; a failing stage is logged and the pipeline continues rather
than halting):

    index --incremental  ->  download --index index_new.jsonl  ->  extract
    ->  predict (default zero_shot)  ->  [--upload to GCS]

For each newly detected document it appends a latency row to
data/predictions/latency_log.jsonl (RQ3):
    {stem, reference, published_date, detected_at, classified_at}

Timestamps are UTC ISO-8601. ``detected_at`` is recorded when the index stage
completes; ``classified_at`` when the predict stage completes, so per-document
latency is at *stage* granularity (the batch completes together), not
per-call granularity.

Run:
    python -m scraper.run_pipeline [--method rule_based] [--upload] \
        [--bucket gs-bucket --prefix fca-corpus]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from scraper import config
from scraper.download import obj_stem

INDEX_NEW = os.path.join(config.INDEX_DIR, "index_new.jsonl")
STEMS_FILE = os.path.join(config.INDEX_DIR, "index_new_stems.txt")
LATENCY_LOG = os.path.join(config.BASE_DIR, "data", "predictions", "latency_log.jsonl")

NO_NEW_MARKER = "No new publications."


def run(cmd: list[str], stage: str) -> tuple[int, str]:
    print(f"\n=== {stage} ===")
    result = subprocess.run(cmd, capture_output=True, text=True)
    out = (result.stdout or "").strip() + ("\n" + (result.stderr or "").strip()).rstrip()
    if out:
        print(out[-3000:])
    if result.returncode != 0:
        print(f"[{stage}] FAILED (exit {result.returncode}) - continuing where possible")
    return result.returncode, out


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_new_records() -> list[dict]:
    if not os.path.exists(INDEX_NEW):
        return []
    with open(INDEX_NEW, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_stems_file(records: list[dict]) -> str:
    with open(STEMS_FILE, "w") as f:
        for rec in records:
            f.write(obj_stem(rec) + "\n")
    return STEMS_FILE


def log_latency(records: list[dict], detected_at: str, classified_at: str) -> None:
    os.makedirs(os.path.dirname(LATENCY_LOG), exist_ok=True)
    new_rows = 0
    with open(LATENCY_LOG, "a") as f:
        for rec in records:
            row = {
                "stem": obj_stem(rec),
                "reference": rec.get("reference"),
                "published_date": rec.get("published_date"),
                "detected_at": detected_at,
                "classified_at": classified_at,
            }
            f.write(json.dumps(row) + "\n")
            new_rows += 1
    print(f"[latency] appended {new_rows} row(s) -> {LATENCY_LOG}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--method", default="zero_shot", choices=["zero_shot", "rule_based"])
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between predict calls")
    ap.add_argument("--upload", action="store_true", help="upload corpus+state to GCS after predict")
    ap.add_argument("--bucket", default=os.environ.get("GCS_BUCKET", ""))
    ap.add_argument("--prefix", default=os.environ.get("GCS_PREFIX", "fca-corpus"))
    args = ap.parse_args()

    py = sys.executable

    # 1. incremental index (detection)
    rc, out = run([py, "-m", "scraper.index", "--incremental"], "index --incremental")
    if rc != 0:
        print("Index stage failed - aborting.")
        sys.exit(1)
    if NO_NEW_MARKER in out:
        print("Nothing new to process. Exiting 0.")
        return
    detected_at = utcnow()

    records = load_new_records()
    if not records:
        print("No new records found in index_new.jsonl - nothing to do.")
        return
    print(f"\n{len(records)} new publication(s) detected.")

    # 2. download the delta
    run([py, "-m", "scraper.download", "--index", INDEX_NEW], "download")

    # 3. extract text for anything newly captured
    run([py, "-m", "scraper.extract"], "extract")

    # 4. classify the delta (idempotent: skips already-predicted stems)
    stems_file = write_stems_file(records)
    cmd = [py, "-m", f"classifiers.{args.method}", "--stems-file", stems_file]
    if args.method == "zero_shot":
        cmd += ["--sleep", str(args.sleep)]
    rc, out = run(cmd, f"predict ({args.method})")
    if rc != 0:
        print("Predict stage failed - classification did not complete. Exiting 1.")
        sys.exit(1)

    # 5. latency instrumentation (RQ3) - classified_at = predict stage completion
    classified_at = utcnow()
    log_latency(records, detected_at, classified_at)

    # 6. optional cloud persistence
    if args.upload:
        if not args.bucket:
            print("WARNING: --upload passed but no --bucket/GCS_BUCKET - skipping GCS.")
        else:
            run(
                [py, "-m", "scraper.storage", "--upload", "--bucket", args.bucket, "--prefix", args.prefix],
                "gcs upload",
            )

    print("\n=== PIPELINE SUMMARY ===")
    print(f"detected: {len(records)}  method: {args.method}  upload: {args.upload}")


if __name__ == "__main__":
    main()