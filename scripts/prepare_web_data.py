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
OUTPUT_DIR = DATA_DIR / "web_data"
SOURCE_MANIFEST = DATA_DIR / "manifest.json"

FIELDS = [
    "kross_scattering",
    "kplanck",
    "krosseland",
    "krosseland_absorption",
]

GROUP_BLOCK_SIZE = 128
GZIP_LEVEL = 9

FIELD_LABELS = {
    "kross_scattering": "Rosseland-mean scattering opacity",
    "kplanck": "Planck-mean absorption opacity",
    "krosseland": "Rosseland-mean total opacity",
    "krosseland_absorption": (
        "Rosseland-mean absorption opacity"
    ),
}


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
        json.dumps(
            value,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def arrays_equal(
    first: np.ndarray,
    second: np.ndarray,
) -> bool:
    return (
        first.shape == second.shape
        and first.dtype == second.dtype
        and np.array_equal(first, second)
    )


def write_gzip_float64(
    path: Path,
    values: np.ndarray,
) -> None:
    values = np.ascontiguousarray(
        values,
        dtype="<f8",
    )

    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_handle,
            compresslevel=GZIP_LEVEL,
            mtime=0,
        ) as gzip_handle:
            gzip_handle.write(
                values.tobytes(order="C")
            )


def validate_coordinate(
    name: str,
    values: np.ndarray,
    expected_size: int,
) -> None:
    if values.shape != (expected_size,):
        raise ValueError(
            f"{name} has shape {values.shape}; "
            f"expected {(expected_size,)}"
        )

    if not np.all(np.isfinite(values)):
        raise ValueError(
            f"{name} contains NaN or infinity"
        )

    if np.any(np.diff(values) <= 0):
        raise ValueError(
            f"{name} is not strictly increasing"
        )


