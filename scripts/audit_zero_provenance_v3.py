#!/usr/bin/env python3
"""Audit zero provenance using the exact v6 all-group quadrature.

This auditor is intended for the conservative v6 opacity generator.  It does
not classify zeros from raw sample counts alone.  Instead, for every raw
(T, rho) spectrum it calls the generator's ``_all_group_quadrature`` function,
which is the same 32-point zero-aware interpolated-spectrum calculation used to
build the published group tables.

Field-specific zero rules
-------------------------

Planck and Rosseland absorption are weighted arithmetic averages.  They are
zero only when all contributing interpolated absorption nodes are zero (apart
from a final floating-point underflow).

Total Rosseland and Rosseland scattering are harmonic averages.  A zero-opacity
interval gives an infinite integral of W/kappa and therefore a zero harmonic
mean.  In the v6 quadrature this is represented by one or more zero quadrature
nodes.  Positive opacity elsewhere in the same group does not invalidate that
zero.

A positive per-field grey normalization in v6 cannot change any zero mask, so
comparison with the pre-normalization all-group quadrature is exact for zero
provenance.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import h5py
import numpy as np


FIELDS = (
    "kplanck",
    "krosseland",
    "krosseland_absorption",
    "kross_scattering",
)

ARITHMETIC_FIELDS = {
    "kplanck",
    "krosseland_absorption",
}

HARMONIC_FIELDS = {
    "krosseland",
    "kross_scattering",
}


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("collapse_source_v6", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nearest_index(axis: np.ndarray, value: float) -> int:
    return int(np.argmin(np.abs(axis - value)))


def scalar(group: Any, name: str) -> float:
    if name not in group:
        return math.nan
    value = np.asarray(group[name][()], dtype=np.float64).reshape(-1)
    return float(value[0]) if value.size else math.nan


def discover_files(runs_root: Path, mode: str | None) -> list[Path]:
    if (runs_root / "runs").is_dir():
        runs_root = runs_root / "runs"

    files: list[Path] = []
    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir():
            continue

        direct = entry / "starout.h5"
        if direct.is_file():
            files.append(direct)
            continue

        if mode:
            candidate = entry / mode / "starout.h5"
            if candidate.is_file():
                files.append(candidate)
            continue

        candidates = sorted(entry.glob("*/starout.h5"))
        if len(candidates) == 1:
            files.append(candidates[0])
        elif candidates:
            preferred = [
                path
                for path in candidates
                if path.parent.name == "fac-opacity-cowan-state"
            ]
            files.append(preferred[0] if preferred else candidates[0])

    return files


def read_conditions(path: Path) -> tuple[float, float]:
    with h5py.File(path, "r") as h5:
        return scalar(h5, "tev"), scalar(h5, "rho")


def build_run_map(
    runs_root: Path,
    mode: str | None,
    temperatures: np.ndarray,
    densities: np.ndarray,
) -> dict[tuple[int, int], Path]:
    result: dict[tuple[int, int], Path] = {}
    duplicates: Counter[tuple[int, int]] = Counter()

    for path in discover_files(runs_root, mode):
        try:
            temperature, density = read_conditions(path)
        except Exception:
            continue

        if not math.isfinite(temperature) or not math.isfinite(density):
            continue

        key = (
            nearest_index(densities, density),
            nearest_index(temperatures, temperature),
        )

        if key in result:
            duplicates[key] += 1
        else:
            result[key] = path

    if duplicates:
        print(
            f"WARNING: {len(duplicates)} grid cells had duplicate STAR files; "
            "the first discovered file is used."
        )

    return result


def prepare_raw_spectrum(
    hnu: np.ndarray,
    u: np.ndarray,
    absorption: np.ndarray,
    scattering: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    common = (
        np.isfinite(hnu)
        & (hnu > 0.0)
        & np.isfinite(u)
        & (u > 0.0)
        & np.isfinite(absorption)
        & (absorption >= 0.0)
        & np.isfinite(scattering)
        & (scattering >= 0.0)
    )

    hnu = np.asarray(hnu[common], dtype=np.float64)
    u = np.asarray(u[common], dtype=np.float64)
    absorption = np.asarray(absorption[common], dtype=np.float64)
    scattering = np.asarray(scattering[common], dtype=np.float64)

    if hnu.size < 2:
        raise ValueError("fewer than two valid raw spectral samples")

    order = np.argsort(hnu, kind="mergesort")
    hnu = hnu[order]
    u = u[order]
    absorption = absorption[order]
    scattering = scattering[order]

    unique = np.concatenate(([True], np.diff(hnu) > 0.0))
    hnu = hnu[unique]
    u = u[unique]
    absorption = absorption[unique]
    scattering = scattering[unique]

    if hnu.size < 2:
        raise ValueError("fewer than two distinct raw photon energies")

    return hnu, u, absorption, scattering


def quadrature_node_support(
    source: Any,
    hnu: np.ndarray,
    u: np.ndarray,
    absorption: np.ndarray,
    scattering: np.ndarray,
    edges: np.ndarray,
    groups: np.ndarray,
    field: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return raw counts and interpolated-node counts for selected groups."""

    hnu, u, absorption, scattering = prepare_raw_spectrum(
        hnu, u, absorption, scattering
    )

    temperature = source._infer_temperature_from_hnu_u(hnu, u)
    groups = np.asarray(groups, dtype=np.int64)

    low_u = edges[groups] / temperature
    high_u = edges[groups + 1] / temperature
    midpoint = 0.5 * (low_u + high_u)
    half_width = 0.5 * (high_u - low_u)

    u_nodes = (
        midpoint[:, None]
        + half_width[:, None] * source.EMPTY_BIN_GL_X[None, :]
    )
    hnu_nodes = temperature * u_nodes

    absorption_nodes = source.interpolate_nonnegative_log_energy(
        hnu_nodes.reshape(-1), hnu, absorption
    ).reshape(groups.size, source.EMPTY_BIN_QUADRATURE_ORDER)

    scattering_nodes = source.interpolate_nonnegative_log_energy(
        hnu_nodes.reshape(-1), hnu, scattering
    ).reshape(groups.size, source.EMPTY_BIN_QUADRATURE_ORDER)

    if field in ("kplanck", "krosseland_absorption"):
        relevant_nodes = absorption_nodes
        raw_field = absorption
    elif field == "kross_scattering":
        relevant_nodes = scattering_nodes
        raw_field = scattering
    elif field == "krosseland":
        relevant_nodes = absorption_nodes + scattering_nodes
        raw_field = absorption + scattering
    else:
        raise ValueError(field)

    raw_zero_count = np.empty(groups.size, dtype=np.int64)
    raw_positive_count = np.empty(groups.size, dtype=np.int64)

    for local_index, group in enumerate(groups):
        if group < edges.size - 2:
            mask = (hnu >= edges[group]) & (hnu < edges[group + 1])
        else:
            mask = (hnu >= edges[group]) & (hnu <= edges[group + 1])

        raw = raw_field[mask]
        raw_zero_count[local_index] = np.count_nonzero(raw == 0.0)
        raw_positive_count[local_index] = np.count_nonzero(raw > 0.0)

    node_zero_count = np.count_nonzero(relevant_nodes == 0.0, axis=1)
    node_positive_count = np.count_nonzero(relevant_nodes > 0.0, axis=1)

    return (
        raw_zero_count,
        raw_positive_count,
        node_zero_count,
        node_positive_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collapse", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Conservative v6 collapse Python script",
    )
    parser.add_argument("--field", choices=FIELDS, required=True)
    parser.add_argument("--mode", default=None)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--examples", type=int, default=20)
    args = parser.parse_args()

    source = load_module(args.source.expanduser().resolve())

    required_names = (
        "_all_group_quadrature",
        "_infer_temperature_from_hnu_u",
        "interpolate_nonnegative_log_energy",
        "EMPTY_BIN_GL_X",
        "EMPTY_BIN_QUADRATURE_ORDER",
        "load_run_spectrum",
    )
    missing = [name for name in required_names if not hasattr(source, name)]
    if missing:
        raise RuntimeError(
            "The supplied generator is not the conservative v6 source; "
            f"missing: {', '.join(missing)}"
        )

    with np.load(args.collapse.expanduser().resolve(), allow_pickle=False) as data:
        edges = np.asarray(data["hnu_ev_edges"], dtype=np.float64)
        temperatures = np.asarray(data["temp_eV"], dtype=np.float64)
        densities = np.asarray(data["rho_gcc"], dtype=np.float64)
        table = np.asarray(data[args.field], dtype=np.float64)

    expected_shape = (edges.size - 1, densities.size, temperatures.size)
    if table.shape != expected_shape:
        raise ValueError(
            f"{args.field} has shape {table.shape}; expected {expected_shape}"
        )

    zero_indices = np.argwhere(table == 0.0)
    zero_groups_by_run: dict[tuple[int, int], list[int]] = defaultdict(list)
    for group, i_rho, j_temp in zero_indices:
        zero_groups_by_run[(int(i_rho), int(j_temp))].append(int(group))

    run_map = build_run_map(
        args.runs.expanduser().resolve(),
        args.mode,
        temperatures,
        densities,
    )

    counts: Counter[str] = Counter()
    rows: list[dict[str, object]] = []

    for run_number, (key, group_list) in enumerate(
        sorted(zero_groups_by_run.items()), start=1
    ):
        i_rho, j_temp = key
        path = run_map.get(key)
        groups = np.asarray(sorted(group_list), dtype=np.int64)

        if path is None:
            for group in groups:
                rows.append(
                    {
                        "field": args.field,
                        "group": int(group),
                        "rho_index": i_rho,
                        "temp_index": j_temp,
                        "rho_gcc": float(densities[i_rho]),
                        "temp_eV": float(temperatures[j_temp]),
                        "energy_low_eV": float(edges[group]),
                        "energy_high_eV": float(edges[group + 1]),
                        "starout_h5": "",
                        "raw_zero_count": "",
                        "raw_positive_count": "",
                        "quadrature_zero_count": "",
                        "quadrature_positive_count": "",
                        "quadrature_recomputed": "",
                        "zero_rule": "",
                        "classification": "missing_run",
                    }
                )
                counts["missing_run"] += 1
            continue

        try:
            hnu, u, bb, bf, ff, sc = source.load_run_spectrum(path)
            absorption = np.asarray(bb + bf + ff, dtype=np.float64)
            scattering = np.asarray(sc, dtype=np.float64)

            recomputed, _log_p, _log_r = source._all_group_quadrature(
                hnu,
                u,
                absorption,
                scattering,
                edges,
            )
            recomputed_field = np.asarray(recomputed[args.field], dtype=np.float64)

            (
                raw_zero_count,
                raw_positive_count,
                node_zero_count,
                node_positive_count,
            ) = quadrature_node_support(
                source,
                hnu,
                u,
                absorption,
                scattering,
                edges,
                groups,
                args.field,
            )

            for local_index, group in enumerate(groups):
                value = float(recomputed_field[group])
                node_zeros = int(node_zero_count[local_index])
                node_positive = int(node_positive_count[local_index])

                if args.field in ARITHMETIC_FIELDS:
                    rule = "all_quadrature_nodes_zero"
                    support = node_positive == 0 and node_zeros > 0
                    supported_name = "arithmetic_zero_interval_supported"
                else:
                    rule = "any_quadrature_node_zero"
                    support = node_zeros > 0
                    supported_name = "harmonic_zero_interval_supported"

                if value == 0.0 and support:
                    classification = supported_name
                elif value == 0.0:
                    classification = "post_cancellation_or_unexplained_zero"
                elif value > 0.0:
                    classification = "ZERO_TABLE_BUT_POSITIVE_V6_QUADRATURE"
                else:
                    classification = "invalid_v6_quadrature_result"

                rows.append(
                    {
                        "field": args.field,
                        "group": int(group),
                        "rho_index": i_rho,
                        "temp_index": j_temp,
                        "rho_gcc": float(densities[i_rho]),
                        "temp_eV": float(temperatures[j_temp]),
                        "energy_low_eV": float(edges[group]),
                        "energy_high_eV": float(edges[group + 1]),
                        "starout_h5": str(path),
                        "raw_zero_count": int(raw_zero_count[local_index]),
                        "raw_positive_count": int(raw_positive_count[local_index]),
                        "quadrature_zero_count": node_zeros,
                        "quadrature_positive_count": node_positive,
                        "quadrature_recomputed": value,
                        "zero_rule": rule,
                        "classification": classification,
                    }
                )
                counts[classification] += 1

        except Exception as error:
            classification = f"unreadable_run:{type(error).__name__}"
            for group in groups:
                rows.append(
                    {
                        "field": args.field,
                        "group": int(group),
                        "rho_index": i_rho,
                        "temp_index": j_temp,
                        "rho_gcc": float(densities[i_rho]),
                        "temp_eV": float(temperatures[j_temp]),
                        "energy_low_eV": float(edges[group]),
                        "energy_high_eV": float(edges[group + 1]),
                        "starout_h5": str(path),
                        "raw_zero_count": "",
                        "raw_positive_count": "",
                        "quadrature_zero_count": "",
                        "quadrature_positive_count": "",
                        "quadrature_recomputed": "",
                        "zero_rule": "",
                        "classification": classification,
                    }
                )
                counts[classification] += 1

        if run_number % 100 == 0 or run_number == len(zero_groups_by_run):
            print(
                f"Processed {run_number}/{len(zero_groups_by_run)} "
                f"raw spectra for {args.field}",
                flush=True,
            )

    if args.csv is not None:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0]) if rows else ["classification"]
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print()
    print(f"Field: {args.field}")
    print(f"Collapsed table zeros: {len(rows)}")
    print(f"Raw spectra containing zeros: {len(zero_groups_by_run)}")
    print(f"Mapped raw runs: {len(run_map)}")
    print("Classification:")
    for name, count in counts.most_common():
        print(f"  {name:45s} {count:12d}")

    bad_names = {
        "ZERO_TABLE_BUT_POSITIVE_V6_QUADRATURE",
        "post_cancellation_or_unexplained_zero",
        "invalid_v6_quadrature_result",
        "missing_run",
    }
    bad_rows = [
        row
        for row in rows
        if row["classification"] in bad_names
        or str(row["classification"]).startswith("unreadable_run:")
    ]

    if bad_rows:
        print()
        print(f"First {min(args.examples, len(bad_rows))} suspicious rows:")
        for row in bad_rows[: args.examples]:
            print(
                f"  T={row['temp_eV']:.8e} "
                f"rho={row['rho_gcc']:.8e} "
                f"group={row['group']} "
                f"E=[{row['energy_low_eV']:.8e},"
                f"{row['energy_high_eV']:.8e}] "
                f"class={row['classification']} "
                f"quadrature_zero={row['quadrature_zero_count']} "
                f"quadrature_positive={row['quadrature_positive_count']} "
                f"recomputed={row['quadrature_recomputed']}"
            )

    if args.csv is not None:
        print(f"Wrote {args.csv}")

    return 1 if bad_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
