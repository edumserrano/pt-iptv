from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path

WORKING_VERDICT = "working"


def read_report(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row.get("tvg_id", row.get("name", "")): row for row in csv.DictReader(handle)}


def is_working(row: dict[str, str] | None) -> bool:
    return bool(row) and row.get("verdict") == WORKING_VERDICT


def source_changed(before: dict[str, str], after: dict[str, str]) -> bool:
    return (before.get("url") or "").strip() != (after.get("url") or "").strip()


def names(rows: list[dict[str, str]]) -> str:
    return ", ".join(row.get("name", "") for row in rows)


def append_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return "\n"


def restore_first_stream_url(path: Path, url: str) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines[index] = url + line_ending(line)
            path.write_text("".join(lines), encoding="utf-8", newline="")
            return
    raise ValueError(f"No stream URL found in {path}")


def playlist_entry_tvg_id(line: str) -> str | None:
    if not line.startswith("#EXTINF"):
        return None
    match = re.search(r'tvg-id="([^"]+)"', line)
    return match.group(1) if match else None


def restore_playlist_entry_url(path: Path, tvg_id: str, url: str) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    in_entry = False

    for index, line in enumerate(lines):
        current_tvg_id = playlist_entry_tvg_id(line)
        if current_tvg_id is not None:
            in_entry = current_tvg_id == tvg_id
            continue

        if not in_entry:
            continue

        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines[index] = url + line_ending(line)
            path.write_text("".join(lines), encoding="utf-8", newline="")
            return

    raise ValueError(f"No playlist URL found for tvg-id {tvg_id} in {path}")


def restore_regression(repo_root: Path, playlist_path: Path, before: dict[str, str]) -> None:
    tvg_id = before.get("tvg_id", "")
    before_url = before.get("url", "").strip()
    if not before_url:
        return

    if tvg_id.startswith("M3U/"):
        restore_first_stream_url(repo_root / tvg_id, before_url)
    else:
        restore_playlist_entry_url(playlist_path, tvg_id, before_url)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--playlist", type=Path, default=Path("M3U/M3UPT.m3u"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--restore-regressions", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    playlist_path = args.playlist if args.playlist.is_absolute() else repo_root / args.playlist
    before_rows = read_report(args.before)
    after_rows = read_report(args.after)

    fixed: list[dict[str, str]] = []
    updated_fixed: list[dict[str, str]] = []
    still_broken: list[dict[str, str]] = []
    regressed: list[dict[str, str]] = []
    updated_regressed: list[dict[str, str]] = []
    unchanged_regressed: list[dict[str, str]] = []

    for key, after in after_rows.items():
        before = before_rows.get(key)
        if before is None:
            continue

        changed = source_changed(before, after)
        before_working = is_working(before)
        after_working = is_working(after)

        if not before_working and after_working:
            fixed.append(after)
            if changed:
                updated_fixed.append(after)
        elif not before_working and not after_working:
            still_broken.append(after)
        elif before_working and not after_working:
            regressed.append(after)
            if changed:
                updated_regressed.append(after)
            else:
                unchanged_regressed.append(after)

    restored: list[dict[str, str]] = []
    if args.restore_regressions:
        for after in updated_regressed:
            before = before_rows[after.get("tvg_id", after.get("name", ""))]
            restore_regression(repo_root, playlist_path, before)
            restored.append(after)

    outputs = {
        "fixed_count": str(len(fixed)),
        "fixed_names": names(fixed),
        "updated_fixed_count": str(len(updated_fixed)),
        "updated_fixed_names": names(updated_fixed),
        "still_broken_count": str(len(still_broken)),
        "still_broken_names": names(still_broken),
        "regressed_count": str(len(regressed)),
        "regressed_names": names(regressed),
        "updated_regressed_count": str(len(updated_regressed)),
        "updated_regressed_names": names(updated_regressed),
        "unchanged_regressed_count": str(len(unchanged_regressed)),
        "unchanged_regressed_names": names(unchanged_regressed),
        "restored_regressed_count": str(len(restored)),
        "restored_regressed_names": names(restored),
    }
    outputs["pr_ready"] = (
        "true" if outputs["updated_fixed_count"] != "0" and outputs["updated_regressed_count"] == "0" else "false"
    )

    append_github_output(outputs)
    print(json.dumps(outputs, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
