#!/usr/bin/env python
"""Capture real source documents as extraction test fixtures.

v1's extraction tests used only synthetic strings, so nothing was ever checked
against what publishers actually serve. These fixtures let extractor tests run
offline against real markup.

Documents are stored gzipped with a recorded checksum. Re-running refreshes
them; pass --only NAME to refresh one.

    python scripts/v2_capture_fixtures.py [--only NAME] [--force]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from curious_now_v2.retrieval.fetch import Fetcher

FIXTURE_DIR = Path(__file__).parents[1] / "tests" / "fixtures" / "retrieval"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
CAPTURED_PATH = FIXTURE_DIR / "captured.json"

EXTENSIONS = {
    "pdf": "pdf",
    "jats_xml": "xml",
}


def extension_for(kind: str) -> str:
    return EXTENSIONS.get(kind, "html")


def normalise_pdf(data: bytes, pages: int) -> bytes:
    """Shrink a PDF to a size worth versioning, without changing what the
    extractor reads.

    Extraction uses the text layer and block geometry only, so embedded images
    can go. Keeping a leading page range preserves the column layout, heading
    faces, and caption conventions that vary between publishers, which is what
    these fixtures exist to exercise.
    """

    import fitz

    with fitz.open(stream=data, filetype="pdf") as document:
        if pages and document.page_count > pages:
            document.select(list(range(pages)))
        for page in document:
            for image in page.get_images(full=True):
                try:
                    page.delete_image(image[0])
                except Exception:  # noqa: BLE001 - best effort; size only
                    continue
        return document.tobytes(garbage=4, deflate=True, clean=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="capture a single fixture by name")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download fixtures that already exist",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    specs = manifest["fixtures"]
    if args.only:
        specs = [spec for spec in specs if spec["name"] == args.only]
        if not specs:
            raise SystemExit(f"no fixture named {args.only}")

    captured: dict[str, dict[str, object]] = {}
    if CAPTURED_PATH.exists():
        captured = json.loads(CAPTURED_PATH.read_text())

    with Fetcher() as fetcher:
        for spec in specs:
            name = spec["name"]
            path = FIXTURE_DIR / f"{name}.{extension_for(spec['kind'])}.gz"
            if path.exists() and not args.force:
                print(f"skip     {name} (exists)")
                continue

            result = fetcher.fetch(spec["url"])
            if not result.ok or not result.body:
                print(f"FAILED   {name}: {result.outcome.value} {result.error or ''}")
                continue

            body = result.body
            normalised = False
            if spec["kind"] == "pdf":
                body = normalise_pdf(body, int(spec.get("pdf_pages", 8)))
                normalised = True

            path.write_bytes(gzip.compress(body, mtime=0))
            captured[name] = {
                "url": spec["url"],
                "final_url": result.final_url,
                "kind": spec["kind"],
                "content_type": result.content_type,
                "bytes": len(body),
                "fetched_bytes": len(result.body),
                "normalised": normalised,
                "stored_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(body).hexdigest(),
                "captured_at": datetime.now(UTC).isoformat(),
            }
            print(
                f"captured {name}: {len(result.body):>8,}b "
                f"-> {path.stat().st_size:>7,}b gz  {result.content_type}"
            )

    CAPTURED_PATH.write_text(json.dumps(captured, indent=2, sort_keys=True) + "\n")
    total = sum(int(entry["stored_bytes"]) for entry in captured.values())
    print(f"\n{len(captured)} fixtures, {total:,} bytes on disk")


if __name__ == "__main__":
    main()
