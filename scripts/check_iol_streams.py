from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from audit_streams import Entry, check_entry, parse_playlist  # noqa: E402


WORKING_VERDICT = "working"

AFFECTED_PLAYLIST_TVG_IDS = {
    "TVI.pt": "TVI",
    "CNNPortugal.pt": "CNN Portugal",
    "TVIInternacional.pt": "TVI Internacional",
    "VPlusTVI.pt": "V+ TVI",
    "TVIFiccao.pt": "TVI Ficção",
    "TVIReality.pt": "TVI Reality",
}

AFFECTED_SIDECARS = {
    "M3U/TVI.m3u8": "TVI sidecar",
    "M3U/CNN_Portugal.m3u8": "CNN Portugal sidecar",
    "M3U/TVI_Internacional.m3u8": "TVI Internacional sidecar",
    "M3U/Vmais_TVI.m3u8": "V+ TVI sidecar",
    "M3U/TVI_Ficcao.m3u8": "TVI Ficção sidecar",
    "M3U/TVI_Reality.m3u8": "TVI Reality sidecar",
}

AFFECTED_SIDECAR_TVG_IDS = {
    "M3U/TVI.m3u8": "TVI.pt",
    "M3U/CNN_Portugal.m3u8": "CNNPortugal.pt",
    "M3U/TVI_Internacional.m3u8": "TVIInternacional.pt",
    "M3U/Vmais_TVI.m3u8": "VPlusTVI.pt",
    "M3U/TVI_Ficcao.m3u8": "TVIFiccao.pt",
    "M3U/TVI_Reality.m3u8": "TVIReality.pt",
}

AFFECTED_PLAYLIST_SIDECARS = {
    "TVI.pt": "M3U/TVI.m3u8",
    "CNNPortugal.pt": "M3U/CNN_Portugal.m3u8",
    "TVIInternacional.pt": "M3U/TVI_Internacional.m3u8",
    "VPlusTVI.pt": "M3U/Vmais_TVI.m3u8",
    "TVIFiccao.pt": "M3U/TVI_Ficcao.m3u8",
    "TVIReality.pt": "M3U/TVI_Reality.m3u8",
}


def first_stream_url(path: Path) -> str | None:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                return line
    return None


def local_sidecar_stream_url(repo_root: Path, tvg_id: str, playlist_url: str | None) -> str | None:
    relative_path = AFFECTED_PLAYLIST_SIDECARS.get(tvg_id)
    if not relative_path or not playlist_url:
        return None

    parsed = urllib.parse.urlsplit(playlist_url.strip())
    path = urllib.parse.unquote(parsed.path).lstrip("/")
    points_to_local_sidecar = (
        (parsed.netloc == "edumserrano.github.io" and path == f"pt-iptv/{relative_path}")
        or (parsed.netloc == "raw.githubusercontent.com" and path == f"edumserrano/pt-iptv/main/{relative_path}")
        or (parsed.netloc == "github.com" and path == f"edumserrano/pt-iptv/raw/main/{relative_path}")
        or (not parsed.scheme and path in {relative_path, f"./{relative_path}"})
    )
    if not points_to_local_sidecar:
        return None

    sidecar_path = repo_root / relative_path
    return first_stream_url(sidecar_path) if sidecar_path.exists() else None


def affected_entries(repo_root: Path, playlist_path: Path) -> list[Entry]:
    playlist_entries = parse_playlist(playlist_path)
    playlist_entries_by_tvg_id = {entry.tvg_id: entry for entry in playlist_entries if entry.tvg_id}
    entries: list[Entry] = []

    for tvg_id, label in AFFECTED_PLAYLIST_TVG_IDS.items():
        match = next((entry for entry in playlist_entries if entry.tvg_id == tvg_id), None)
        if match is None:
            entries.append(
                Entry(
                    index=len(entries) + 1,
                    line=0,
                    name=label,
                    group="TV",
                    tvg_id=tvg_id,
                    url=None,
                )
            )
        else:
            stream_url = local_sidecar_stream_url(repo_root, tvg_id, match.url)
            entry = Entry(
                index=match.index,
                line=match.line,
                name=match.name,
                group=match.group,
                tvg_id=match.tvg_id,
                url=stream_url or match.url,
                radio=match.radio,
                headers=match.headers,
            )
            if stream_url:
                setattr(entry, "reported_url", match.url or "")
            entries.append(entry)

    for relative_path, label in AFFECTED_SIDECARS.items():
        sidecar_path = repo_root / relative_path
        url = first_stream_url(sidecar_path) if sidecar_path.exists() else None
        playlist_entry = playlist_entries_by_tvg_id.get(AFFECTED_SIDECAR_TVG_IDS.get(relative_path, ""))
        entries.append(
            Entry(
                index=len(entries) + 1,
                line=1,
                name=label,
                group="IOL sidecar",
                tvg_id=relative_path,
                url=url,
                headers=dict(playlist_entry.headers) if playlist_entry else {},
            )
        )

    return entries


