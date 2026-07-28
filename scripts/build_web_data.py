#!/usr/bin/env python3
"""Build browser-ready chunked opacity data from validated split NPZ tables.

Output layout
-------------
<web-data>/manifest.json
<web-data>/axes.json
<web-data>/chunks/partXX/<field>_g####_####.f64.gz

Each chunk stores little-endian float64 values in C order with axis order
[group, rho, temp].  The manifest records the exact shape and byte counts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

FIELDS = (
    'kplanck',
    'kplanck_scattering',
    'krosseland',
    'krosseland_absorption',
)

FIELD_METADATA = {
    'kplanck': {
        'label': 'Planck-mean absorption opacity',
        'weighting': 'Planck arithmetic',
        'description': 'Planck-weighted arithmetic mean of true absorption.',
    },
    'kplanck_scattering': {
        'label': 'Planck-mean scattering opacity',
        'weighting': 'Planck arithmetic',
        'description': 'Planck-weighted arithmetic mean of scattering opacity.',
    },
    'krosseland': {
        'label': 'Rosseland-mean total opacity',
        'weighting': 'Rosseland harmonic',
        'description': 'Rosseland harmonic mean of absorption plus scattering.',
    },
    'krosseland_absorption': {
        'label': 'Rosseland flux-weighted absorption opacity',
        'weighting': 'Rosseland transport',
        'description': (
            'Flux-weighted absorption using the total opacity in the '
            'transport denominator.'
        ),
    },
}


def gzip_float64(path: Path, values: np.ndarray, level: int) -> dict[str, object]:
    array = np.asarray(values, dtype='<f8', order='C')
    raw = array.tobytes(order='C')
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(
        filename=str(path), mode='wb', compresslevel=level, mtime=0
    ) as handle:
        handle.write(raw)
    compressed = path.read_bytes()
    return {
        'file': path.as_posix(),
        'shape': list(array.shape),
        'dtype': 'float64-le',
        'axis_order': ['group', 'rho', 'temp'],
        'uncompressed_bytes': len(raw),
        'compressed_bytes': len(compressed),
        'sha256': hashlib.sha256(compressed).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--parts-dir', type=Path, default=Path('solar_final/group_collapse')
    )
    parser.add_argument(
        '--pattern', default='opacity_group_collapse_part*.npz'
    )
    parser.add_argument(
        '--output-dir', type=Path, default=Path('solar_final/web_data')
    )
    parser.add_argument('--group-chunk-size', type=int, default=64)
    parser.add_argument('--gzip-level', type=int, default=9)
    args = parser.parse_args()

    if args.group_chunk_size <= 0:
        raise ValueError('--group-chunk-size must be positive')

    parts_dir = args.parts_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    paths = sorted(parts_dir.glob(args.pattern))
    if not paths:
        raise FileNotFoundError(f'No files match {parts_dir / args.pattern}')

    reference_edges = None
    reference_rho = None
    all_temperatures: list[np.ndarray] = []
    manifest_parts: list[dict[str, object]] = []
    global_temp_start = 0

    # Refuse stale mixed-schema output.
    output_dir.mkdir(parents=True, exist_ok=True)

    for part_index, path in enumerate(paths):
        with np.load(path, allow_pickle=False) as data:
            required = {'hnu_ev_edges', 'temp_eV', 'rho_gcc', *FIELDS}
            missing = sorted(required.difference(data.files))
            if missing:
                raise KeyError(f'{path.name} is missing {missing}')
            if 'kross_scattering' in data.files:
                raise ValueError(
                    f'{path.name} contains stale kross_scattering. '
                    'Regenerate with the v7 Planck-scattering generator.'
                )

            edges = np.asarray(data['hnu_ev_edges'], dtype=np.float64)
            rho = np.asarray(data['rho_gcc'], dtype=np.float64)
            temp = np.asarray(data['temp_eV'], dtype=np.float64)

            if reference_edges is None:
                reference_edges = edges
                reference_rho = rho
            else:
                if not np.array_equal(edges, reference_edges):
                    raise ValueError(f'Energy edges differ in {path.name}')
                if not np.array_equal(rho, reference_rho):
                    raise ValueError(f'Density axis differs in {path.name}')

            if temp.ndim != 1 or temp.size == 0 or np.any(np.diff(temp) <= 0):
                raise ValueError(f'Invalid temperature axis in {path.name}')

            all_temperatures.append(temp)
            n_groups = edges.size - 1
            expected = (n_groups, rho.size, temp.size)
            chunks: list[dict[str, object]] = []

            for field in FIELDS:
                values = np.asarray(data[field], dtype=np.float64)
                if values.shape != expected:
                    raise ValueError(
                        f'{path.name}:{field} has {values.shape}; expected {expected}'
                    )
                if np.any(values < 0.0) or np.any(~np.isfinite(values)):
                    raise ValueError(f'{path.name}:{field} contains invalid values')

                for group_start in range(0, n_groups, args.group_chunk_size):
                    group_stop = min(n_groups, group_start + args.group_chunk_size)
                    relative = Path('chunks') / f'part{part_index:02d}' / (
                        f'{field}_g{group_start:04d}_{group_stop:04d}.f64.gz'
                    )
                    metadata = gzip_float64(
                        output_dir / relative,
                        values[group_start:group_stop, :, :],
                        args.gzip_level,
                    )
                    # Store path relative to web_data, not absolute.
                    metadata['file'] = relative.as_posix()
                    metadata.update(
                        {
                            'field': field,
                            'group_start': group_start,
                            'group_stop': group_stop,
                        }
                    )
                    chunks.append(metadata)

            global_temp_stop = global_temp_start + temp.size
            manifest_parts.append(
                {
                    'part_index': part_index,
                    'source_file': path.name,
                    'temperature_global_start': global_temp_start,
                    'temperature_global_stop': global_temp_stop,
                    'temperature_count': int(temp.size),
                    'chunks': chunks,
                }
            )
            global_temp_start = global_temp_stop
            print(
                f'{path.name}: {temp.size} temperatures, '
                f'{len(chunks)} chunks'
            )

    assert reference_edges is not None and reference_rho is not None
    temperatures = np.concatenate(all_temperatures)
    if np.any(np.diff(temperatures) <= 0):
        raise ValueError('Combined temperature axis is not strictly increasing')

    axes = {
        'temp_eV': temperatures.tolist(),
        'rho_gcc': reference_rho.tolist(),
        'hnu_ev_edges': reference_edges.tolist(),
    }
    (output_dir / 'axes.json').write_text(
        json.dumps(axes, separators=(',', ':')) + '\n', encoding='utf-8'
    )

    total_compressed = sum(
        int(chunk['compressed_bytes'])
        for part in manifest_parts
        for chunk in part['chunks']
    )
    manifest = {
        'version': 2,
        'schema': 'glow-planck-scattering-v7',
        'dimensions': {
            'groups': int(reference_edges.size - 1),
            'densities': int(reference_rho.size),
            'temperatures': int(temperatures.size),
        },
        'storage': {
            'dtype': 'float64-le',
            'compression': 'gzip',
            'axis_order': ['group', 'rho', 'temp'],
            'group_chunk_size': args.group_chunk_size,
        },
        'field_metadata': FIELD_METADATA,
        'parts': manifest_parts,
        'total_compressed_bytes': total_compressed,
    }
    (output_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )

    print(f'Wrote {output_dir / "manifest.json"}')
    print(f'Wrote {output_dir / "axes.json"}')
    print(f'Total compressed chunk bytes: {total_compressed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
