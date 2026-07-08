from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


KEY_CHANNELS = [
    {
        "label": "RTP1",
        "tvg_ids": {"rtp1.pt"},
        "names": {"rtp 1", "rtp1"},
    },
    {
        "label": "RTP2",
        "tvg_ids": {"rtp2.pt"},
        "names": {"rtp 2", "rtp2"},
    },
    {
        "label": "SIC",
        "tvg_ids": {"sic.pt"},
        "names": {"sic"},
    },
    {
        "label": "SIC Noticias",
        "tvg_ids": {"sicnoticias.pt"},
        "names": {"sic noticias"},
    },
    {
        "label": "CNN Portugal",
        "tvg_ids": {"cnnportugal.pt"},
        "names": {"cnn portugal"},
    },
    {
        "label": "TVI",
        "tvg_ids": {"tvi.pt"},
        "names": {"tvi"},
    },
    {
        "label": "Sport TV 1",
        "tvg_ids": {"sporttv1.pt", "sporttv.pt"},
        "names": {"sport tv 1", "sport tv1", "sporttv 1", "sporttv1", "sport tv 1 pt", "sport tv1 pt"},
    },
    {
        "label": "Sport TV 2",
        "tvg_ids": {"sporttv2.pt"},
        "names": {"sport tv 2", "sport tv2", "sporttv 2", "sporttv2", "sport tv 2 pt", "sport tv2 pt"},
    },
    {
        "label": "Sport TV 3",
        "tvg_ids": {"sporttv3.pt"},
        "names": {"sport tv 3", "sport tv3", "sporttv 3", "sporttv3", "sport tv 3 pt", "sport tv3 pt"},
    },
    {
        "label": "Sport TV 4",
        "tvg_ids": {"sporttv4.pt"},
        "names": {"sport tv 4", "sport tv4", "sporttv 4", "sporttv4", "sport tv 4 pt", "sport tv4 pt"},
    },
    {
        "label": "Sport TV 5",
        "tvg_ids": {"sporttv5.pt"},
        "names": {"sport tv 5", "sport tv5", "sporttv 5", "sporttv5", "sport tv 5 pt", "sport tv5 pt"},
    },
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.casefold().split())


def channel_key(row: dict[str, str]) -> str:
    tvg_id = (row.get("tvg_id") or "").strip()
    if tvg_id:
        return "id:" + normalize(tvg_id.split("@", 1)[0])
    name = (row.get("name") or "").strip()
    if name:
        return "name:" + normalize(name)
    return ""


def key_channel_row(rows: list[dict[str, str]], channel: dict[str, object]) -> dict[str, str]:
    tvg_ids = channel["tvg_ids"]
    names = channel["names"]

    for row in rows:
        tvg_id = normalize((row.get("tvg_id") or "").split("@", 1)[0])
        if tvg_id in tvg_ids:
            return row

    for row in rows:
        name = normalize(row.get("name", ""))
        if name in names:
            return row

    return {
        "name": str(channel["label"]),
        "verdict": "missing",
        "reason": "missing_from_playlist",
        "http_status": "",
        "detail": "no matching channel entry",
        "line": "",
        "url": "",
        "final_url": "",
    }


def is_missing_from_playlist(row: dict[str, str]) -> bool:
    return row.get("verdict") == "missing" and row.get("reason") == "missing_from_playlist"


