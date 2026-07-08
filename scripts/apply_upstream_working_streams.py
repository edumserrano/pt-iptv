from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    start: int
    end: int
    lines: list[str]
    name: str
    tvg_id: str
    url: str


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.casefold().split())


def parse_attrs(extinf: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r'([\w-]+)="([^"]*)"', extinf)}


def channel_key_from_values(tvg_id: str, name: str) -> str:
    clean_tvg_id = (tvg_id or "").strip()
    if clean_tvg_id:
        return "id:" + normalize(clean_tvg_id.split("@", 1)[0])
    clean_name = (name or "").strip()
    if clean_name:
        return "name:" + normalize(clean_name)
    return ""


def channel_key(row: dict[str, str]) -> str:
    return channel_key_from_values(row.get("tvg_id", ""), row.get("name", ""))


def first_stream_url(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def parse_blocks(path: Path) -> tuple[list[str], list[Block]]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    extinf_indexes = [index for index, line in enumerate(lines) if line.startswith("#EXTINF:")]
    if not extinf_indexes:
        return lines, []

    blocks: list[Block] = []
    for offset, start in enumerate(extinf_indexes):
        end = extinf_indexes[offset + 1] if offset + 1 < len(extinf_indexes) else len(lines)
        block_lines = lines[start:end]
        attrs = parse_attrs(block_lines[0])
        name = block_lines[0].rsplit(",", 1)[-1].strip() if "," in block_lines[0] else ""
        blocks.append(
            Block(
                start=start,
                end=end,
                lines=block_lines,
                name=name,
                tvg_id=attrs.get("tvg-id", ""),
                url=first_stream_url(block_lines),
            )
        )
    return lines, blocks


def block_key(block: Block) -> str:
    return channel_key_from_values(block.tvg_id, block.name)


def replacement_lines(local: Block, upstream: Block) -> list[str]:
    upstream_options = [line for line in upstream.lines[1:] if line.startswith("#EXTVLCOPT:")]
    upstream_url = first_stream_url(upstream.lines)

    kept_tail: list[str] = []
    removed_url = False
    for line in local.lines[1:]:
        stripped = line.strip()
        if line.startswith("#EXTVLCOPT:"):
            continue
        if stripped and not stripped.startswith("#") and not removed_url:
            removed_url = True
            continue
        kept_tail.append(line)

    new_lines = [local.lines[0]]
    new_lines.extend(upstream_options)
    if upstream_url:
        new_lines.append(upstream_url)
    new_lines.extend(kept_tail)
    return new_lines


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_report(output_dir: Path, rows: list[dict[str, str]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ["channel", "tvg_id", "status", "reason", "local_url", "upstream_url"]
    with (output_dir / "upstream-auto-update-candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])

    with (output_dir / "upstream-auto-update-candidates.md").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Upstream Auto-Update Candidates\n\n")
        handle.write(f"Candidates inspected: {len(rows)}\n\n")
        handle.write("| Channel | Status | Reason |\n")
        handle.write("|---|---|---|\n")
        for row in rows:
            channel = (row.get("channel", "") or "").replace("|", "\\|")
            status = (row.get("status", "") or "").replace("|", "\\|")
            reason = (row.get("reason", "") or "").replace("|", "\\|")
            handle.write(f"| {channel} | {status} | {reason} |\n")


def append_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def apply_updates(
    local_playlist: Path,
    upstream_playlist: Path,
    mine_audit: Path,
    upstream_audit: Path,
) -> list[dict[str, str]]:
    local_lines, local_blocks = parse_blocks(local_playlist)
    _, upstream_blocks = parse_blocks(upstream_playlist)

    local_blocks_by_line = {str(block.start + 1): block for block in local_blocks}
    upstream_blocks_by_line = {str(block.start + 1): block for block in upstream_blocks}
    local_blocks_by_key: dict[str, Block] = {}
    upstream_blocks_by_key: dict[str, Block] = {}
    for block in local_blocks:
        key = block_key(block)
        if key:
            local_blocks_by_key.setdefault(key, block)
    for block in upstream_blocks:
        key = block_key(block)
        if key:
            upstream_blocks_by_key.setdefault(key, block)
    mine_rows_by_key = {channel_key(row): row for row in read_rows(mine_audit) if channel_key(row)}

    report_rows: list[dict[str, str]] = []
    replacements: list[tuple[Block, list[str]]] = []

    for upstream_row in read_rows(upstream_audit):
        if upstream_row.get("verdict") != "working":
            continue

        key = channel_key(upstream_row)
        if not key:
            continue

        local_row = mine_rows_by_key.get(key)
        if local_row is None or local_row.get("verdict") == "working":
            continue

        local_block = local_blocks_by_line.get(local_row.get("line", "")) if local_row else None
        if local_block is None:
            local_block = local_blocks_by_key.get(key)
        upstream_block = upstream_blocks_by_line.get(upstream_row.get("line", ""))
        if upstream_block is None:
            upstream_block = upstream_blocks_by_key.get(key)
        base = {
            "channel": upstream_row.get("name", ""),
            "tvg_id": upstream_row.get("tvg_id", ""),
            "local_url": local_row.get("url", "") if local_row else "",
            "upstream_url": upstream_row.get("url", ""),
        }

        if local_block is None:
            report_rows.append({**base, "status": "skipped", "reason": "local block not found"})
            continue
        if upstream_block is None:
            report_rows.append({**base, "status": "skipped", "reason": "upstream block not found"})
            continue
        if not upstream_block.url:
            report_rows.append({**base, "status": "skipped", "reason": "upstream URL missing"})
            continue
        if local_block.url == upstream_block.url:
            report_rows.append({**base, "status": "skipped", "reason": "same URL; likely transient failure"})
            continue

        new_lines = replacement_lines(local_block, upstream_block)
        if new_lines == local_block.lines:
            report_rows.append({**base, "status": "skipped", "reason": "replacement produced no change"})
            continue

        replacements.append((local_block, new_lines))
        report_rows.append({**base, "status": "updated", "reason": "copied working upstream URL/options"})

    if replacements:
        replacements.sort(key=lambda item: item[0].start, reverse=True)
        for block, new_lines in replacements:
            local_lines[block.start : block.end] = new_lines
        local_playlist.write_text("\n".join(local_lines) + "\n", encoding="utf-8")

    return report_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-playlist", required=True, type=Path)
    parser.add_argument("--upstream-playlist", required=True, type=Path)
    parser.add_argument("--mine-audit", required=True, type=Path)
    parser.add_argument("--upstream-audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    rows = apply_updates(args.local_playlist, args.upstream_playlist, args.mine_audit, args.upstream_audit)
    updated = [row for row in rows if row.get("status") == "updated"]
    write_report(args.output_dir, rows)

    changed_names = ", ".join(row.get("channel", "") for row in updated)
    append_github_output(
        {
            "changed_count": str(len(updated)),
            "changed_names": changed_names,
        }
    )
    print(f"candidates={len(rows)}")
    print(f"changed_count={len(updated)}")
    if changed_names:
        print(f"changed_names={changed_names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
