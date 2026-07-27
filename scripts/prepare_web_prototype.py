#!/usr/bin/env python3

import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "solar_final"
SOURCE_DIR = DATA_DIR / "group_collapse"
SOURCE_PATH = SOURCE_DIR / "opacity_group_collapse_part00.npz"

OUTPUT_DIR = DATA_DIR / "web_data_prototype"

FIELD = "kplanck"
GROUP_BLOCK_SIZE = 128


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_gzip_float64(
    path: Path,
    values: np.ndarray,
) -> None:
    values = np.ascontiguousarray(values, dtype="<f8")

    # gzip.GzipFile allows mtime=0, making output reproducible.
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_handle,
            compresslevel=9,
            mtime=0,
        ) as gzip_handle:
            gzip_handle.write(values.tobytes(order="C"))


def main() -> None:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"Missing source file: {SOURCE_PATH}"
        )

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    CHUNK_DIR = OUTPUT_DIR / "part00"
    CHUNK_DIR.mkdir(parents=True)

    with np.load(SOURCE_PATH, allow_pickle=False) as source:
        required = {
            "hnu_ev_edges",
            "hnu_ev_centers",
            "rho_gcc",
            "temp_eV",
            FIELD,
        }

        missing = required.difference(source.files)

        if missing:
            raise ValueError(
                f"Source is missing arrays: {sorted(missing)}"
            )

        energy_edges = np.asarray(
            source["hnu_ev_edges"],
            dtype=np.float64,
        )
        energy_centers = np.asarray(
            source["hnu_ev_centers"],
            dtype=np.float64,
        )
        densities = np.asarray(
            source["rho_gcc"],
            dtype=np.float64,
        )
        temperatures = np.asarray(
            source["temp_eV"],
            dtype=np.float64,
        )
        opacity = np.asarray(
            source[FIELD],
            dtype=np.float64,
        )

        expected_shape = (
            energy_centers.size,
            densities.size,
            temperatures.size,
        )

        if opacity.shape != expected_shape:
            raise ValueError(
                f"{FIELD} has shape {opacity.shape}; "
                f"expected {expected_shape}"
            )

        if not np.all(np.isfinite(opacity)):
            raise ValueError(
                f"{FIELD} contains NaN or infinity"
            )

        if np.any(opacity < 0):
            raise ValueError(
                f"{FIELD} contains negative opacity"
            )

        axes = {
            "hnu_ev_edges": energy_edges.tolist(),
            "hnu_ev_centers": energy_centers.tolist(),
            "rho_gcc": densities.tolist(),
            "temp_eV": temperatures.tolist(),
            "units": {
                "hnu_ev_edges": "eV",
                "hnu_ev_centers": "eV",
                "rho_gcc": "g cm^-3",
                "temp_eV": "eV",
                "opacity": "cm^2 g^-1",
            },
        }

        chunks = []

        for group_start in range(
            0,
            energy_centers.size,
            GROUP_BLOCK_SIZE,
        ):
            group_stop = min(
                group_start + GROUP_BLOCK_SIZE,
                energy_centers.size,
            )

            chunk = opacity[
                group_start:group_stop,
                :,
                :,
            ]

            filename = (
                f"{FIELD}_"
                f"groups{group_start:04d}_"
                f"{group_stop - 1:04d}.f64.gz"
            )

            relative_path = Path("part00") / filename
            output_path = OUTPUT_DIR / relative_path

            write_gzip_float64(output_path, chunk)

            compressed_bytes = output_path.stat().st_size
            uncompressed_bytes = chunk.nbytes

            chunks.append(
                {
                    "field": FIELD,
                    "file": relative_path.as_posix(),
                    "group_start": group_start,
                    "group_stop": group_stop,
                    "shape": list(chunk.shape),
                    "dtype": "float64",
                    "byte_order": "little-endian",
                    "array_order": "C",
                    "axis_order": [
                        "group",
                        "rho",
                        "temp",
                    ],
                    "compressed_bytes": compressed_bytes,
                    "uncompressed_bytes": uncompressed_bytes,
                    "sha256": sha256_file(output_path),
                    "minimum": float(chunk.min()),
                    "maximum": float(chunk.max()),
                    "zero_count": int(
                        np.count_nonzero(chunk == 0)
                    ),
                }
            )

            print(
                f"Wrote {relative_path}: "
                f"{compressed_bytes / 1024**2:.2f} MiB"
            )

    manifest = {
        "format_version": 1,
        "prototype": True,
        "dataset": "GLOW solar multigroup opacity",
        "composition": "solar",
        "field": FIELD,
        "field_label": "Planck-mean absorption opacity",
        "field_units": "cm^2 g^-1",
        "temperature_part": 0,
        "storage": {
            "format": "gzip-compressed raw binary",
            "dtype": "float64",
            "byte_order": "little-endian",
            "array_order": "C",
            "axis_order": [
                "group",
                "rho",
                "temp",
            ],
            "group_block_size": GROUP_BLOCK_SIZE,
        },
        "dimensions": {
            "groups": int(energy_centers.size),
            "densities": int(densities.size),
            "temperatures": int(temperatures.size),
        },
        "chunks": chunks,
    }

    write_json(OUTPUT_DIR / "axes.json", axes)
    write_json(OUTPUT_DIR / "manifest.json", manifest)

    total_compressed = sum(
        chunk["compressed_bytes"]
        for chunk in chunks
    )

    print()
    print("Prototype generation completed.")
    print(f"Chunks: {len(chunks)}")
    print(
        f"Compressed size: "
        f"{total_compressed / 1024**2:.2f} MiB"
    )
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)