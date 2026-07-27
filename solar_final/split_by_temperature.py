#!/usr/bin/env python3
"""Split solar_final opacity archives and tables into equal temperature chunks."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
GROUP_DIR = ROOT / "group_collapse"
N_PARTS = 5
PART_SUFFIXES = [f"part{i:02d}" for i in range(N_PARTS)]
PART_FILE_RE = re.compile(r"^(?P<stem>.+)_part\d{2}\.(?P<ext>npz|csv)$")

GROUP_COLLAPSE_3D = [
    "opacity_group_collapse",
    "planck_groups",
    "rosseland_absorption_groups",
    "rosseland_groups",
    "scattering_rosseland_groups",
]

GROUP_COLLAPSE_FIELDS = {
    "opacity_group_collapse": [
        "kross_scattering",
        "kplanck",
        "krosseland",
        "krosseland_absorption",
    ],
    "planck_groups": ["kplanck"],
    "rosseland_absorption_groups": ["krosseland_absorption"],
    "rosseland_groups": ["krosseland"],
    "scattering_rosseland_groups": ["kross_scattering"],
}

TABLE_2D_FIELDS = [
    "kross_scattering",
    "kplanck",
    "krosseland",
    "krosseland_absorption",
]

CSV_STEMS = ["planck", "rosseland", "rosseland_absorption", "scattering_rosseland"]


def temp_slices(n_temp: int) -> list[np.ndarray]:
    return list(np.array_split(np.arange(n_temp), N_PARTS))


def existing_part_suffixes(stem: str, directory: Path) -> list[str]:
    suffixes = []
    for path in sorted(directory.glob(f"{stem}_part*.npz")) + sorted(directory.glob(f"{stem}_part*.csv")):
        match = PART_FILE_RE.match(path.name)
        if match and match.group("stem") == stem:
            suffix = path.stem.rsplit("_", 1)[1]
            if suffix not in suffixes:
                suffixes.append(suffix)
    return sorted(suffixes)


def delete_part_files() -> None:
    for directory in (ROOT, GROUP_DIR):
        for path in directory.glob("*_part*.*"):
            if PART_FILE_RE.match(path.name):
                path.unlink()


def merge_group_collapse_npz(stem: str, fields: list[str]) -> None:
    src = GROUP_DIR / f"{stem}.npz"
    if src.exists():
        return

    suffixes = existing_part_suffixes(stem, GROUP_DIR)
    if not suffixes:
        raise FileNotFoundError(f"No source or part files found for {stem}")

    arrays: dict[str, list[np.ndarray]] = {field: [] for field in fields}
    temps: list[np.ndarray] = []
    shared: dict[str, np.ndarray] = {}

    for suffix in suffixes:
        with np.load(GROUP_DIR / f"{stem}_{suffix}.npz") as z:
            if not shared:
                shared = {
                    "hnu_ev_edges": z["hnu_ev_edges"],
                    "hnu_ev_centers": z["hnu_ev_centers"],
                    "rho_gcc": z["rho_gcc"],
                }
            temps.append(z["temp_eV"])
            for field in fields:
                arrays[field].append(z[field])

    payload = {
        **shared,
        "temp_eV": np.concatenate(temps),
    }
    for field in fields:
        payload[field] = np.concatenate(arrays[field], axis=2)

    np.savez_compressed(src, **payload)


def merge_opacity_tables_npz() -> None:
    src = ROOT / "opacity_tables.npz"
    if src.exists():
        return

    suffixes = existing_part_suffixes("opacity_tables", ROOT)
    if not suffixes:
        raise FileNotFoundError("No source or part files found for opacity_tables")

    temps: list[np.ndarray] = []
    arrays: dict[str, list[np.ndarray]] = {field: [] for field in TABLE_2D_FIELDS}
    rho: np.ndarray | None = None

    for suffix in suffixes:
        with np.load(ROOT / f"opacity_tables_{suffix}.npz") as z:
            if rho is None:
                rho = z["rho_gcc"]
            temps.append(z["temp_eV"])
            for field in TABLE_2D_FIELDS:
                arrays[field].append(z[field])

    payload = {"rho_gcc": rho, "temp_eV": np.concatenate(temps)}
    for field in TABLE_2D_FIELDS:
        payload[field] = np.concatenate(arrays[field], axis=1)

    np.savez_compressed(src, **payload)


def merge_wide_csv(stem: str, temp: np.ndarray) -> None:
    src = ROOT / f"{stem}.csv"
    if src.exists():
        return

    suffixes = existing_part_suffixes(stem, ROOT)
    if not suffixes:
        raise FileNotFoundError(f"No source or part files found for {stem}")

    header = ["rho_gcc", *[str(v) for v in temp]]
    rows_by_rho: list[list[str]] = []

    for suffix in suffixes:
        with (ROOT / f"{stem}_{suffix}.csv").open(newline="") as fh:
            part_rows = list(csv.reader(fh))
        part_header = part_rows[0]
        if not rows_by_rho:
            rows_by_rho = [[row[0]] for row in part_rows[1:]]
        for row_idx, row in enumerate(part_rows[1:]):
            rows_by_rho[row_idx].extend(row[1:])

    with src.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows_by_rho)


def merge_opacity_table_csv(temp: np.ndarray) -> None:
    src = ROOT / "opacity_table.csv"
    if src.exists():
        return

    suffixes = existing_part_suffixes("opacity_table", ROOT)
    if not suffixes:
        raise FileNotFoundError("No source or part files found for opacity_table")

    rows: list[dict] = []
    fieldnames: list[str] | None = None
    for suffix in suffixes:
        with (ROOT / f"opacity_table_{suffix}.csv").open(newline="") as fh:
            reader = csv.DictReader(fh)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            rows.extend(reader)

    with src.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_group_collapse_npz(stem: str, fields: list[str], slices: list[np.ndarray]) -> list[dict]:
    src = GROUP_DIR / f"{stem}.npz"
    part_meta = []

    with np.load(src) as z:
        shared = {
            "hnu_ev_edges": z["hnu_ev_edges"],
            "hnu_ev_centers": z["hnu_ev_centers"],
            "rho_gcc": z["rho_gcc"],
        }
        temp = z["temp_eV"]

        for suffix, idx in zip(PART_SUFFIXES, slices):
            out = GROUP_DIR / f"{stem}_{suffix}.npz"
            payload = {**shared, "temp_eV": temp[idx]}
            for field in fields:
                payload[field] = z[field][:, :, idx]
            np.savez_compressed(out, **payload)
            part_meta.append(
                {
                    "suffix": suffix,
                    "file": out.name,
                    "temp_index_range": [int(idx[0]), int(idx[-1]) + 1],
                    "temp_eV_min": float(temp[idx[0]]),
                    "temp_eV_max": float(temp[idx[-1]]),
                    "n_temp": int(len(idx)),
                    "shape": [int(z[fields[0]].shape[0]), int(z[fields[0]].shape[1]), int(len(idx))],
                }
            )

    src.unlink()
    return part_meta


def split_opacity_tables_npz(slices: list[np.ndarray]) -> list[dict]:
    src = ROOT / "opacity_tables.npz"
    part_meta = []

    with np.load(src) as z:
        rho = z["rho_gcc"]
        temp = z["temp_eV"]

        for suffix, idx in zip(PART_SUFFIXES, slices):
            out = ROOT / f"opacity_tables_{suffix}.npz"
            payload = {"rho_gcc": rho, "temp_eV": temp[idx]}
            for field in TABLE_2D_FIELDS:
                payload[field] = z[field][:, idx]
            np.savez_compressed(out, **payload)
            part_meta.append(
                {
                    "suffix": suffix,
                    "file": out.name,
                    "temp_index_range": [int(idx[0]), int(idx[-1]) + 1],
                    "temp_eV_min": float(temp[idx[0]]),
                    "temp_eV_max": float(temp[idx[-1]]),
                    "n_temp": int(len(idx)),
                    "shape": [int(rho.shape[0]), int(len(idx))],
                }
            )

    src.unlink()
    return part_meta


def split_wide_csv(stem: str, slices: list[np.ndarray], temp: np.ndarray) -> None:
    src = ROOT / f"{stem}.csv"
    with src.open(newline="") as fh:
        rows = list(csv.reader(fh))

    header_temps = np.array([float(v) for v in rows[0][1:]])
    if not np.allclose(header_temps, temp):
        raise ValueError(f"{src.name} temperature header does not match opacity_tables.npz")

    for suffix, idx in zip(PART_SUFFIXES, slices):
        out = ROOT / f"{stem}_{suffix}.csv"
        col_idx = [0, *(int(i) + 1 for i in idx)]
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            for row in rows:
                writer.writerow([row[i] for i in col_idx])

    src.unlink()


def split_opacity_table_csv(slices: list[np.ndarray], temp: np.ndarray) -> None:
    src = ROOT / "opacity_table.csv"
    with src.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    temp_to_part = np.empty(temp.shape[0], dtype=int)
    for part_idx, idx in enumerate(slices):
        temp_to_part[idx] = part_idx

    buckets: list[list[dict]] = [[] for _ in range(N_PARTS)]
    for row in rows:
        ti = int(np.argmin(np.abs(temp - float(row["temp_eV"]))))
        buckets[temp_to_part[ti]].append(row)

    for suffix, bucket in zip(PART_SUFFIXES, buckets):
        out = ROOT / f"opacity_table_{suffix}.csv"
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(bucket)

    src.unlink()


def write_manifest(
    slices: list[np.ndarray],
    temp: np.ndarray,
    group_files: dict[str, list[dict]],
    table_parts: list[dict],
) -> None:
    parts = []
    for part_idx, (suffix, idx) in enumerate(zip(PART_SUFFIXES, slices)):
        parts.append(
            {
                "part_index": part_idx,
                "suffix": suffix,
                "temp_index_range": [int(idx[0]), int(idx[-1]) + 1],
                "temp_eV_min": float(temp[idx[0]]),
                "temp_eV_max": float(temp[idx[-1]]),
                "n_temp": int(len(idx)),
                "shape_group_collapse": [1024, 128, int(len(idx))],
                "shape_tables": [128, int(len(idx))],
                "files": {
                    stem: group_files[stem][part_idx]["file"]
                    for stem in GROUP_COLLAPSE_3D
                }
                | {
                    "opacity_tables": table_parts[part_idx]["file"],
                    "planck": f"planck_{suffix}.csv",
                    "rosseland": f"rosseland_{suffix}.csv",
                    "rosseland_absorption": f"rosseland_absorption_{suffix}.csv",
                    "scattering_rosseland": f"scattering_rosseland_{suffix}.csv",
                    "opacity_table": f"opacity_table_{suffix}.csv",
                },
            }
        )

    manifest = {
        "axis_order": "group,rho,temp",
        "fields": GROUP_COLLAPSE_FIELDS["opacity_group_collapse"],
        "hnu_min_eV": 0.01,
        "hnu_max_eV": 2_000_000.0,
        "n_groups": 1024,
        "n_rho": 128,
        "n_temp_total": int(temp.shape[0]),
        "n_temp_parts": N_PARTS,
        "spacing": "log",
        "temperature_parts": parts,
        "unsplit_files": ["frequency_groups.csv"],
    }

    with (GROUP_DIR / "manifest.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def main() -> None:
    merge_opacity_tables_npz()
    for stem in GROUP_COLLAPSE_3D:
        merge_group_collapse_npz(stem, GROUP_COLLAPSE_FIELDS[stem])

    with np.load(ROOT / "opacity_tables.npz") as z:
        temp = z["temp_eV"]

    merge_opacity_table_csv(temp)
    for stem in CSV_STEMS:
        merge_wide_csv(stem, temp)

    delete_part_files()

    slices = temp_slices(temp.shape[0])

    group_files: dict[str, list[dict]] = {}
    for stem in GROUP_COLLAPSE_3D:
        group_files[stem] = split_group_collapse_npz(stem, GROUP_COLLAPSE_FIELDS[stem], slices)

    table_parts = split_opacity_tables_npz(slices)

    for stem in CSV_STEMS:
        split_wide_csv(stem, slices, temp)

    split_opacity_table_csv(slices, temp)
    write_manifest(slices, temp, group_files, table_parts)

    print("Split complete:")
    for part in json.loads((GROUP_DIR / "manifest.json").read_text())["temperature_parts"]:
        size = (GROUP_DIR / part["files"]["opacity_group_collapse"]).stat().st_size / 1e6
        print(
            f"  {part['suffix']}: T={part['temp_eV_min']:.6g}..{part['temp_eV_max']:.6g} eV "
            f"({part['n_temp']} temps, opacity_group_collapse {size:.1f} MB)"
        )


if __name__ == "__main__":
    main()
