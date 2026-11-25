"""Local operational utilities; no external services or secrets in output."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from app import platform_core as core


def backup_database(source, destination):
    """Use SQLite online backup, validate snapshot, and never overwrite a backup."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".backup-", suffix=".sqlite", dir=destination.parent)
    os.close(fd)
    staged = Path(name)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(staged)) as copy:
                original.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
        # Close Windows file handles before publication.
        # Hard link is an atomic no-overwrite publication on the same local filesystem.
        os.link(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    return destination


def doctor():
    print("Python:", sys.version.split()[0])
    print("SQLite:", sqlite3.sqlite_version)
    missing = []
    for name in ("ffmpeg", "ffprobe", "node", "npm"):
        found = shutil.which(name)
        print(f"{name}: {found or 'NOT FOUND'}")
        if not found:
            missing.append(name)
    print("Platform database:", core.DB)
    print("Free disk (GiB):", round(shutil.disk_usage(core.DB.parent.parent).free / 1024**3, 1))
    return not missing


def main():
    parser = argparse.ArgumentParser(description="Autopilot AI local maintenance")
    parser.add_argument("action", choices=("doctor", "backup"))
    args = parser.parse_args()
    if args.action == "doctor":
        sys.exit(0 if doctor() else 1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for source in (core.DB, core.DB.parent / "agent.sqlite3"):
        if source.exists():
            target = core.DB.parent / "backups" / (source.stem + "-" + stamp + ".sqlite3")
            print("Verified database snapshot:", backup_database(source, target))


if __name__ == "__main__":
    main()
