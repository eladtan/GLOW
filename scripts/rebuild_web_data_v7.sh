#!/usr/bin/env bash
set -euo pipefail

PARTS_DIR="${1:-solar_final/group_collapse}"
WEB_DATA_DIR="${2:-solar_final/web_data}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "$PARTS_DIR" ]]; then
  echo "ERROR: missing parts directory: $PARTS_DIR" >&2
  exit 1
fi

BACKUP="${WEB_DATA_DIR}.before_planck_scattering_v7"
rm -rf "$BACKUP"
if [[ -d "$WEB_DATA_DIR" ]]; then
  mv "$WEB_DATA_DIR" "$BACKUP"
fi
mkdir -p "$WEB_DATA_DIR"

python3 "$SCRIPT_DIR/build_web_data.py" \
  --parts-dir "$PARTS_DIR" \
  --output-dir "$WEB_DATA_DIR"

python3 "$SCRIPT_DIR/build_plot_data.py" \
  --parts-dir "$PARTS_DIR" \
  --web-data-dir "$WEB_DATA_DIR"

python3 "$SCRIPT_DIR/validate_v7_schema.py" \
  --parts-dir "$PARTS_DIR" \
  --web-data-dir "$WEB_DATA_DIR"

echo "Rebuilt v7 browser data in $WEB_DATA_DIR"
if [[ -d "$BACKUP" ]]; then
  echo "Previous browser data kept at $BACKUP"
fi
