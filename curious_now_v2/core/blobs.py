"""A content-addressed store for the raw bodies we fetch.

These bytes do not belong in Postgres. They are large, immutable, and — this is
the part that decides it — recoverable: a lost blob costs one re-fetch, where a
lost row costs data. Splitting them out lets the database keep a filesystem with
real POSIX ownership and honest fsync semantics, while the bulk goes to whatever
large disk is available, which here is NTFS and cannot host a database at all.

Addressing by SHA-256 rather than by item does two useful things. Identical
bodies are stored once, which matters because retrieval routinely fetches the
same article under two candidate names — `publisher_html` and `article_html`
came back byte-identical at 231,143 bytes each in the corpus. And the filename
is a checksum, so corruption is detectable instead of silent.

Nothing here is transactional. Writes go blob-first, then the row that points at
it: a crash between the two leaves an orphaned file, which a sweep can collect,
where the reverse order would leave a row pointing at nothing. Reads report a
missing blob rather than raising, because "this needs re-fetching" is a state
the pipeline can act on and an exception is not.
"""

from __future__ import annotations

import gzip
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "CURIOUS_NOW_V2_BLOB_ROOT"
DEFAULT_ROOT = "/media/gan/Data/curious-now/blobs"

# Two levels of two hex characters: 256 directories of 256, so no directory
# holds more than a few thousand files at the corpus sizes in view.
_FAN_OUT = (2, 4)


@dataclass(frozen=True)
class StoredBlob:
    digest: str
    path: Path
    raw_bytes: int
    stored_bytes: int
    written: bool

    @property
    def ratio(self) -> float:
        return self.raw_bytes / max(self.stored_bytes, 1)


def blob_root(override: str | Path | None = None) -> Path:
    """Where blobs live: the override, the environment, or the default."""

    if override is not None:
        return Path(override)
    return Path(os.environ.get(ENV_VAR) or DEFAULT_ROOT)


def digest_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def path_for(digest: str, *, root: str | Path | None = None) -> Path:
    """Where a body with this digest is stored.

    Pure: it derives a path and touches no filesystem, so callers can record a
    location without committing to writing one.
    """

    if len(digest) < _FAN_OUT[1] or not digest.isalnum():
        raise ValueError(f"not a usable digest: {digest!r}")
    base = blob_root(root)
    return (
        base
        / digest[: _FAN_OUT[0]]
        / digest[_FAN_OUT[0] : _FAN_OUT[1]]
        / f"{digest}.gz"
    )


def put(body: bytes, *, root: str | Path | None = None) -> StoredBlob:
    """Store a body, returning where it went.

    A blob that is already present is left alone: the digest is the content, so
    a matching file cannot differ from what we would have written, and rewriting
    it would only risk truncating a good file for no gain.

    The write goes to a temporary name in the same directory and is renamed into
    place, so a reader never observes a partial blob.
    """

    digest = digest_of(body)
    target = path_for(digest, root=root)
    if target.exists():
        return StoredBlob(
            digest=digest,
            path=target,
            raw_bytes=len(body),
            stored_bytes=target.stat().st_size,
            written=False,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    # mtime is fixed so the same bytes always produce the same file, which keeps
    # the store reproducible and comparable across machines.
    compressed = gzip.compress(body, compresslevel=6, mtime=0)
    temporary = target.with_suffix(f".gz.{os.getpid()}.part")
    temporary.write_bytes(compressed)
    temporary.replace(target)

    return StoredBlob(
        digest=digest,
        path=target,
        raw_bytes=len(body),
        stored_bytes=len(compressed),
        written=True,
    )


def get(digest: str, *, root: str | Path | None = None) -> bytes | None:
    """The stored body, or None if it is not there.

    None is a legitimate answer and means the item needs fetching again. It is
    deliberately not an error: blobs live on a disk the database does not
    control, and the pipeline has to keep working when one goes missing.
    """

    try:
        path = path_for(digest, root=root)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return gzip.decompress(path.read_bytes())
    except (OSError, gzip.BadGzipFile, EOFError):
        # A truncated or unreadable blob is as absent as a missing one, and
        # saying so lets it be re-fetched rather than crashing a run.
        return None


def exists(digest: str, *, root: str | Path | None = None) -> bool:
    try:
        return path_for(digest, root=root).exists()
    except ValueError:
        return False


def usable(root: str | Path | None = None) -> tuple[bool, str]:
    """Whether the store can be written to, and why not when it cannot.

    Checked before a run rather than discovered partway through it: the default
    root is an external drive, and an unmounted drive should stop a backfill at
    the start instead of silently losing every body it fetches.
    """

    base = blob_root(root)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return False, f"cannot create {base}: {error}"

    probe = base / f".write-probe.{os.getpid()}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as error:
        return False, f"cannot write to {base}: {error}"
    return True, str(base)
