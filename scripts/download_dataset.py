from __future__ import annotations

import argparse
from pathlib import Path

import gdown


DEFAULT_FOLDER_ID = "1ZexqdCYpCQPpSjxL38Y8NpvPNCz_lJwH"


def target_path(root: Path, drive_path: str) -> Path:
    parts = Path(drive_path).parts
    if parts and parts[0] == "assignment_videos":
        return root.joinpath("videos", *parts[1:])
    return root.joinpath(*parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the project Google Drive dataset.")
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID)
    parser.add_argument("--output-dir", type=Path, default=Path("data/inputs"))
    args = parser.parse_args()

    files = gdown.download_folder(
        id=args.folder_id,
        output=str(args.output_dir),
        quiet=True,
        skip_download=True,
    )

    failures: list[tuple[str, str]] = []
    downloaded = 0
    skipped = 0
    for file in files:
        output_path = target_path(args.output_dir, file.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and output_path.stat().st_size > 0:
            skipped += 1
            continue

        try:
            result = gdown.download(
                id=file.id,
                output=str(output_path),
                quiet=False,
                resume=True,
            )
        except Exception as exc:  # gdown raises generic exceptions for Drive access failures.
            failures.append((file.path, str(exc)))
            continue

        if result is None:
            failures.append((file.path, "gdown returned no output path"))
        else:
            downloaded += 1

    print(
        f"Dataset download complete: downloaded={downloaded}, skipped={skipped}, "
        f"failed={len(failures)}"
    )
    if failures:
        print("Failed files:")
        for path, reason in failures:
            print(f"- {path}: {reason}")


if __name__ == "__main__":
    main()
