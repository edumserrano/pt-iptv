# M3UPT fixed TVI/CNN playlist

Minimal copy of the upstream `LITUATUI/M3UPT` playlist with the broken TVI and CNN Portugal stream URLs corrected.

After pushing this repository to GitHub, use this raw playlist URL:

```text
https://raw.githubusercontent.com/<your-github-user>/<your-repo>/main/M3U/M3UPT.m3u
```

Raw EPG URL:

```text
https://raw.githubusercontent.com/edumserrano/pt-iptv/main/EPG/epg-m3upt.xml.xz
```

The TVI/CNN URLs use IOL `wmsAuthSign` tokens, which expire after 1440 minutes. Refresh them before pushing with:

```powershell
.\scripts\Update-IolToken.ps1
```
