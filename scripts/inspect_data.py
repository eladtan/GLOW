#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "solar_final"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def describe_array(name: str, array: np.ndarray) -> None:
    print(f"  name:       {name}")
    print(f"  shape:      {array.shape}")
    print(f"  dtype:      {array.dtype}")
    print(f"  size:       {array.size:,}")
    print(f"  bytes:      {array.nbytes / 1024**2:.3f} MiB")

    if np.issubdtype(array.dtype, np.number):
        finite = np.isfinite(array)

        print(f"  finite:     {finite.sum():,} / {array.size:,}")
        print(f"  NaN:        {np.isnan(array).sum():,}")

        if np.issubdtype(array.dtype, np.floating):
            print(f"  +inf:       {np.isposinf(array).sum():,}")
            print(f"  -inf:       {np.isneginf(array).sum():,}")

        if finite.any():
            finite_values = array[finite]

            print(f"  minimum:    {finite_values.min():.12e}")
            print(f"  maximum:    {finite_values.max():.12e}")
            print(f"  mean:       {finite_values.mean():.12e}")

    print()


def inspect_npz(path: Path) -> dict:
    print("=" * 72)
    print(f"File: {path.relative_to(REPO_ROOT)}")
    print(f"File size: {path.stat().st_size / 1024**2:.3f} MiB")
    print()

    information = {
        "file": path.name,
        "file_size_bytes": path.stat().st_size,
        "arrays": {},
    }

    with np.load(path, allow_pickle=False) as archive:
        print("Archive entries:")
        print()

        for name in archive.files:
            array = archive[name]

            describe_array(name, array)

            information["arrays"][name] = {
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "size": int(array.size),
                "nbytes": int(array.nbytes),
            }

    return information


def main() -> None:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(
            f"Manifest was not found: {MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    parts = manifest.get("temperature_parts", [])

    if not parts:
        raise ValueError(
            "The manifest contains no temperature_parts."
        )

    report = {
        "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
        "parts": [],
    }

    for part in parts:
        filename = part["files"]["opacity_tables"]
        path = DATA_DIR / filename

        if not path.is_file():
            raise FileNotFoundError(
                f"Referenced NPZ file does not exist: {path}"
            )

        report["parts"].append(inspect_npz(path))

    report_path = DATA_DIR / "npz_inspection.json"

    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print("=" * 72)
    print("All NPZ files were inspected successfully.")
    print(f"Machine-readable report: {report_path}")
    print()
    print("Next, review whether:")
    print("  1. All four files contain the same array names.")
    print("  2. Table arrays have shape (128, 32).")
    print("  3. Density and temperature coordinate arrays are present.")
    print("  4. The data are float32 or float64.")
    print("  5. There are no unexpected NaN or infinite values.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)