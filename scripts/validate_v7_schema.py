#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REQUIRED_FIELDS = {
    'kplanck',
    'kplanck_scattering',
    'krosseland',
    'krosseland_absorption',
}
STALE_FIELDS = {'kross_scattering'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--parts-dir', type=Path, default=Path('solar_final/group_collapse')
    )
    parser.add_argument(
        '--web-data-dir', type=Path, default=Path('solar_final/web_data')
    )
    parser.add_argument(
        '--pattern', default='opacity_group_collapse_part*.npz'
    )
    args = parser.parse_args()

    parts = sorted(args.parts_dir.glob(args.pattern))
    if not parts:
        raise FileNotFoundError('No split collapse files found')

    total_zeros = {field: 0 for field in REQUIRED_FIELDS}
    for path in parts:
        with np.load(path, allow_pickle=False) as data:
            names = set(data.files)
            missing = REQUIRED_FIELDS - names
            stale = STALE_FIELDS & names
            if missing:
                raise KeyError(f'{path.name} missing {sorted(missing)}')
            if stale:
                raise ValueError(f'{path.name} contains stale {sorted(stale)}')
            for field in REQUIRED_FIELDS:
                values = np.asarray(data[field])
                if np.any(values < 0) or np.any(~np.isfinite(values)):
                    raise ValueError(f'{path.name}:{field} contains invalid values')
                total_zeros[field] += int(np.count_nonzero(values == 0))
        print(f'OK {path.name}')

    manifest_path = args.web_data_dir / 'manifest.json'
    plot_manifest_path = args.web_data_dir / 'plot' / 'manifest.json'
    for path in (manifest_path, plot_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    web_fields = set(manifest['field_metadata'])
    if web_fields != REQUIRED_FIELDS:
        raise ValueError(
            f'Browser manifest fields are {sorted(web_fields)}, '
            f'expected {sorted(REQUIRED_FIELDS)}'
        )

    plot_manifest = json.loads(plot_manifest_path.read_text(encoding='utf-8'))
    plot_fields = set(plot_manifest['fields'])
    if plot_fields != REQUIRED_FIELDS:
        raise ValueError(
            f'Plot manifest fields are {sorted(plot_fields)}, '
            f'expected {sorted(REQUIRED_FIELDS)}'
        )

    print('Zero counts:')
    for field in sorted(REQUIRED_FIELDS):
        print(f'  {field:28s} {total_zeros[field]:12d}')
    print('PASS: no stale Rosseland-scattering field remains.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
