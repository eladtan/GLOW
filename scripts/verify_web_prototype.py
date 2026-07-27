#!/usr/bin/env python3

import gzip
import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "solar_final"
SOURCE_PATH = (
    DATA_DIR
    / "group_collapse"
    / "opacity_group_collapse_part00.npz"
)
WEB_DIR = DATA_DIR / "web_data_prototype"


def main() -> None:
    manifest = json.loads(
        (WEB_DIR / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    field = manifest["field"]

    with np.load(SOURCE_PATH, allow_pickle=False) as source:
        source_values = source[field]

        for chunk_info in manifest["chunks"]:
            path = WEB_DIR / chunk_info["file"]

            with gzip.open(path, "rb") as handle:
                raw = handle.read()

            expected_bytes = (
                int(np.prod(chunk_info["shape"]))
                * np.dtype("<f8").itemsize
            )

            if len(raw) != expected_bytes:
                raise ValueError(
                    f"{path}: got {len(raw)} bytes; "
                    f"expected {expected_bytes}"
                )

            reconstructed = np.frombuffer(
                raw,
                dtype="<f8",
            ).reshape(
                chunk_info["shape"],
                order="C",
            )

            start = chunk_info["group_start"]
            stop = chunk_info["group_stop"]

            expected = source_values[
                start:stop,
                :,
                :,
            ]

            if not np.array_equal(
                reconstructed,
                expected,
            ):
                difference = np.max(
                    np.abs(reconstructed - expected)
                )

                raise ValueError(
                    f"{path}: reconstruction failed; "
                    f"maximum difference={difference}"
                )

            print(f"Verified {chunk_info['file']}")

    print()
    print("All prototype chunks match the NPZ source exactly.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)