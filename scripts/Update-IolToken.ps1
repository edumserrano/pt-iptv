$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$userAgent = 'Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0'
$token = (curl.exe -L -s -A $userAgent 'https://services.iol.pt/matrix?userId=').Trim()

if (-not $token -or $token.Length -lt 50) {
    throw 'Failed to fetch a valid IOL token.'
}

$tviUrl = "https://video-auth6.iol.pt/live_tvi/live_tvi/edge_servers/tvi-720p/chunks.m3u8?wmsAuthSign=$token"
$cnnUrl = "https://video-auth7.iol.pt/live_cnn/live_cnn/edge_servers/cnn-720p/chunks.m3u8?wmsAuthSign=$token"

$playlistPath = Join-Path $root 'M3U/M3UPT.m3u'
$playlist = Get-Content -Raw -LiteralPath $playlistPath
$playlist = $playlist -replace 'https://video-auth6\.iol\.pt/live_tvi/live_tvi/edge_servers/tvi-720p/chunks\.m3u8\?wmsAuthSign=[^\r\n]+', $tviUrl
$playlist = $playlist -replace 'https://video-auth7\.iol\.pt/live_cnn/live_cnn/edge_servers/cnn-720p/chunks\.m3u8\?wmsAuthSign=[^\r\n]+', $cnnUrl
Set-Content -LiteralPath $playlistPath -Value $playlist -Encoding utf8NoBOM

$tviSidecar = @(
    '#EXTM3U'
    '#EXT-X-VERSION:3'
    '#EXT-X-STREAM-INF:BANDWIDTH=2480050,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"'
    $tviUrl
    ''
) -join "`n"

$cnnSidecar = @(
    '#EXTM3U'
    '#EXT-X-VERSION:3'
    '#EXT-X-STREAM-INF:BANDWIDTH=2077116,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"'
    $cnnUrl
    ''
) -join "`n"

Set-Content -LiteralPath (Join-Path $root 'M3U/TVI.m3u8') -Value $tviSidecar -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/CNN_Portugal.m3u8') -Value $cnnSidecar -Encoding utf8NoBOM

$decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($token))
Write-Host "Updated IOL token: $decoded"