def write_reports(results: list[dict[str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "name",
        "tvg_id",
        "verdict",
        "reason",
        "http_status",
        "detail",
        "url",
        "final_url",
    ]
    with (output_dir / "iol-token-stream-check.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({field: row.get(field, "") for field in fields})

    broken = [row for row in results if row.get("verdict") != "working"]
    with (output_dir / "iol-token-stream-check.md").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# IOL Token Stream Check\n\n")
        handle.write(f"Streams checked: {len(results)}\n\n")
        handle.write(f"Broken streams: {len(broken)}\n\n")
        handle.write("| Channel | Verdict | Reason | HTTP | Detail |\n")
        handle.write("|---|---|---|---:|---|\n")
        for row in results:
            detail = (row.get("detail", "") or "").replace("|", "\\|")[:120]
            handle.write(
                f"| {row.get('name', '')} | {row.get('verdict', '')} | {row.get('reason', '')} | "
                f"{row.get('http_status', '')} | {detail} |\n"
            )


def summarize_attempt(row: dict[str, str], attempt: int) -> str:
    pieces = [str(attempt), row.get("verdict", ""), row.get("reason", "")]
    status = row.get("http_status", "")
    if status:
        pieces.append(status)
    return "/".join(piece for piece in pieces if piece)


def check_entry_with_success_retry(entry: Entry, timeout: float, attempts: int) -> dict[str, str]:
    attempts = max(1, attempts)
    results = [check_entry(entry, timeout) for _ in range(attempts)]
    successes = [row for row in results if row.get("verdict") == WORKING_VERDICT]
    selected = dict(successes[0] if successes else results[-1])

    if attempts > 1:
        selected["detail"] = (
            f"{len(successes)}/{attempts} attempts working; "
            f"{selected.get('detail', '')}; "
            f"attempts: {'; '.join(summarize_attempt(row, index + 1) for index, row in enumerate(results))}"
        )
    return selected


def cached_result_for_entry(entry: Entry, cached: dict[str, str]) -> dict[str, str]:
    return {
        **cached,
        "index": str(entry.index),
        "line": str(entry.line),
        "name": entry.name,
        "group": entry.group,
        "tvg_id": entry.tvg_id,
        "url": entry.url or "",
    }


def append_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--playlist", type=Path, default=Path("M3U/M3UPT.m3u"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    playlist_path = args.playlist if args.playlist.is_absolute() else repo_root / args.playlist
    entries = affected_entries(repo_root, playlist_path)
    results = []
    result_cache: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, str]] = {}
    for entry in entries:
        cache_key = (entry.url or "", tuple(sorted(entry.headers.items())))
        if cache_key in result_cache:
            result = cached_result_for_entry(entry, result_cache[cache_key])
        else:
            result = check_entry_with_success_retry(entry, args.timeout, args.attempts)
            result_cache[cache_key] = dict(result)
        reported_url = getattr(entry, "reported_url", None)
        if reported_url is not None:
            result["url"] = reported_url
        results.append(result)
    broken = [row for row in results if row.get("verdict") != "working"]
    broken_names = ", ".join(row.get("name", "") for row in broken)

    write_reports(results, args.output_dir)
    summary = {
        "checked_count": str(len(results)),
        "broken_count": str(len(broken)),
        "broken_names": broken_names,
        "all_working": "true" if not broken else "false",
    }
    append_github_output(summary)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
