#!/usr/bin/env python3
"""Validate split 1024-group opacity tables and one-group conservation.

This checks that:
  1. all split files have consistent energy/rho axes;
  2. their temperature blocks concatenate cleanly;
  3. all four opacity arrays are finite and non-negative;
  4. regrouping all native groups to one group reproduces a direct one-group
     collapse made by the same generator.

Expected split fields:
    kplanck
    krosseland
    krosseland_absorption
    kross_scattering

The regrouping conventions are:
    Planck:
        sum(P_g * kP_g) / sum(P_g)

    Rosseland total and scattering:
        sum(R_g) / sum(R_g / kR_g)

    Rosseland flux-weighted absorption:
        sum((R_g / kR_total_g) * kRa_g)
        / sum(R_g / kR_total_g)

where P_g and R_g are integrated Planck and Rosseland weights over each
native energy group.

The weight integrals are evaluated in log space with Gauss-Legendre
quadrature, preventing Wien-tail underflow.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np


FIELDS = (
    "kplanck",
    "krosseland",
    "krosseland_absorption",
    "kross_scattering",
)

ROSS_C = 15.0 / (4.0 * math.pi**4)


def logsumexp(values: np.ndarray, axis=None) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    maximum = np.max(values, axis=axis, keepdims=True)
    finite_maximum = np.isfinite(maximum)

    shifted = np.where(
        finite_maximum,
        values - maximum,
        -np.inf,
    )
    total = np.sum(np.exp(shifted), axis=axis, keepdims=True)

    result = np.where(
        finite_maximum & (total > 0.0),
        maximum + np.log(total),
        -np.inf,
    )

    if axis is not None:
        result = np.squeeze(result, axis=axis)
    return result


def log_planck_weight(u: np.ndarray) -> np.ndarray:
    u = np.asarray(u, dtype=np.float64)
    result = np.full_like(u, -np.inf)

    good = np.isfinite(u) & (u > 0.0)
    x = u[good]

    log_expm1 = np.empty_like(x)
    small = x < 50.0
    log_expm1[small] = np.log(np.expm1(x[small]))
    log_expm1[~small] = (
        x[~small] + np.log1p(-np.exp(-x[~small]))
    )

    result[good] = 3.0 * np.log(x) - log_expm1
    return result


def log_rosseland_weight(u: np.ndarray) -> np.ndarray:
    u = np.asarray(u, dtype=np.float64)
    result = np.full_like(u, -np.inf)

    good = np.isfinite(u) & (u > 0.0)
    x = u[good]

    result[good] = (
        math.log(ROSS_C)
        - x
        + 4.0 * np.log(x)
        - 2.0 * np.log(-np.expm1(-x))
    )
    return result


def integrated_log_weight(
    energy_edges: np.ndarray,
    temperatures: np.ndarray,
    kind: str,
    order: int,
) -> np.ndarray:
    """Return log integrated weights with shape (group, temperature)."""

    nodes, weights = np.polynomial.legendre.leggauss(order)

    low = energy_edges[:-1, None]
    high = energy_edges[1:, None]

    # Gauss-Legendre nodes and Jacobian in photon energy.
    energy = (
        0.5 * (high - low) * nodes[None, :]
        + 0.5 * (high + low)
    )
    jacobian = 0.5 * (high - low)

    output = np.empty(
        (energy_edges.size - 1, temperatures.size),
        dtype=np.float64,
    )

    log_quadrature_weights = np.log(weights)[None, :]

    for j, temperature in enumerate(temperatures):
        if not math.isfinite(float(temperature)) or temperature <= 0.0:
            raise ValueError(
                f"Invalid temperature at index {j}: {temperature}"
            )

        u = energy / temperature

        if kind == "planck":
            log_kernel = log_planck_weight(u)
        elif kind == "rosseland":
            log_kernel = log_rosseland_weight(u)
        else:
            raise ValueError(kind)

        # dE = T du. The T factor is common to every group at a fixed
        # temperature and cancels in all regrouping ratios. Keeping dE here
        # is convenient and still mathematically equivalent.
        log_terms = log_kernel + log_quadrature_weights
        output[:, j] = (
            np.log(jacobian[:, 0])
            + logsumexp(log_terms, axis=1)
        )

    return output


def load_split_parts(
    directory: Path,
    pattern: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    paths = sorted(directory.glob(pattern))
    if not paths:
        raise FileNotFoundError(
            f"No split files match {directory / pattern}"
        )

    reference_edges = None
    reference_rho = None
    temperatures: list[np.ndarray] = []
    field_parts = {field: [] for field in FIELDS}

    previous_last_temperature = -math.inf

    for path in paths:
        with np.load(path, allow_pickle=False) as data:
            required = {
                "hnu_ev_edges",
                "temp_eV",
                "rho_gcc",
                *FIELDS,
            }
            missing = sorted(required.difference(data.files))
            if missing:
                raise KeyError(
                    f"{path.name} is missing arrays: {missing}"
                )

            edges = np.asarray(
                data["hnu_ev_edges"],
                dtype=np.float64,
            )
            rho = np.asarray(
                data["rho_gcc"],
                dtype=np.float64,
            )
            temp = np.asarray(
                data["temp_eV"],
                dtype=np.float64,
            )

            if reference_edges is None:
                reference_edges = edges
                reference_rho = rho
            else:
                if not np.array_equal(edges, reference_edges):
                    raise ValueError(
                        f"Energy edges differ in {path.name}"
                    )
                if not np.array_equal(rho, reference_rho):
                    raise ValueError(
                        f"Density axis differs in {path.name}"
                    )

            if temp.ndim != 1 or temp.size == 0:
                raise ValueError(
                    f"Invalid temperature axis in {path.name}"
                )
            if np.any(np.diff(temp) <= 0.0):
                raise ValueError(
                    f"Temperature axis is not strictly increasing "
                    f"in {path.name}"
                )
            if temp[0] <= previous_last_temperature:
                raise ValueError(
                    f"Temperature blocks overlap or are out of order "
                    f"at {path.name}"
                )
            previous_last_temperature = float(temp[-1])
            temperatures.append(temp)

            expected_shape = (
                edges.size - 1,
                rho.size,
                temp.size,
            )

            for field in FIELDS:
                values = np.asarray(
                    data[field],
                    dtype=np.float64,
                )
                if values.shape != expected_shape:
                    raise ValueError(
                        f"{path.name}:{field} has shape "
                        f"{values.shape}; expected {expected_shape}"
                    )
                field_parts[field].append(values)

        print(
            f"Loaded {path.name}: "
            f"{temp.size} temperatures"
        )

    assert reference_edges is not None
    assert reference_rho is not None

    combined_temperatures = np.concatenate(temperatures)
    combined_fields = {
        field: np.concatenate(parts, axis=2)
        for field, parts in field_parts.items()
    }

    return (
        reference_edges,
        reference_rho,
        combined_temperatures,
        combined_fields,
    )


def load_one_group_reference(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    with np.load(path, allow_pickle=False) as data:
        required = {
            "hnu_ev_edges",
            "temp_eV",
            "rho_gcc",
            *FIELDS,
        }
        missing = sorted(required.difference(data.files))
        if missing:
            raise KeyError(
                f"{path} is missing arrays: {missing}"
            )

        edges = np.asarray(
            data["hnu_ev_edges"],
            dtype=np.float64,
        )
        temperatures = np.asarray(
            data["temp_eV"],
            dtype=np.float64,
        )
        densities = np.asarray(
            data["rho_gcc"],
            dtype=np.float64,
        )

        if edges.size != 2:
            raise ValueError(
                f"One-group file has {edges.size - 1} groups, expected 1"
            )

        expected_shape = (
            1,
            densities.size,
            temperatures.size,
        )
        fields = {}

        for field in FIELDS:
            values = np.asarray(
                data[field],
                dtype=np.float64,
            )
            if values.shape != expected_shape:
                raise ValueError(
                    f"One-group {field} has shape {values.shape}; "
                    f"expected {expected_shape}"
                )
            fields[field] = values[0]

    return edges, densities, temperatures, fields


def arithmetic_regroup(
    values: np.ndarray,
    log_weights: np.ndarray,
) -> np.ndarray:
    """Weighted arithmetic mean over group axis.

    values shape: (group, rho, temp)
    log_weights shape: (group, temp)
    result shape: (rho, temp)
    """

    if np.any(values < 0.0) or np.any(~np.isfinite(values)):
        raise ValueError(
            "Arithmetic regroup received invalid opacity values"
        )

    log_weight_3d = log_weights[:, None, :]

    denominator_log = logsumexp(
        log_weight_3d,
        axis=0,
    )

    positive = values > 0.0
    log_numerator_terms = np.full_like(
        values,
        -np.inf,
        dtype=np.float64,
    )
    log_numerator_terms[positive] = (
        log_weight_3d[
            np.broadcast_to(
                np.ones_like(values, dtype=bool),
                values.shape,
            )
        ].reshape(values.shape)[positive]
        + np.log(values[positive])
    )

    numerator_log = logsumexp(
        log_numerator_terms,
        axis=0,
    )

    output = np.zeros_like(denominator_log)
    valid = (
        np.isfinite(numerator_log)
        & np.isfinite(denominator_log)
    )
    output[valid] = np.exp(
        numerator_log[valid] - denominator_log[valid]
    )
    return output


def arithmetic_regroup_simple(
    values: np.ndarray,
    log_weights: np.ndarray,
) -> np.ndarray:
    # Simpler broadcast-safe implementation.
    log_weight_3d = np.broadcast_to(
        log_weights[:, None, :],
        values.shape,
    )
    terms = np.full_like(values, -np.inf)
    positive = values > 0.0
    terms[positive] = (
        log_weight_3d[positive]
        + np.log(values[positive])
    )
    log_num = logsumexp(terms, axis=0)
    log_den = logsumexp(log_weight_3d, axis=0)

    result = np.zeros_like(log_den)
    good = np.isfinite(log_num) & np.isfinite(log_den)
    result[good] = np.exp(log_num[good] - log_den[good])
    return result


def harmonic_regroup(
    values: np.ndarray,
    log_weights: np.ndarray,
) -> np.ndarray:
    """Weighted harmonic mean over group axis."""

    if np.any(values < 0.0) or np.any(~np.isfinite(values)):
        raise ValueError(
            "Harmonic regroup received invalid opacity values"
        )

    log_weight_3d = np.broadcast_to(
        log_weights[:, None, :],
        values.shape,
    )

    # A zero opacity with a mathematically nonzero group weight makes
    # the harmonic mean zero.
    has_zero = np.any(values == 0.0, axis=0)

    terms = np.full_like(values, -np.inf)
    positive = values > 0.0
    terms[positive] = (
        log_weight_3d[positive]
        - np.log(values[positive])
    )

    log_num = logsumexp(log_weight_3d, axis=0)
    log_den = logsumexp(terms, axis=0)

    result = np.zeros_like(log_num)
    good = (
        ~has_zero
        & np.isfinite(log_num)
        & np.isfinite(log_den)
    )
    result[good] = np.exp(
        log_num[good] - log_den[good]
    )
    return result


def absorption_regroup(
    absorption: np.ndarray,
    total_rosseland: np.ndarray,
    log_rosseland_weights: np.ndarray,
) -> np.ndarray:
    """Regroup the flux-weighted Rosseland absorption field."""

    if (
        np.any(absorption < 0.0)
        or np.any(total_rosseland < 0.0)
        or np.any(~np.isfinite(absorption))
        or np.any(~np.isfinite(total_rosseland))
    ):
        raise ValueError(
            "Rosseland absorption regroup received invalid values"
        )

    # Effective group weight is R_g / kR_total,g.
    base = np.broadcast_to(
        log_rosseland_weights[:, None, :],
        total_rosseland.shape,
    )

    effective = np.full_like(total_rosseland, np.inf)
    positive_total = total_rosseland > 0.0
    effective[positive_total] = (
        base[positive_total]
        - np.log(total_rosseland[positive_total])
    )

    if np.any(~positive_total):
        # A zero total Rosseland opacity represents an infinite transport
        # denominator. This should not occur in the current data.
        raise ValueError(
            "Zero total Rosseland opacity prevents absorption regrouping"
        )

    numerator_terms = np.full_like(absorption, -np.inf)
    positive_absorption = absorption > 0.0
    numerator_terms[positive_absorption] = (
        effective[positive_absorption]
        + np.log(absorption[positive_absorption])
    )

    log_num = logsumexp(numerator_terms, axis=0)
    log_den = logsumexp(effective, axis=0)

    result = np.zeros_like(log_den)
    good = np.isfinite(log_num) & np.isfinite(log_den)
    result[good] = np.exp(log_num[good] - log_den[good])
    return result


def error_statistics(
    actual: np.ndarray,
    reference: np.ndarray,
    atol: float,
) -> dict[str, float]:
    absolute = np.abs(actual - reference)
    scale = np.maximum(np.abs(reference), atol)
    relative = absolute / scale

    return {
        "max_abs": float(np.max(absolute)),
        "max_rel": float(np.max(relative)),
        "q99_rel": float(np.quantile(relative, 0.99)),
        "q999_rel": float(np.quantile(relative, 0.999)),
        "median_rel": float(np.median(relative)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parts-dir",
        type=Path,
        default=Path("solar_final/group_collapse"),
    )
    parser.add_argument(
        "--pattern",
        default="opacity_group_collapse_part*.npz",
    )
    parser.add_argument(
        "--one-group",
        type=Path,
        required=True,
        help=(
            "Direct one-group opacity_group_collapse.npz produced "
            "by the same generator and raw runs"
        ),
    )
    parser.add_argument(
        "--quadrature-order",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=5.0e-10,
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=1.0e-300,
    )
    args = parser.parse_args()

    (
        native_edges,
        densities,
        temperatures,
        fields,
    ) = load_split_parts(
        args.parts_dir.resolve(),
        args.pattern,
    )

    (
        one_edges,
        one_densities,
        one_temperatures,
        one_fields,
    ) = load_one_group_reference(
        args.one_group.resolve()
    )

    if not np.array_equal(densities, one_densities):
        raise ValueError(
            "Density axis differs between split and one-group data"
        )
    if not np.array_equal(temperatures, one_temperatures):
        raise ValueError(
            "Temperature axis differs between split and one-group data"
        )
    if not np.allclose(
        native_edges[[0, -1]],
        one_edges,
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError(
            "One-group energy range differs from split-table range"
        )

    print()
    print("Combined split-table shape")
    for field in FIELDS:
        values = fields[field]
        print(
            f"  {field:28s} {values.shape} "
            f"zeros={np.count_nonzero(values == 0):10d} "
            f"negative={np.count_nonzero(values < 0):6d} "
            f"nonfinite={np.count_nonzero(~np.isfinite(values)):6d}"
        )
        if np.any(values < 0.0) or np.any(~np.isfinite(values)):
            raise ValueError(
                f"{field} contains invalid values"
            )

    print()
    print("Computing stable group weights...")
    log_planck = integrated_log_weight(
        native_edges,
        temperatures,
        "planck",
        args.quadrature_order,
    )
    log_rosseland = integrated_log_weight(
        native_edges,
        temperatures,
        "rosseland",
        args.quadrature_order,
    )

    reconstructed = {
        "kplanck": arithmetic_regroup_simple(
            fields["kplanck"],
            log_planck,
        ),
        "krosseland": harmonic_regroup(
            fields["krosseland"],
            log_rosseland,
        ),
        "kross_scattering": harmonic_regroup(
            fields["kross_scattering"],
            log_rosseland,
        ),
        "krosseland_absorption": absorption_regroup(
            fields["krosseland_absorption"],
            fields["krosseland"],
            log_rosseland,
        ),
    }

    failed = False
    print()
    print("1024 groups -> 1 group conservation")
    for field in FIELDS:
        actual = reconstructed[field]
        reference = one_fields[field]
        stats = error_statistics(
            actual,
            reference,
            args.atol,
        )

        close = np.allclose(
            actual,
            reference,
            rtol=args.rtol,
            atol=args.atol,
            equal_nan=False,
        )
        failed = failed or not close

        print(field)
        print(f"  allclose:   {close}")
        print(f"  median rel: {stats['median_rel']:.6e}")
        print(f"  99% rel:    {stats['q99_rel']:.6e}")
        print(f"  99.9% rel:  {stats['q999_rel']:.6e}")
        print(f"  max rel:    {stats['max_rel']:.6e}")
        print(f"  max abs:    {stats['max_abs']:.6e}")

        if not close:
            relative = np.abs(actual - reference) / np.maximum(
                np.abs(reference),
                args.atol,
            )
            flat = int(np.argmax(relative))
            i_rho, j_temp = np.unravel_index(
                flat,
                relative.shape,
            )
            print(
                "  worst cell: "
                f"rho_index={i_rho}, temp_index={j_temp}, "
                f"rho={densities[i_rho]:.16e}, "
                f"T={temperatures[j_temp]:.16e}, "
                f"reconstructed={actual[i_rho, j_temp]:.16e}, "
                f"reference={reference[i_rho, j_temp]:.16e}"
            )

    print()
    if failed:
        print(
            "FAIL: split tables do not preserve the direct one-group "
            "collapse at the requested tolerance."
        )
        return 1

    print(
        "PASS: split tables preserve the direct one-group Planck, "
        "Rosseland, scattering, and flux-weighted absorption means."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