def main() -> None:
    source_manifest = json.loads(
        SOURCE_MANIFEST.read_text(
            encoding="utf-8"
        )
    )

    n_parts = int(source_manifest["n_temp_parts"])
    n_groups = int(source_manifest["n_groups"])
    n_rho = int(source_manifest["n_rho"])
    expected_total_temp = int(
        source_manifest["n_temp_total"]
    )

    source_paths = [
        SOURCE_DIR
        / f"opacity_group_collapse_part{index:02d}.npz"
        for index in range(n_parts)
    ]

    missing = [
        path
        for path in source_paths
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing source files:\n"
            + "\n".join(str(path) for path in missing)
        )

    if OUTPUT_DIR.exists():
        print(f"Removing existing {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True)

    reference_edges = None
    reference_centers = None
    reference_rho = None

    combined_temperatures = []
    global_temperature_offset = 0

    manifest = {
        "format_version": 1,
        "dataset": "GLOW solar multigroup opacity tables",
        "composition": "solar",
        "prototype": False,
        "field_metadata": {
            field: {
                "label": FIELD_LABELS[field],
                "units": "cm^2 g^-1",
            }
            for field in FIELDS
        },
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
            "compression": "gzip",
        },
        "dimensions": {
            "groups": n_groups,
            "densities": n_rho,
            "temperatures": expected_total_temp,
        },
        "parts": [],
    }

    total_compressed_bytes = 0
    total_uncompressed_bytes = 0
    chunk_count = 0

    for part_index, source_path in enumerate(
        source_paths
    ):
        print()
        print("=" * 72)
        print(
            f"Reading "
            f"{source_path.relative_to(REPO_ROOT)}"
        )

        with np.load(
            source_path,
            allow_pickle=False,
        ) as source:
            required = {
                "hnu_ev_edges",
                "hnu_ev_centers",
                "rho_gcc",
                "temp_eV",
                *FIELDS,
            }

            missing_arrays = required.difference(
                source.files
            )

            if missing_arrays:
                raise ValueError(
                    f"{source_path.name} is missing "
                    f"{sorted(missing_arrays)}"
                )

            edges = np.asarray(
                source["hnu_ev_edges"],
                dtype=np.float64,
            )
            centers = np.asarray(
                source["hnu_ev_centers"],
                dtype=np.float64,
            )
            rho = np.asarray(
                source["rho_gcc"],
                dtype=np.float64,
            )
            temperatures = np.asarray(
                source["temp_eV"],
                dtype=np.float64,
            )

            validate_coordinate(
                "hnu_ev_edges",
                edges,
                n_groups + 1,
            )
            validate_coordinate(
                "hnu_ev_centers",
                centers,
                n_groups,
            )
            validate_coordinate(
                "rho_gcc",
                rho,
                n_rho,
            )
            validate_coordinate(
                "temp_eV",
                temperatures,
                temperatures.size,
            )

            if reference_edges is None:
                reference_edges = edges.copy()
                reference_centers = centers.copy()
                reference_rho = rho.copy()
            else:
                if not arrays_equal(
                    reference_edges,
                    edges,
                ):
                    raise ValueError(
                        f"Energy edges differ in "
                        f"{source_path.name}"
                    )

                if not arrays_equal(
                    reference_centers,
                    centers,
                ):
                    raise ValueError(
                        f"Energy centers differ in "
                        f"{source_path.name}"
                    )

                if not arrays_equal(
                    reference_rho,
                    rho,
                ):
                    raise ValueError(
                        f"Density axis differs in "
                        f"{source_path.name}"
                    )

                if (
                    temperatures[0]
                    <= combined_temperatures[-1][-1]
                ):
                    raise ValueError(
                        "Temperature parts overlap or "
                        "are out of order"
                    )

            n_temp = int(temperatures.size)
            combined_temperatures.append(
                temperatures.copy()
            )

            part_dir = (
                OUTPUT_DIR
                / f"part{part_index:02d}"
            )
            part_dir.mkdir()

            part_manifest = {
                "part_index": part_index,
                "source_file": source_path.name,
                "temperature_local_count": n_temp,
                "temperature_global_start": (
                    global_temperature_offset
                ),
                "temperature_global_stop": (
                    global_temperature_offset
                    + n_temp
                ),
                "temperature_min_eV": float(
                    temperatures[0]
                ),
                "temperature_max_eV": float(
                    temperatures[-1]
                ),
                "chunks": [],
            }

            expected_shape = (
                n_groups,
                n_rho,
                n_temp,
            )

            for field in FIELDS:
                values = np.asarray(source[field])

                if values.shape != expected_shape:
                    raise ValueError(
                        f"{source_path.name}/{field} "
                        f"has shape {values.shape}; "
                        f"expected {expected_shape}"
                    )

                if values.dtype != np.float64:
                    raise ValueError(
                        f"{source_path.name}/{field} "
                        f"has dtype {values.dtype}; "
                        "expected float64"
                    )

                if not np.all(np.isfinite(values)):
                    raise ValueError(
                        f"{source_path.name}/{field} "
                        "contains NaN or infinity"
                    )

                if np.any(values < 0):
                    raise ValueError(
                        f"{source_path.name}/{field} "
                        "contains negative values"
                    )

                print(
                    f"{field}: "
                    f"shape={values.shape}, "
                    f"min={values.min():.6e}, "
                    f"max={values.max():.6e}"
                )

                for group_start in range(
                    0,
                    n_groups,
                    GROUP_BLOCK_SIZE,
                ):
                    group_stop = min(
                        group_start
                        + GROUP_BLOCK_SIZE,
                        n_groups,
                    )

                    chunk = values[
                        group_start:group_stop,
                        :,
                        :,
                    ]

                    filename = (
                        f"{field}_"
                        f"groups{group_start:04d}_"
                        f"{group_stop - 1:04d}.f64.gz"
                    )

                    relative_path = (
                        Path(f"part{part_index:02d}")
                        / filename
                    )
                    output_path = (
                        OUTPUT_DIR / relative_path
                    )

                    write_gzip_float64(
                        output_path,
                        chunk,
                    )

                    compressed_bytes = (
                        output_path.stat().st_size
                    )
                    uncompressed_bytes = (
                        chunk.nbytes
                    )

                    total_compressed_bytes += (
                        compressed_bytes
                    )
                    total_uncompressed_bytes += (
                        uncompressed_bytes
                    )
                    chunk_count += 1

                    part_manifest["chunks"].append(
                        {
                            "field": field,
                            "file": (
                                relative_path.as_posix()
                            ),
                            "group_start": group_start,
                            "group_stop": group_stop,
                            "shape": list(chunk.shape),
                            "dtype": "float64",
                            "compressed_bytes": (
                                compressed_bytes
                            ),
                            "uncompressed_bytes": (
                                uncompressed_bytes
                            ),
                            "sha256": sha256_file(
                                output_path
                            ),
                            "minimum": float(
                                chunk.min()
                            ),
                            "maximum": float(
                                chunk.max()
                            ),
                            "zero_count": int(
                                np.count_nonzero(
                                    chunk == 0
                                )
                            ),
                        }
                    )

                    print(
                        f"  {relative_path}: "
                        f"{compressed_bytes / 1024**2:.2f} MiB"
                    )

            manifest["parts"].append(part_manifest)

            global_temperature_offset += n_temp

    all_temperatures = np.concatenate(
        combined_temperatures
    )

    if all_temperatures.size != expected_total_temp:
        raise ValueError(
            f"Found {all_temperatures.size} "
            f"temperatures; expected "
            f"{expected_total_temp}"
        )

    axes = {
        "hnu_ev_edges": reference_edges.tolist(),
        "hnu_ev_centers": (
            reference_centers.tolist()
        ),
        "rho_gcc": reference_rho.tolist(),
        "temp_eV": all_temperatures.tolist(),
        "temperature_parts": [
            {
                "part_index": part["part_index"],
                "global_start": (
                    part["temperature_global_start"]
                ),
                "global_stop": (
                    part["temperature_global_stop"]
                ),
            }
            for part in manifest["parts"]
        ],
        "units": {
            "hnu_ev_edges": "eV",
            "hnu_ev_centers": "eV",
            "rho_gcc": "g cm^-3",
            "temp_eV": "eV",
            "opacity": "cm^2 g^-1",
        },
    }

    manifest["total_chunks"] = chunk_count
    manifest["total_compressed_bytes"] = (
        total_compressed_bytes
    )
    manifest["total_uncompressed_bytes"] = (
        total_uncompressed_bytes
    )

    write_json(
        OUTPUT_DIR / "axes.json",
        axes,
    )
    write_json(
        OUTPUT_DIR / "manifest.json",
        manifest,
    )

    print()
    print("=" * 72)
    print("Full browser dataset created successfully.")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Chunks: {chunk_count}")
    print(
        "Compressed size: "
        f"{total_compressed_bytes / 1024**2:.2f} MiB"
    )
    print(
        "Uncompressed size: "
        f"{total_uncompressed_bytes / 1024**2:.2f} MiB"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)