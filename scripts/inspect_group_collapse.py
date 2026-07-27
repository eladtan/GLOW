#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "solar_final"
GROUP_DIR = DATA_DIR / "group_collapse"
MANIFEST_PATH = DATA_DIR / "manifest.json"
OUTPUT_PATH = GROUP_DIR / "group_collapse_inspection.json"


def expected_parts(manifest: dict) -> list[str]:
    n_parts = int(manifest["n_temp_parts"])
    return [
        f"opacity_group_collapse_part{index:02d}.npz"
        for index in range(n_parts)
    ]


def describe_array(array: np.ndarray) -> dict:
    result = {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "size": int(array.size),
        "nbytes": int(array.nbytes),
    }

    if np.issubdtype(array.dtype, np.number):
        finite = np.isfinite(array)

        result["finite_count"] = int(finite.sum())
        result["nan_count"] = int(np.isnan(array).sum())

        if np.issubdtype(array.dtype, np.floating):
            result["positive_infinity_count"] = int(
                np.isposinf(array).sum()
            )
            result["negative_infinity_count"] = int(
                np.isneginf(array).sum()
            )

        if finite.any():
            finite_values = array[finite]

            result["minimum"] = float(finite_values.min())
            result["maximum"] = float(finite_values.max())
            result["mean"] = float(finite_values.mean())

    return result


def inspect_file(path: Path) -> dict:
    print("=" * 78)
    print(f"Inspecting: {path.relative_to(REPO_ROOT)}")
    print(
        f"Compressed file size: "
        f"{path.stat().st_size / 1024**2:.3f} MiB"
    )
    print()

    result = {
        "file": path.name,
        "file_size_bytes": path.stat().st_size,
        "arrays": {},
    }

    with np.load(path, allow_pickle=False) as archive:
        print(f"Arrays: {archive.files}")
        print()

        for name in archive.files:
            array = archive[name]
            details = describe_array(array)

            result["arrays"][name] = details

            print(f"{name}")
            print(f"  shape:  {array.shape}")
            print(f"  dtype:  {array.dtype}")
            print(f"  size:   {array.size:,}")
            print(
                f"  memory: "
                f"{array.nbytes / 1024**2:.3f} MiB"
            )

            if "minimum" in details:
                print(
                    f"  range:  "
                    f"{details['minimum']:.12e} to "
                    f"{details['maximum']:.12e}"
                )

            if details.get("nan_count", 0):
                print(
                    f"  WARNING: {details['nan_count']:,} NaNs"
                )

            if details.get("positive_infinity_count", 0):
                print(
                    "  WARNING: "
                    f"{details['positive_infinity_count']:,} +inf"
                )

            if details.get("negative_infinity_count", 0):
                print(
                    "  WARNING: "
                    f"{details['negative_infinity_count']:,} -inf"
                )

            print()

    return result


def validate_consistency(parts: list[dict]) -> list[str]:
    errors = []

    first_arrays = parts[0]["arrays"]
    first_names = set(first_arrays)

    for part in parts[1:]:
        names = set(part["arrays"])

        if names != first_names:
            errors.append(
                f"{part['file']} has different array names: "
                f"{sorted(names)} instead of "
                f"{sorted(first_names)}"
            )

    for name in sorted(first_names):
        reference = first_arrays[name]

        for part in parts[1:]:
            current = part["arrays"].get(name)

            if current is None:
                continue

            if current["dtype"] != reference["dtype"]:
                errors.append(
                    f"Array {name} has inconsistent dtype: "
                    f"{parts[0]['file']}={reference['dtype']}, "
                    f"{part['file']}={current['dtype']}"
                )

            reference_shape = reference["shape"]
            current_shape = current["shape"]

            # Temperature-part files may differ only in the
            # temperature-axis length. At present they are expected
            # to have identical shapes, but this check makes the
            # report useful if the last part is shorter.
            if len(current_shape) != len(reference_shape):
                errors.append(
                    f"Array {name} has inconsistent rank: "
                    f"{parts[0]['file']}={reference_shape}, "
                    f"{part['file']}={current_shape}"
                )

    return errors


def main() -> None:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(
            f"Missing manifest: {MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    report = {
        "manifest": str(
            MANIFEST_PATH.relative_to(REPO_ROOT)
        ),
        "group_directory": str(
            GROUP_DIR.relative_to(REPO_ROOT)
        ),
        "expected_axis_order": manifest.get("axis_order"),
        "expected_number_of_groups": manifest.get("n_groups"),
        "expected_number_of_densities": manifest.get("n_rho"),
        "expected_total_temperatures": manifest.get(
            "n_temp_total"
        ),
        "parts": [],
        "validation_errors": [],
    }

    for filename in expected_parts(manifest):
        path = GROUP_DIR / filename

        if not path.is_file():
            raise FileNotFoundError(
                f"Missing group-collapse file: {path}"
            )

        report["parts"].append(inspect_file(path))

    report["validation_errors"] = validate_consistency(
        report["parts"]
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print("=" * 78)
    print(f"Wrote report: {OUTPUT_PATH}")

    if report["validation_errors"]:
        print()
        print("Validation warnings:")

        for error in report["validation_errors"]:
            print(f"  - {error}")
    else:
        print("All files have consistent array names and types.")

    print()
    print("Important arrays to identify:")
    print("  - density coordinate")
    print("  - temperature coordinate")
    print("  - energy-group coordinate or group boundaries")
    print("  - group-resolved opacity arrays")
    print()
    n_temps = report["parts"][0]["arrays"]["temp_eV"]["shape"][0]
    print("Expected multigroup table shape:")
    print(f"  (1024, 128, {n_temps})")
    print("or an equivalent axis ordering.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)