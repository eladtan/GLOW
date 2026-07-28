#!/usr/bin/env python3
import importlib.util
import math
from pathlib import Path
import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    PACKAGE_ROOT / 'original_collapse_source_planck_scattering.py',
    PACKAGE_ROOT / 'scripts' / 'generate_opacity_tables_planck_scattering.py',
)
MODULE_PATH = next((path for path in CANDIDATES if path.is_file()), CANDIDATES[0])
spec = importlib.util.spec_from_file_location('collapse', MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f'Could not import {MODULE_PATH}')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def regroup(collapse, edges, temperature):
    low = edges[:-1] / temperature
    high = edges[1:] / temperature
    mid = 0.5 * (low + high)
    half = 0.5 * (high - low)
    u_nodes = mid[:, None] + half[:, None] * mod.EMPTY_BIN_GL_X[None, :]
    logq = np.log(mod.EMPTY_BIN_GL_W)[None, :]
    logp_nodes = mod.planck_log_weight_u(u_nodes) + logq
    logr_nodes = mod.rosseland_log_weight_u(u_nodes) + logq
    logp = np.array([
        math.log(half[i]) + mod._logsumexp_1d(logp_nodes[i])
        for i in range(len(half))
    ])
    logr = np.array([
        math.log(half[i]) + mod._logsumexp_1d(logr_nodes[i])
        for i in range(len(half))
    ])
    return mod._regroup_collapse_fields(collapse, logp, logr)


def main():
    temperature = 7.3
    hnu = np.logspace(-2, 4, 401)
    u = hnu / temperature
    x = np.log(hnu)
    absorption = 2.0 + 0.3 * np.sin(1.7 * x) ** 2 + 0.01 * hnu ** 0.2
    scattering = 0.2 + 0.04 * np.cos(0.8 * x) ** 2

    # Genuine zero intervals in both arithmetic fields. They must remain local
    # zeros, but positive opacity elsewhere must keep the full Planck means > 0.
    absorption[(hnu > 500.0) & (hnu < 700.0)] = 0.0
    scattering[(hnu > 50.0) & (hnu < 80.0)] = 0.0

    bb = 0.5 * absorption
    bf = 0.3 * absorption
    ff = 0.2 * absorption

    targets = {
        'kplanck': 3.25,
        'krosseland': 1.75,
        'kplanck_scattering': 0.225,
        'krosseland_absorption': 2.15,
    }

    edges1024 = np.logspace(np.log10(hnu[0]), np.log10(hnu[-1]), 1025)
    c1024 = mod.compute_group_collapse(
        hnu, u, bb, bf, ff, scattering, edges1024, targets
    )
    r1024 = regroup(c1024, edges1024, temperature)

    edges1 = np.array([hnu[0], hnu[-1]])
    c1 = mod.compute_group_collapse(
        hnu, u, bb, bf, ff, scattering, edges1, targets
    )
    r1 = regroup(c1, edges1, temperature)

    for field, target in targets.items():
        assert math.isclose(
            r1024[field], target, rel_tol=5e-13, abs_tol=1e-14
        ), (field, r1024[field], target)
        assert math.isclose(
            r1[field], target, rel_tol=5e-13, abs_tol=1e-14
        ), (field, r1[field], target)

    assert np.count_nonzero(c1024['kplanck'] == 0.0) > 0
    assert np.count_nonzero(c1024['krosseland_absorption'] == 0.0) > 0
    assert np.count_nonzero(c1024['kplanck_scattering'] == 0.0) > 0
    assert np.all(c1024['krosseland'] > 0.0)

    # Crucial regression: local zero scattering groups must not force the
    # full-range Planck scattering mean to zero.
    assert r1024['kplanck_scattering'] > 0.0
    assert math.isclose(
        r1024['kplanck_scattering'], targets['kplanck_scattering'],
        rel_tol=5e-13, abs_tol=1e-14,
    )

    # Wien-tail underflow regression.
    T2 = 1.0
    hnu2 = np.linspace(800.0, 1000.0, 101)
    u2 = hnu2 / T2
    a2 = np.full_like(hnu2, 2.0)
    s2 = np.full_like(hnu2, 0.5)
    targets2 = {
        'kplanck': 2.0,
        'krosseland': 2.5,
        'kplanck_scattering': 0.5,
        'krosseland_absorption': 2.0,
    }
    edges2 = np.linspace(800.0, 1000.0, 65)
    c2 = mod.compute_group_collapse(
        hnu2, u2, a2, np.zeros_like(a2), np.zeros_like(a2), s2,
        edges2, targets2,
    )
    r2 = regroup(c2, edges2, T2)
    for field, target in targets2.items():
        assert math.isclose(
            r2[field], target, rel_tol=5e-13, abs_tol=1e-14
        ), (field, r2[field], target)

    print('Planck-scattering conservative collapse tests passed.')
    for field in targets:
        print(
            f'{field}: 1024->1={r1024[field]:.16e}, '
            f'direct1={r1[field]:.16e}, target={targets[field]:.16e}'
        )


if __name__ == '__main__':
    main()
