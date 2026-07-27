#!/usr/bin/env python3

import gzip
import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "solar_final"
SOURCE_DIR = DATA_DIR / "group_collapse"
WEB_DIR = DATA_DIR / "web_data"


def main() -> None:
    manifest = json.loads(
        (WEB_DIR / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    verified = 0

    for part in manifest["parts"]:
        part_index = int(part["part_index"])

        source_path = (
            SOURCE_DIR
            / f"opacity_group_collapse_part"
            f"{part_index:02d}.npz"
        )

        with np.load(
            source_path,
            allow_pickle=False,
        ) as source:
            for chunk_info in part["chunks"]:
                path = WEB_DIR / chunk_info["file"]

                with gzip.open(path, "rb") as handle:
                    raw = handle.read()

                shape = tuple(chunk_info["shape"])

                expected_bytes = (
                    int(np.prod(shape))
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
                    shape,
                    order="C",
                )

                field = chunk_info["field"]
                start = int(
                    chunk_info["group_start"]
                )
                stop = int(
                    chunk_info["group_stop"]
                )

                expected = source[field][
                    start:stop,
                    :,
                    :,
                ]

                if not np.array_equal(
                    reconstructed,
                    expected,
                ):
                    maximum_difference = np.max(
                        np.abs(
                            reconstructed
                            - expected
                        )
                    )

                    raise ValueError(
                        f"{path}: mismatch; "
                        f"maximum difference="
                        f"{maximum_difference}"
                    )

                verified += 1
                print(
                    f"[{verified:03d}/"
                    f"{manifest['total_chunks']:03d}] "
                    f"{chunk_info['file']}"
                )

    if verified != manifest["total_chunks"]:
        raise ValueError(
            f"Verified {verified} chunks; "
            f"manifest contains "
            f"{manifest['total_chunks']}"
        )

    print()
    print(
        "All full-dataset browser chunks "
        "match the NPZ sources exactly."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)