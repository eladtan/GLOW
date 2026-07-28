#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


TEMPERATURE_PART_SIZES = (26, 26, 26, 25, 25)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split opacity_group_collapse.npz into five "
            "temperature blocks."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
    )
    parser.add_argument(
        "output_directory",
        type=Path,
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    output = args.output_directory.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    with np.load(source, allow_pickle=False) as data:
        payload = {
            key: np.asarray(data[key])
            for key in data.files
        }

    temperatures = payload["temp_eV"]
    densities = payload["rho_gcc"]
    edges = payload["hnu_ev_edges"]

    if temperatures.shape != (128,):
        raise ValueError(
            f"Expected 128 temperatures, got "
            f"{temperatures.shape}"
        )

    if densities.shape != (128,):
        raise ValueError(
            f"Expected 128 densities, got "
            f"{densities.shape}"
        )

    if edges.shape != (1025,):
        raise ValueError(
            f"Expected 1025 energy edges, got "
            f"{edges.shape}"
        )

    group_fields = []

    for key, values in payload.items():
        if values.ndim == 3:
            expected = (
                edges.size - 1,
                densities.size,
                temperatures.size,
            )

            if values.shape != expected:
                raise ValueError(
                    f"{key}: expected {expected}, "
                    f"got {values.shape}"
                )

            group_fields.append(key)

    start = 0

    for part, count in enumerate(
        TEMPERATURE_PART_SIZES
    ):
        stop = start + count

        part_payload = {}

        for key, values in payload.items():
            if key == "temp_eV":
                part_payload[key] = values[start:stop]
            elif key in group_fields:
                part_payload[key] = values[:, :, start:stop]
            else:
                part_payload[key] = values

        path = output / (
            f"opacity_group_collapse_part{part:02d}.npz"
        )

        np.savez_compressed(
            path,
            **part_payload,
        )

        print(
            f"{path.name}: temperatures "
            f"{start}:{stop}, "
            f"T=[{temperatures[start]:.16e}, "
            f"{temperatures[stop - 1]:.16e}]"
        )

        start = stop

    if start != temperatures.size:
        raise RuntimeError(
            f"Split consumed {start} temperatures, "
            f"expected {temperatures.size}"
        )


if __name__ == "__main__":
    main()
