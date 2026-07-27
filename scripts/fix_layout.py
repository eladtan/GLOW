#!/usr/bin/env python3

import json
import shutil
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPOSITORY_ROOT / "solar_final"
OLD_METADATA_DIR = DATA_DIR / "group_collapse"

OLD_MANIFEST_PATH = OLD_METADATA_DIR / "manifest.json"
OLD_FREQUENCY_PATH = OLD_METADATA_DIR / "frequency_groups.csv"

NEW_MANIFEST_PATH = DATA_DIR / "manifest.json"
NEW_FREQUENCY_PATH = DATA_DIR / "frequency_groups.csv"

BACKUP_MANIFEST_PATH = DATA_DIR / "manifest.original.json"


def require_file(path: Path) -> None:
    """Exit with a clear error if a required file is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"Required file does not exist: {path}")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def main() -> None:
    print(f"Repository root: {REPOSITORY_ROOT}")
    print(f"Data directory:  {DATA_DIR}")
    print()

    require_file(OLD_MANIFEST_PATH)
    require_file(OLD_FREQUENCY_PATH)

    manifest = load_json(OLD_MANIFEST_PATH)

    temperature_parts = manifest.get("temperature_parts")

    if not isinstance(temperature_parts, list):
        raise ValueError(
            "The manifest does not contain a valid "
            "'temperature_parts' list."
        )

    # Save an unchanged backup of the original manifest.
    if BACKUP_MANIFEST_PATH.exists():
        print(
            "Backup already exists; leaving it unchanged:"
            f" {BACKUP_MANIFEST_PATH}"
        )
    else:
        shutil.copy2(
            OLD_MANIFEST_PATH,
            BACKUP_MANIFEST_PATH,
        )
        print(
            "Created original-manifest backup:"
            f" {BACKUP_MANIFEST_PATH}"
        )

    expected_npz_files = []

    for part in temperature_parts:
        if "part_index" not in part:
            raise ValueError(
                "A temperature part is missing 'part_index'."
            )

        part_index = int(part["part_index"])
        expected_filename = (
            f"opacity_tables_part{part_index:02d}.npz"
        )
        expected_path = DATA_DIR / expected_filename

        require_file(expected_path)
        expected_npz_files.append(expected_filename)

        # Replace the old file mapping, which referred to files that
        # were not uploaded, with the file that actually exists.
        part["files"] = {
            "opacity_tables": expected_filename
        }

    # Since the manifest now resides in solar_final/, this is relative
    # to the manifest location.
    manifest["unsplit_files"] = [
        "frequency_groups.csv"
    ]

    # Add explicit information useful to the future website.
    manifest["data_format"] = "numpy_npz"
    manifest["data_directory"] = "."
    manifest["available_datasets"] = [
        "opacity_tables"
    ]

    # Move frequency_groups.csv unless it is already present.
    if NEW_FREQUENCY_PATH.exists():
        if (
            OLD_FREQUENCY_PATH.read_bytes()
            != NEW_FREQUENCY_PATH.read_bytes()
        ):
            raise FileExistsError(
                "A different frequency_groups.csv already exists at "
                f"{NEW_FREQUENCY_PATH}"
            )

        print(
            "Target frequency file already exists and is identical."
        )
        OLD_FREQUENCY_PATH.unlink()
    else:
        shutil.move(
            str(OLD_FREQUENCY_PATH),
            str(NEW_FREQUENCY_PATH),
        )
        print(
            f"Moved frequency file to: {NEW_FREQUENCY_PATH}"
        )

    # Write the cleaned manifest at its new location.
    if NEW_MANIFEST_PATH.exists():
        print(
            f"Replacing existing manifest: {NEW_MANIFEST_PATH}"
        )

    write_json(NEW_MANIFEST_PATH, manifest)
    print(f"Wrote cleaned manifest: {NEW_MANIFEST_PATH}")

    # Remove the old manifest after the new one was written
    # successfully.
    if OLD_MANIFEST_PATH.exists():
        OLD_MANIFEST_PATH.unlink()
        print(f"Removed old manifest: {OLD_MANIFEST_PATH}")

    # Remove the old directory only if nothing remains inside it.
    if OLD_METADATA_DIR.exists():
        remaining_files = list(OLD_METADATA_DIR.iterdir())

        if remaining_files:
            print()
            print(
                "The old group_collapse directory was not removed "
                "because it still contains:"
            )

            for path in remaining_files:
                print(f"  - {path.name}")
        else:
            OLD_METADATA_DIR.rmdir()
            print(
                f"Removed empty directory: {OLD_METADATA_DIR}"
            )

    print()
    print("Validated NPZ files:")

    for filename in expected_npz_files:
        size_mb = (DATA_DIR / filename).stat().st_size / 1024**2
        print(f"  - {filename}: {size_mb:.2f} MiB")

    print()
    print("Final expected layout:")
    print("  solar_final/")
    print("  ├── manifest.json")
    print("  ├── manifest.original.json")
    print("  ├── frequency_groups.csv")

    for filename in expected_npz_files:
        print(f"  ├── {filename}")

    print()
    print("Data-layout update completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)