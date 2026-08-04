"""Refresh the reader's copy of the field taxonomy.

The canonical file is config/v2/fields.json. The reader needs its own copy
because Next resolves neither a path outside the app root nor a symlink to one,
so the import fails to bundle however it is written.

A copy that nothing checks is a copy that drifts, so test_v2_fields.py fails
when the two differ. Run this after editing the config.
"""

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config" / "v2" / "fields.json"
COPY = ROOT / "apps" / "reader" / "lib" / "fields.json"

if SOURCE.read_bytes() == COPY.read_bytes():
    print("already in step")
    sys.exit(0)

shutil.copyfile(SOURCE, COPY)
print(f"copied {SOURCE.relative_to(ROOT)} -> {COPY.relative_to(ROOT)}")
