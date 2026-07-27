#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "solar_final"
GROUP_DIR = DATA_DIR / "group_collapse"
MANIFEST_PATH = DATA_DIR / "manifest.json"

FIELDS = [
    "kross_scattering",
    "kplanck",
    "krosseland",
    "krosseland_absorption",
]


def main() -> None:
    manifest = json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )

    n_parts = int(manifest["n_temp_parts"])
    expected_groups = int(manifest["n_groups"])
    expected_rho = int(manifest["n_rho"])
    expected_total_temp = int(manifest["n_temp_total"])

    reference_edges = None
    reference_centers = None
    reference_rho = None
    previous_temperature = None
    total_temperatures = 0

    report = {
        "parts": [],
        "total_temperatures": 0,
        "errors": [],
        "warnings": [],
    }

    for part_index in range(n_parts):
        path = (
            GROUP_DIR
            / f"opacity_group_collapse_part{part_index:02d}.npz"
        )

        if not path.is_file():
            report["errors"].append(
                f"Missing file: {path.name}"
            )
            continue

        with np.load(path, allow_pickle=False) as data:
            required = {
                "hnu_ev_edges",
                "hnu_ev_centers",
                "rho_gcc",
                "temp_eV",
                *FIELDS,
            }

            missing = required.difference(data.files)

            if missing:
                report["errors"].append(
                    f"{path.name} missing arrays: {sorted(missing)}"
                )
                continue

            edges = data["hnu_ev_edges"]
            centers = data["hnu_ev_centers"]
            rho = data["rho_gcc"]
            temperatures = data["temp_eV"]

            if reference_edges is None:
                reference_edges = edges.copy()
                reference_centers = centers.copy()
                reference_rho = rho.copy()
            else:
                if not np.array_equal(edges, reference_edges):
                    report["errors"].append(
                        f"Energy edges differ in {path.name}"
                    )

                if not np.array_equal(
                    centers,
                    reference_centers,
                ):
                    report["errors"].append(
                        f"Energy centers differ in {path.name}"
                    )

                if not np.array_equal(rho, reference_rho):
                    report["errors"].append(
                        f"Density axis differs in {path.name}"
                    )

            if edges.shape != (expected_groups + 1,):
                report["errors"].append(
                    f"{path.name}: bad energy-edge shape "
                    f"{edges.shape}"
                )

            if centers.shape != (expected_groups,):
                report["errors"].append(
                    f"{path.name}: bad energy-center shape "
                    f"{centers.shape}"
                )

            if rho.shape != (expected_rho,):
                report["errors"].append(
                    f"{path.name}: bad density shape {rho.shape}"
                )

            if np.any(np.diff(edges) <= 0):
                report["errors"].append(
                    f"{path.name}: energy edges not increasing"
                )

            if np.any(np.diff(rho) <= 0):
                report["errors"].append(
                    f"{path.name}: densities not increasing"
                )

            if np.any(np.diff(temperatures) <= 0):
                report["errors"].append(
                    f"{path.name}: temperatures not increasing"
                )

            if (
                previous_temperature is not None
                and temperatures[0] <= previous_temperature
            ):
                report["errors"].append(
                    f"{path.name}: temperature overlap or disorder"
                )

            previous_temperature = float(temperatures[-1])
            total_temperatures += temperatures.size

            part_report = {
                "file": path.name,
                "n_temperatures": int(temperatures.size),
                "temperature_min_eV": float(
                    temperatures[0]
                ),
                "temperature_max_eV": float(
                    temperatures[-1]
                ),
                "fields": {},
            }

            expected_shape = (
                expected_groups,
                expected_rho,
                temperatures.size,
            )

            for field in FIELDS:
                values = data[field]

                field_report = {
                    "shape": list(values.shape),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "nan_count": int(
                        np.isnan(values).sum()
                    ),
                    "infinity_count": int(
                        np.isinf(values).sum()
                    ),
                    "negative_count": int(
                        np.count_nonzero(values < 0)
                    ),
                    "zero_count": int(
                        np.count_nonzero(values == 0)
                    ),
                }

                part_report["fields"][field] = field_report

                if values.shape != expected_shape:
                    report["errors"].append(
                        f"{path.name}/{field}: "
                        f"shape {values.shape}, "
                        f"expected {expected_shape}"
                    )

                if not np.all(np.isfinite(values)):
                    report["errors"].append(
                        f"{path.name}/{field}: "
                        "contains NaN or infinity"
                    )

                if np.any(values < 0):
                    report["warnings"].append(
                        f"{path.name}/{field}: "
                        "contains negative values"
                    )

            report["parts"].append(part_report)

    report["total_temperatures"] = total_temperatures

    if total_temperatures != expected_total_temp:
        report["errors"].append(
            f"Found {total_temperatures} temperatures; "
            f"expected {expected_total_temp}"
        )

    output = GROUP_DIR / "dataset_validation.json"
    output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {output}")
    print(f"Temperature count: {total_temperatures}")
    print(f"Errors: {len(report['errors'])}")
    print(f"Warnings: {len(report['warnings'])}")

    for error in report["errors"]:
        print(f"ERROR: {error}")

    for warning in report["warnings"]:
        print(f"WARNING: {warning}")

    if report["errors"]:
        sys.exit(1)

    print("Dataset validation passed.")


if __name__ == "__main__":
    main()