def key_channels_present_in(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return [channel for channel in KEY_CHANNELS if not is_missing_from_playlist(key_channel_row(rows, channel))]


def status_summary(row: dict[str, str]) -> str:
    verdict = row.get("verdict", "") or "unknown"
    reason = row.get("reason", "")
    if reason:
        return f"{verdict} ({reason})"
    return verdict


def key_channel_statuses(
    rows: list[dict[str, str]],
    channels: list[dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    statuses = []
    active_channels = KEY_CHANNELS if channels is None else channels
    for channel in active_channels:
        row = key_channel_row(rows, channel)
        statuses.append(
            {
                "label": str(channel["label"]),
                "name": row.get("name", ""),
                "line": row.get("line", ""),
                "verdict": row.get("verdict", ""),
                "reason": row.get("reason", ""),
                "http_status": row.get("http_status", ""),
                "detail": row.get("detail", ""),
                "url": row.get("url", ""),
            }
        )
    return statuses


def key_channel_diff(
    mine_rows: list[dict[str, str]],
    upstream_rows: list[dict[str, str]],
    channels: list[dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    diffs = []
    active_channels = key_channels_present_in(mine_rows) if channels is None else channels
    for channel in active_channels:
        mine = key_channel_row(mine_rows, channel)
        upstream = key_channel_row(upstream_rows, channel)
        mine_verdict = mine.get("verdict", "") or "unknown"
        upstream_verdict = upstream.get("verdict", "") or "unknown"

        if mine_verdict == upstream_verdict:
            diff = "same_verdict"
        elif is_missing_from_playlist(mine):
            diff = "not_in_this_repo"
        elif upstream_verdict == "working" and mine_verdict != "working":
            diff = "upstream_working_this_repo_failing"
        elif mine_verdict == "working" and upstream_verdict != "working":
            diff = "this_repo_working_upstream_failing"
        else:
            diff = "different_failure_status"

        diffs.append(
            {
                "label": str(channel["label"]),
                "this_repo": status_summary(mine),
                "upstream": status_summary(upstream),
                "diff": diff,
                "this_repo_line": mine.get("line", ""),
                "upstream_line": upstream.get("line", ""),
            }
        )
    return diffs


def summarize(rows: list[dict[str, str]]) -> Counter:
    return Counter(row.get("verdict", "") or "unknown" for row in rows)


def reason_summary(rows: list[dict[str, str]]) -> Counter:
    return Counter(row.get("reason", "") or "unknown" for row in rows)


def escape_cell(value: str, limit: int | None = None) -> str:
    text = (value or "").replace("|", "\\|").replace("\n", " ")
    if limit and len(text) > limit:
        return text[: limit - 1] + "..."
    return text


def write_count_table(handle, counts: Counter) -> None:
    handle.write("| Status | Count |\n|---|---:|\n")
    for key, count in counts.most_common():
        handle.write(f"| {escape_cell(key)} | {count} |\n")


def write_failure_table(handle, rows: list[dict[str, str]], limit: int | None = None) -> None:
    handle.write("| # | Line | Channel | Group | Verdict | Reason | HTTP | Detail |\n")
    handle.write("|---:|---:|---|---|---|---|---:|---|\n")
    displayed = rows if limit is None else rows[:limit]
    for row in displayed:
        handle.write(
            "| {index} | {line} | {name} | {group} | {verdict} | {reason} | {http_status} | {detail} |\n".format(
                index=escape_cell(row.get("index", "")),
                line=escape_cell(row.get("line", "")),
                name=escape_cell(row.get("name", "")),
                group=escape_cell(row.get("group", "")),
                verdict=escape_cell(row.get("verdict", "")),
                reason=escape_cell(row.get("reason", "")),
                http_status=escape_cell(row.get("http_status", "")),
                detail=escape_cell(row.get("detail", ""), 120),
            )
        )
    if limit is not None and len(rows) > limit:
        handle.write(f"|  |  | ...and {len(rows) - limit} more |  |  |  |  |  |\n")


def write_key_channel_table(handle, rows: list[dict[str, str]]) -> None:
    handle.write("| Channel | Playlist Name | Line | Verdict | Reason | HTTP | Detail |\n")
    handle.write("|---|---|---:|---|---|---:|---|\n")
    for row in rows:
        handle.write(
            f"| {escape_cell(row['label'])} | {escape_cell(row['name'])} | "
            f"{escape_cell(row['line'])} | {escape_cell(row['verdict'])} | "
            f"{escape_cell(row['reason'])} | {escape_cell(row['http_status'])} | "
            f"{escape_cell(row['detail'], 120)} |\n"
        )


def write_key_channel_diff_table(handle, rows: list[dict[str, str]]) -> None:
    handle.write("| Channel | This Repo | LITUATUI/M3UPT | Diff | This Line | Upstream Line |\n")
    handle.write("|---|---|---|---|---:|---:|\n")
    for row in rows:
        handle.write(
            f"| {escape_cell(row['label'])} | {escape_cell(row['this_repo'])} | "
            f"{escape_cell(row['upstream'])} | {escape_cell(row['diff'])} | "
            f"{escape_cell(row['this_repo_line'])} | {escape_cell(row['upstream_line'])} |\n"
        )


def build_upstream_success_local_failure(
    mine_rows: list[dict[str, str]],
    upstream_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    mine_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in mine_rows:
        key = channel_key(row)
        if key:
            mine_by_key[key].append(row)

    findings: list[dict[str, str]] = []
    for upstream in upstream_rows:
        if upstream.get("verdict") != "working":
            continue
        key = channel_key(upstream)
        if not key:
            continue
        local_matches = mine_by_key.get(key, [])
        if not local_matches:
            continue
        if any(row.get("verdict") == "working" for row in local_matches):
            continue

        local = local_matches[0]
        findings.append(
            {
                "key": key,
                "channel": upstream.get("name", ""),
                "tvg_id": upstream.get("tvg_id", ""),
                "upstream_line": upstream.get("line", ""),
                "upstream_reason": upstream.get("reason", ""),
                "upstream_url": upstream.get("url", ""),
                "local_line": local.get("line", ""),
                "local_verdict": local.get("verdict", ""),
                "local_reason": local.get("reason", ""),
                "local_url": local.get("url", ""),
            }
        )
    return findings


def write_comparison_csv(path: Path, findings: list[dict[str, str]]) -> None:
    fields = [
        "channel",
        "tvg_id",
        "upstream_line",
        "upstream_reason",
        "upstream_url",
        "local_line",
        "local_verdict",
        "local_reason",
        "local_url",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in findings:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_key_channel_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["label", "this_repo", "upstream", "diff", "this_repo_line", "upstream_line"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_report(
    path: Path,
    mine_rows: list[dict[str, str]],
    upstream_rows: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    mine_failures = [row for row in mine_rows if row.get("verdict") != "working"]
    upstream_failures = [row for row in upstream_rows if row.get("verdict") != "working"]
    report_key_channels = key_channels_present_in(mine_rows)
    mine_key_statuses = key_channel_statuses(mine_rows, report_key_channels)
    upstream_key_statuses = key_channel_statuses(upstream_rows, report_key_channels)
    key_diffs = key_channel_diff(mine_rows, upstream_rows, report_key_channels)

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# PT IPTV Stream Health Report\n\n")
        handle.write(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")

        handle.write("## This Repo Health\n\n")
        handle.write(f"Entries checked: {len(mine_rows)}\n\n")
        write_count_table(handle, summarize(mine_rows))
        handle.write("\n### Key Channel Status\n\n")
        write_key_channel_table(handle, mine_key_statuses)
        handle.write("\n### Reason Summary\n\n")
        write_count_table(handle, reason_summary(mine_rows))

        handle.write("\n## LITUATUI/M3UPT Health (Radios Excluded)\n\n")
        handle.write(f"Entries checked: {len(upstream_rows)}\n\n")
        write_count_table(handle, summarize(upstream_rows))
        handle.write("\n### Key Channel Status\n\n")
        write_key_channel_table(handle, upstream_key_statuses)
        handle.write("\n### Reason Summary\n\n")
        write_count_table(handle, reason_summary(upstream_rows))

        handle.write("\n## Upstream Working, This Repo Failing\n\n")
        handle.write("### Key Channel Comparison\n\n")
        write_key_channel_diff_table(handle, key_diffs)
        handle.write("\n### Full Comparison\n\n")
        handle.write(f"Findings: {len(findings)}\n\n")
        handle.write("| Channel | TVG ID | Upstream Line | Local Line | Local Verdict | Local Reason |\n")
        handle.write("|---|---|---:|---:|---|---|\n")
        for row in findings:
            handle.write(
                f"| {escape_cell(row['channel'])} | {escape_cell(row['tvg_id'])} | "
                f"{escape_cell(row['upstream_line'])} | {escape_cell(row['local_line'])} | "
                f"{escape_cell(row['local_verdict'])} | {escape_cell(row['local_reason'])} |\n"
            )

        handle.write("\n## This Repo Detailed Failures\n\n")
        write_failure_table(handle, mine_failures)

        handle.write("\n## LITUATUI/M3UPT Detailed Failures (Radios Excluded)\n\n")
        write_failure_table(handle, upstream_failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mine", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    mine_rows = read_rows(args.mine)
    upstream_rows = read_rows(args.upstream)
    findings = build_upstream_success_local_failure(mine_rows, upstream_rows)

    report_path = args.output_dir / "pt-iptv-stream-health-report.md"
    comparison_csv_path = args.output_dir / "upstream-working-local-failing.csv"
    key_channel_csv_path = args.output_dir / "key-channel-comparison.csv"
    key_diffs = key_channel_diff(mine_rows, upstream_rows)
    write_report(report_path, mine_rows, upstream_rows, findings)
    write_comparison_csv(comparison_csv_path, findings)
    write_key_channel_csv(key_channel_csv_path, key_diffs)

    print(f"combined_markdown={report_path}")
    print(f"comparison_csv={comparison_csv_path}")
    print(f"key_channel_csv={key_channel_csv_path}")
    print(f"upstream_working_local_failing={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
