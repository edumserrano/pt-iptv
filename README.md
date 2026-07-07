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

The TVI/CNN URLs use IOL `wmsAuthSign` tokens, which expire after 1440 minutes. Refresh them before pushing with:

```powershell
.\scripts\Update-IolToken.ps1
```

## Stream health report

The `Stream Health Check` GitHub Actions workflow can be run manually and also runs every 5 hours. Each run checks this playlist, checks the upstream `LITUATUI/M3UPT` playlist without radio entries, and uploads a `stream-health-report` artifact containing:

- `pt-iptv-stream-health-report.md`
- `upstream-working-local-failing.csv`
- Individual Markdown/CSV audits for this repo and upstream
