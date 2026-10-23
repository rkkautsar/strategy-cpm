"""Private, versioned R2 snapshots for the monthly research runner."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
import argparse

SNAPSHOT_PREFIX = "taa/monthly-snapshots"
LATEST_KEY = f"{SNAPSHOT_PREFIX}/latest.json"
SNAPSHOT_PATHS = (Path(".cache"), Path("results"))


def _client():
    from .data import _r2_client

    client, bucket = _r2_client()
    if os.getenv("CPM_REQUIRE_R2") == "1" and client is None:
        raise RuntimeError("Monthly runner requires private R2; configure CPM_R2_BUCKET and its credentials.")
    return client, bucket


def _archive_bytes(*, include_results: bool = True) -> bytes:
    with tempfile.TemporaryFile() as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            roots = SNAPSHOT_PATHS if include_results else (Path(".cache"),)
            for root in roots:
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        archive.add(path, arcname=path.as_posix(), recursive=False)
        stream.seek(0)
        return stream.read()


def restore_latest_snapshot() -> str:
    """Restore the last complete private cache/results archive, if present."""
    client, bucket = _client()
    if client is None:
        return "R2 snapshots disabled"
    try:
        manifest = json.loads(client.get_object(Bucket=bucket, Key=LATEST_KEY)["Body"].read())
    except client.exceptions.NoSuchKey:
        return "no prior R2 snapshot"
    payload = client.get_object(Bucket=bucket, Key=manifest["object"])["Body"].read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest.get("sha256"):
        raise ValueError("R2 snapshot checksum does not match latest manifest.")
    allowed = {".cache", "results"}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = []
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or not path.parts or path.parts[0] not in allowed or ".." in path.parts:
                raise ValueError(f"Unsafe path in R2 snapshot: {member.name}")
            if member.isfile():
                members.append(member)
        archive.extractall(".", members=members)
    return f"restored {manifest['snapshot_id']} ({manifest['created_at']})"


def publish_snapshot(*, include_results: bool = True) -> str:
    """Write an immutable archive, then advance the latest pointer last."""
    client, bucket = _client()
    if client is None:
        return "R2 snapshots disabled"
    payload = _archive_bytes(include_results=include_results)
    digest = hashlib.sha256(payload).hexdigest()
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_key = f"{SNAPSHOT_PREFIX}/{snapshot_id}-{digest[:12]}.tar.gz"
    client.put_object(Bucket=bucket, Key=object_key, Body=payload, ContentType="application/gzip")
    manifest = {
        "snapshot_id": snapshot_id,
        "created_at": created,
        "object": object_key,
        "sha256": digest,
        "bytes": len(payload),
    }
    client.put_object(
        Bucket=bucket,
        Key=LATEST_KEY,
        Body=(json.dumps(manifest, sort_keys=True) + "\n").encode(),
        ContentType="application/json",
    )
    return f"saved {snapshot_id} ({len(payload):,} bytes, sha256 {digest[:12]})"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore or publish the private R2 cache snapshot.")
    parser.add_argument("action", choices=("restore", "publish"))
    action = parser.parse_args().action
    print(restore_latest_snapshot() if action == "restore" else publish_snapshot())
