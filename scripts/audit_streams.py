from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"
MEDIA_CONTENT_TYPES = (
    "audio/",
    "video/",
    "application/octet-stream",
    "application/ogg",
    "application/x-ogg",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/mpegurl",
    "binary/octet-stream",
)
HLS_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
)
MEDIA_EXTENSIONS = (
    ".mp3",
    ".aac",
    ".aacp",
    ".m4a",
    ".mp4",
    ".m4s",
    ".ts",
    ".mkv",
    ".webm",
    ".ogg",
    ".oga",
    ".flv",
)


@dataclass
class Entry:
    index: int
    line: int
    name: str
    group: str
    tvg_id: str
    url: str | None
    radio: bool = False
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class FetchResult:
    ok: bool
    status: int | str
    url: str
    content_type: str
    data: bytes
    error: str = ""


def parse_attrs(extinf: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r'([\w-]+)="([^"]*)"', extinf)}


def parse_playlist(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    current: dict | None = None

    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = raw_line.strip()

            if line.startswith("#EXTINF:"):
                if current is not None:
                    entries.append(
                        Entry(
                            index=len(entries) + 1,
                            line=current["line"],
                            name=current["name"],
                            group=current["group"],
                            tvg_id=current["tvg_id"],
                            url=current["url"],
                            radio=current["radio"],
                            headers=current["headers"],
                        )
                    )

                attrs = parse_attrs(line)
                name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
                current = {
                    "line": line_no,
                    "name": name,
                    "group": attrs.get("group-title", ""),
                    "tvg_id": attrs.get("tvg-id", ""),
                    "url": None,
                    "radio": attrs.get("radio", "").lower() == "true",
                    "headers": {},
                }
                continue

            if current is None:
                continue

            if line.startswith("#EXTVLCOPT:"):
                option = line[len("#EXTVLCOPT:") :]
                if "=" in option:
                    key, value = option.split("=", 1)
                    value = value.strip().strip('"')
                    if key == "http-user-agent":
                        current["headers"]["User-Agent"] = value
                    elif key == "http-referrer":
                        current["headers"]["Referer"] = value
                    elif key == "http-origin":
                        current["headers"]["Origin"] = value
                continue

            if line and not line.startswith("#") and current["url"] is None:
                current["url"] = line

    if current is not None:
        entries.append(
            Entry(
                index=len(entries) + 1,
                line=current["line"],
                name=current["name"],
                group=current["group"],
                tvg_id=current["tvg_id"],
                url=current["url"],
                radio=current["radio"],
                headers=current["headers"],
            )
        )

    return entries


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def is_radio_entry(entry: Entry) -> bool:
    group = normalize_label(entry.group)
    return entry.radio or group in {"radio", "radios"}


def decompress_if_needed(data: bytes, content_encoding: str) -> bytes:
    enc = content_encoding.lower()
    if enc == "gzip" or data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if enc == "deflate":
        return zlib.decompress(data)
    return data


def fetch(url: str, headers: dict[str, str], timeout: float, max_bytes: int | None = None, byte_range: str | None = None) -> FetchResult:
    request_headers = {"User-Agent": DEFAULT_UA}
    request_headers.update(headers)
    if byte_range:
        request_headers["Range"] = byte_range

    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as response:
            raw = response.read(max_bytes) if max_bytes else response.read()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if byte_range is None:
                try:
                    raw = decompress_if_needed(raw, response.headers.get("Content-Encoding", ""))
                except Exception:
                    pass
            return FetchResult(True, response.status, response.geturl(), content_type, raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read(512)
        content_type = exc.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        return FetchResult(False, exc.code, url, content_type, raw, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
        reason = getattr(exc, "reason", exc)
        return FetchResult(False, type(exc).__name__, url, "", b"", str(reason))
    except Exception as exc:
        return FetchResult(False, type(exc).__name__, url, "", b"", str(exc))


def decode_text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def non_comment_uris(text: str) -> list[str]:
    uris = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            uris.append(line)
    return uris


def uri_looks_like_playlist(uri: str) -> bool:
    path = urllib.parse.urlsplit(uri).path.lower()
    return path.endswith(".m3u") or path.endswith(".m3u8")


def looks_like_hls(url: str, result: FetchResult) -> bool:
    path = urllib.parse.urlsplit(result.url or url).path.lower()
    if path.endswith(".m3u") or path.endswith(".m3u8"):
        return True
    if result.content_type in HLS_CONTENT_TYPES:
        return True
    return result.data.lstrip().startswith(b"#EXTM3U")


def media_content_type(content_type: str, url: str, data: bytes) -> bool:
    if any(content_type.startswith(prefix) for prefix in MEDIA_CONTENT_TYPES):
        return True
    path = urllib.parse.urlsplit(url).path.lower()
    if path.endswith(MEDIA_EXTENSIONS):
        return True
    if data.startswith(b"\x47") or data.startswith(b"ID3") or data[:4] == b"ftyp":
        return True
    return False


def check_hls(entry: Entry, timeout: float) -> dict[str, str]:
    assert entry.url
    current_url = entry.url
    last_status: int | str = ""

    for depth in range(4):
        playlist_result = fetch(current_url, entry.headers, timeout)
        last_status = playlist_result.status
        if not playlist_result.ok:
            return {
                "verdict": "not_working",
                "reason": "playlist_fetch_failed",
                "http_status": str(playlist_result.status),
                "detail": playlist_result.error,
                "final_url": playlist_result.url,
            }

        text = decode_text(playlist_result.data)
        uris = non_comment_uris(text)
        if not uris:
            return {
                "verdict": "not_working",
                "reason": "hls_no_media_uri",
                "http_status": str(last_status),
                "detail": "playlist has no media or variant URI",
                "final_url": playlist_result.url,
            }

        next_playlist = next((uri for uri in uris if uri_looks_like_playlist(uri)), None)
        first_segment = next((uri for uri in uris if not uri_looks_like_playlist(uri)), None)

        if first_segment and "#EXT-X-STREAM-INF" not in text:
            segment_url = urllib.parse.urljoin(playlist_result.url, first_segment)
            segment_result = fetch(segment_url, entry.headers, timeout, max_bytes=16, byte_range="bytes=0-15")
            if segment_result.ok:
                return {
                    "verdict": "working",
                    "reason": "hls_segment_ok",
                    "http_status": str(segment_result.status),
                    "detail": f"{segment_result.content_type or 'unknown content-type'} segment reachable",
                    "final_url": segment_result.url,
                }
            return {
                "verdict": "not_working",
                "reason": "hls_segment_failed",
                "http_status": str(segment_result.status),
                "detail": segment_result.error,
                "final_url": segment_result.url,
            }

        if next_playlist:
            current_url = urllib.parse.urljoin(playlist_result.url, next_playlist)
            continue

        if first_segment:
            segment_url = urllib.parse.urljoin(playlist_result.url, first_segment)
            segment_result = fetch(segment_url, entry.headers, timeout, max_bytes=16, byte_range="bytes=0-15")
            if segment_result.ok:
                return {
                    "verdict": "working",
                    "reason": "hls_segment_ok",
                    "http_status": str(segment_result.status),
                    "detail": f"{segment_result.content_type or 'unknown content-type'} segment reachable",
                    "final_url": segment_result.url,
                }

    return {
        "verdict": "not_working",
        "reason": "hls_too_many_playlist_hops",
        "http_status": str(last_status),
        "detail": "stopped after four playlist hops",
        "final_url": current_url,
    }


def check_entry(entry: Entry, timeout: float) -> dict[str, str]:
    base = {
        "index": str(entry.index),
        "line": str(entry.line),
        "name": entry.name,
        "group": entry.group,
        "tvg_id": entry.tvg_id,
        "url": entry.url or "",
    }

    if not entry.url:
        return {
            **base,
            "verdict": "missing_url",
            "reason": "missing_url",
            "http_status": "",
            "detail": "no non-comment URL after #EXTINF",
            "final_url": "",
        }

    parsed = urllib.parse.urlsplit(entry.url)
    if parsed.scheme not in {"http", "https"}:
        return {
            **base,
            "verdict": "not_working",
            "reason": "unsupported_scheme",
            "http_status": "",
            "detail": parsed.scheme,
            "final_url": entry.url,
        }

    top = fetch(entry.url, entry.headers, timeout, max_bytes=65536)
    if not top.ok:
        return {
            **base,
            "verdict": "not_working",
            "reason": "top_fetch_failed",
            "http_status": str(top.status),
            "detail": top.error,
            "final_url": top.url,
        }

    if looks_like_hls(entry.url, top):
        hls = check_hls(entry, timeout)
        return {**base, **hls}

    if media_content_type(top.content_type, top.url, top.data[:32]):
        return {
            **base,
            "verdict": "working",
            "reason": "direct_media_ok",
            "http_status": str(top.status),
            "detail": top.content_type or "media-like response",
            "final_url": top.url,
        }

    return {
        **base,
        "verdict": "not_working",
        "reason": "not_media_response",
        "http_status": str(top.status),
        "detail": top.content_type or "unknown content-type",
        "final_url": top.url,
    }


def write_reports(results: list[dict[str, str]], output_dir: Path, elapsed: float) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pt-iptv-channel-audit.csv"
    md_path = output_dir / "pt-iptv-channel-audit.md"

    fields = [
        "index",
        "line",
        "name",
        "group",
        "tvg_id",
        "verdict",
        "reason",
        "http_status",
        "detail",
        "url",
        "final_url",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({field: row.get(field, "") for field in fields})

    verdict_counts = Counter(row["verdict"] for row in results)
    reason_counts = Counter(row["reason"] for row in results)
    not_ok = [row for row in results if row["verdict"] != "working"]
    ok = [row for row in results if row["verdict"] == "working"]

    def table_rows(rows: list[dict[str, str]]) -> list[str]:
        lines = ["| # | Line | Channel | Group | Verdict | Reason | HTTP | Detail |", "|---:|---:|---|---|---|---|---:|---|"]
        for row in rows:
            detail = row.get("detail", "").replace("|", "\\|")[:120]
            channel = row.get("name", "").replace("|", "\\|")
            group = row.get("group", "").replace("|", "\\|")
            lines.append(
                f"| {row['index']} | {row['line']} | {channel} | {group} | {row['verdict']} | {row['reason']} | {row.get('http_status','')} | {detail} |"
            )
        return lines

    with md_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# PT IPTV Channel Audit\n\n")
        handle.write(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")
        handle.write(f"Entries checked: {len(results)}\n\n")
        handle.write(f"Elapsed: {elapsed:.1f} seconds\n\n")
        handle.write("## Verdict Summary\n\n")
        handle.write("| Verdict | Count |\n|---|---:|\n")
        for verdict, count in verdict_counts.most_common():
            handle.write(f"| {verdict} | {count} |\n")
        handle.write("\n## Reason Summary\n\n")
        handle.write("| Reason | Count |\n|---|---:|\n")
        for reason, count in reason_counts.most_common():
            handle.write(f"| {reason} | {count} |\n")
        handle.write("\n## Not Working Or Missing URL\n\n")
        handle.write("\n".join(table_rows(not_ok)))
        handle.write("\n\n## Working\n\n")
        handle.write("\n".join(table_rows(ok)))
        handle.write("\n")

    return csv_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--playlist", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--exclude-radio", action="store_true", help="Skip entries marked as radio stations")
    args = parser.parse_args()

    all_entries = parse_playlist(args.playlist)
    entries = [entry for entry in all_entries if not (args.exclude_radio and is_radio_entry(entry))]
    skipped = len(all_entries) - len(entries)
    if skipped:
        print(f"skipped_radio={skipped}", flush=True)

    start = time.time()
    results: list[dict[str, str]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(check_entry, entry, args.timeout): entry for entry in entries}
        completed = 0
        for future in concurrent.futures.as_completed(future_map):
            completed += 1
            entry = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "index": str(entry.index),
                        "line": str(entry.line),
                        "name": entry.name,
                        "group": entry.group,
                        "tvg_id": entry.tvg_id,
                        "url": entry.url or "",
                        "verdict": "not_working",
                        "reason": "audit_exception",
                        "http_status": "",
                        "detail": str(exc),
                        "final_url": entry.url or "",
                    }
                )
            if completed % 50 == 0 or completed == len(entries):
                print(f"checked {completed}/{len(entries)}", flush=True)

    results.sort(key=lambda row: int(row["index"]))
    elapsed = time.time() - start
    csv_path, md_path = write_reports(results, args.output_dir, elapsed)

    verdict_counts = Counter(row["verdict"] for row in results)
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")
    print("summary=" + ", ".join(f"{key}:{value}" for key, value in verdict_counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
