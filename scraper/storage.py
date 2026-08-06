"""GCS upload for the corpus (Phase 4).

OFF BY DEFAULT. The script performs no network activity unless ``--upload`` is
passed (equivalently env ``FCA_GCS_UPLOAD=1``). google-cloud-storage is an
optional dependency and is only imported on the upload path.

Uploads ``data/text/`` (and optionally ``data/pdfs`` and ``data/metadata``) to
``gs://<bucket>/<remote_prefix>/...`` keeping the same relative layout, so the
store mirrors the local corpus and the sidecar texts stay keyed by stem.

Auth uses the default Google credentials (GOOGLE_APPLICATION_CREDENTIALS,
gcloud auth, or a custom ``--credentials`` path).
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

from scraper import config


def upload_dir(
    bucket_name: str,
    local_dir: str,
    remote_prefix: str,
    credentials: Optional[str] = None,
) -> int:
    """Upload every file under ``local_dir`` to the bucket's ``remote_prefix``."""
    try:
        from google.cloud import storage  # deferred: optional dependency
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "google-cloud-storage is not installed. "
            "Run: pip install google-cloud-storage"
        ) from exc

    if credentials:
        client = storage.Client.from_service_account_json(credentials)
    else:
        client = storage.Client()
    bucket = client.bucket(bucket_name)

    uploaded = 0
    for root, _, files in os.walk(local_dir):
        for name in sorted(files):
            local_path = os.path.join(root, name)
            rel = os.path.relpath(local_path, local_dir)
            blob_name = f"{remote_prefix}/{rel}".lstrip("/")
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            uploaded += 1
    return uploaded


def _enabled(args: argparse.Namespace) -> bool:
    return bool(args.upload or os.environ.get("FCA_GCS_UPLOAD", "0") == "1")


_UPLOAD_GROUPS = [
    ("text", config.TEXT_DIR, True),
    ("pdfs", config.PDFS_DIR, False),
    ("html", config.HTML_DIR, False),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload the corpus to GCS. OFF by default.")
    parser.add_argument("--upload", action="store_true", help="actually upload (default: off)")
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET", ""))
    parser.add_argument("--prefix", default=os.environ.get("GCS_PREFIX", "fca-corpus"))
    parser.add_argument("--credentials", default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    parser.add_argument("--include-pdfs", action="store_true", help="also upload data/pdfs")
    parser.add_argument("--include-html", action="store_true", help="also upload data/html")
    args = parser.parse_args()

    if not _enabled(args):
        print("GCS upload disabled (pass --upload). Nothing done.")
        return
    if not args.bucket:
        print("ERROR: --bucket (or GCS_BUCKET) is required for upload.")
        return

    total = 0
    for label, local_dir, always in _UPLOAD_GROUPS:
        if not always:
            if label == "pdfs" and not args.include_pdfs:
                continue
            if label == "html" and not args.include_html:
                continue
        if local_dir and os.path.isdir(local_dir):
            n = upload_dir(args.bucket, local_dir, f"{args.prefix}/{label}", args.credentials)
            total += n
            print(f"uploaded {label}: {n} files")
    print(f"TOTAL uploaded: {total}")


if __name__ == "__main__":
    main()