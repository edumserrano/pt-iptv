# M3UPT fixed TVI/CNN playlist

Minimal copy of the upstream `LITUATUI/M3UPT` playlist with the broken TVI and CNN Portugal stream URLs corrected.

Raw playlist URL:

```text
https://raw.githubusercontent.com/edumserrano/pt-iptv/main/M3U/M3UPT.m3u
```

Raw EPG URL:

```text
https://raw.githubusercontent.com/edumserrano/pt-iptv/main/EPG/epg-m3upt.xml.xz
```

GitHub Pages short URLs, after enabling Pages with **Source: GitHub Actions** in repository settings:

```text
https://edumserrano.github.io/pt-iptv/p.m3u
https://edumserrano.github.io/pt-iptv/e.xml.xz
https://edumserrano.github.io/pt-iptv/
```

The Pages workflow publishes `p.m3u` and `e.xml.xz` from the current repository contents, so those URLs stay stable while the playlist and EPG behind them are refreshed by normal commits and automation.

Note: GitHub Pages output can be publicly reachable even when repository visibility changes, depending on the repository plan and Pages settings. Treat anything published through the Pages workflow as public.

The TVI/CNN URLs use IOL `wmsAuthSign` tokens, which expire after 1440 minutes. Refresh them before pushing with:

```powershell
.\scripts\Update-IolToken.ps1
```

The `Refresh IOL Tokens` GitHub Actions workflow also runs every 5 hours. If the IOL-token streams are broken and `Update-IolToken.ps1` fixes them, it opens or updates an automated PR and enables squash auto-merge.

## Stream health report

The `Stream Health Check` GitHub Actions workflow can be run manually and also runs every 5 hours. Each run checks this playlist, checks the upstream `LITUATUI/M3UPT` playlist without radio entries, and uploads a `stream-health-report` artifact containing:

- `pt-iptv-stream-health-report.md`
- `upstream-working-local-failing.csv`
- `key-channel-comparison.csv`
- Individual Markdown/CSV audits for this repo and upstream

The key-channel comparison explicitly calls out RTP1, RTP2, SIC, SIC Noticias, CNN Portugal, TVI, and Sport TV 1-5 for this repo, upstream, and the diff section.

If a matching upstream stream is working while this repo's stream is failing, and the upstream URL/options differ, the workflow opens or updates an automated PR and enables squash auto-merge.
