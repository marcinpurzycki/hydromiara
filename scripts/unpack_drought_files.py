#!/usr/bin/env python3
"""Unpack the yearly archives of the Combined Drought Indicator into the data directory.

The European Drought Observatory publishes one archive per year
(`cdinx_m_edo_YYYY0101_YYYYMMDD_t.zip`) with one GeoTIFF per ten-day period.
The API reads the unpacked GeoTIFF files from the directory given by
EDO_DATA_PATH (default ./data/edo).

Usage:
    python3 scripts/unpack_drought_files.py ARCHIVE_DIR [TARGET_DIR]

Only GeoTIFF files with the expected name are written, flat into TARGET_DIR;
files that already exist with the same size are skipped, so the script can be
run again after downloading a newer archive. Uses the standard library only.
"""

import os
import re
import sys
import zipfile
from pathlib import Path

ARCHIVE_PATTERN = "cdinx_m_edo_*_t.zip"
MEMBER_PATTERN = re.compile(r"cdinx_m_edo_\d{8}_t_\d{3}_[pz]\d{2}\.tif")
DEFAULT_TARGET = "./data/edo"


def unpack(archive_dir: Path, target_dir: Path) -> tuple[int, int]:
    """Extract the GeoTIFF files; returns (written, skipped)."""
    archives = sorted(archive_dir.glob(ARCHIVE_PATTERN))
    if not archives:
        raise FileNotFoundError(f"no {ARCHIVE_PATTERN} archives in {archive_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for archive in archives:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                # The bare file name is used, so a member cannot escape TARGET_DIR.
                name = Path(member.filename).name
                if member.is_dir() or not MEMBER_PATTERN.fullmatch(name):
                    continue
                target = target_dir / name
                if target.is_file() and target.stat().st_size == member.file_size:
                    skipped += 1
                    continue
                partial = target.with_suffix(".part")
                partial.write_bytes(bundle.read(member))
                partial.replace(target)
                written += 1
    return written, skipped


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) > 1 and argv[1] in ("-h", "--help") else 2
    archive_dir = Path(argv[1])
    configured = os.environ.get("EDO_DATA_PATH") or DEFAULT_TARGET
    target_dir = Path(argv[2] if len(argv) == 3 else configured)
    try:
        written, skipped = unpack(archive_dir, target_dir)
    except (OSError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"{target_dir}: {written} files written, {skipped} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
