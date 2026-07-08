param(
    [switch]$ShowDecodedToken
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$userAgent = 'Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0'
$tokenResponse = Invoke-WebRequest `
    -Uri 'https://services.iol.pt/matrix?userId=' `
    -Headers @{ 'User-Agent' = $userAgent } `
    -UseBasicParsing
$token = ([string]$tokenResponse.Content).Trim()

if (-not $token -or $token.Length -lt 50) {
    throw 'Failed to fetch a valid IOL token.'
}

$tviUrl = "https://video-auth6.iol.pt/live_tvi/live_tvi/edge_servers/tvi-720p/chunks.m3u8?wmsAuthSign=$token"
$cnnUrl = "https://video-auth7.iol.pt/live_cnn/live_cnn/edge_servers/cnn-720p/chunks.m3u8?wmsAuthSign=$token"
$tviInternacionalUrl = "https://video-auth6.iol.pt/live_tvi_internacional/live_tvi_internacional/playlist.m3u8?wmsAuthSign=$token"
$vmaisUrl = "https://video-auth2.iol.pt/live_vmais/live_vmais/edge_servers/vmais-720p/playlist.m3u8?wmsAuthSign=$token"
$tviFiccaoUrl = "https://video-auth1.iol.pt/live_tvi_ficcao/live_tvi_ficcao/edge_servers/tvificcao-720p/chunks.m3u8?wmsAuthSign=$token"
$tviRealityUrl = "https://video-auth4.iol.pt/live_tvi_reality/live_tvi_reality/edge_servers/tvireality-720_passthrough/chunks.m3u8?wmsAuthSign=$token"

$playlistPath = Join-Path $root 'M3U/M3UPT.m3u'
$playlist = Get-Content -Raw -LiteralPath $playlistPath
$playlist = $playlist -replace 'https://video-auth6\.iol\.pt/live_tvi/live_tvi/edge_servers/tvi-720p/chunks\.m3u8\?wmsAuthSign=[^\r\n]+', $tviUrl
$playlist = $playlist -replace 'https://video-auth7\.iol\.pt/live_cnn/live_cnn/edge_servers/cnn-720p/chunks\.m3u8\?wmsAuthSign=[^\r\n]+', $cnnUrl
$playlist = $playlist -replace 'https://(?:github\.com/LITUATUI/M3UPT/raw/main/M3U/TVI_Internacional\.m3u8|video-auth6\.iol\.pt/live_tvi_internacional/live_tvi_internacional/playlist\.m3u8\?wmsAuthSign=[^\r\n]+)', $tviInternacionalUrl
$playlist = $playlist -replace 'https://(?:github\.com/LITUATUI/M3UPT/raw/main/M3U/Vmais_TVI\.m3u8|video-auth2\.iol\.pt/live_vmais/live_vmais/edge_servers/vmais-720p/playlist\.m3u8\?wmsAuthSign=[^\r\n]+)', $vmaisUrl
$playlist = $playlist -replace 'https://(?:github\.com/LITUATUI/M3UPT/raw/main/M3U/TVI_Ficcao\.m3u8|raw\.githubusercontent\.com/LITUATUI/M3UPT/main/M3U/TVI_Ficcao\.m3u8|video-auth1\.iol\.pt/live_tvi_ficcao/live_tvi_ficcao/edge_servers/tvificcao-720p/chunks\.m3u8\?wmsAuthSign=[^\r\n]+)', $tviFiccaoUrl
$playlist = $playlist -replace 'https://(?:github\.com/LITUATUI/M3UPT/raw/main/M3U/TVI_Reality\.m3u8|raw\.githubusercontent\.com/LITUATUI/M3UPT/main/M3U/TVI_Reality\.m3u8|video-auth4\.iol\.pt/live_tvi_reality/live_tvi_reality/edge_servers/tvireality-720_passthrough/chunks\.m3u8\?wmsAuthSign=[^\r\n]+)', $tviRealityUrl
Set-Content -LiteralPath $playlistPath -Value $playlist -Encoding utf8NoBOM

$tviSidecar = @(
    '#EXTM3U'
    '#EXT-X-VERSION:3'
    '#EXT-X-STREAM-INF:BANDWIDTH=2480050,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"'
    $tviUrl
) -join "`n"

$cnnSidecar = @(
    '#EXTM3U'
    '#EXT-X-VERSION:3'
    '#EXT-X-STREAM-INF:BANDWIDTH=2077116,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"'
    $cnnUrl
) -join "`n"

Set-Content -LiteralPath (Join-Path $root 'M3U/TVI.m3u8') -Value $tviSidecar -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/CNN_Portugal.m3u8') -Value $cnnSidecar -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/TVI_Internacional.m3u8') -Value (($tviSidecar -replace [regex]::Escape($tviUrl), $tviInternacionalUrl) -replace 'BANDWIDTH=2480050,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"', 'BANDWIDTH=1525190,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.4d4029,mp4a.40.2"') -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/Vmais_TVI.m3u8') -Value (($tviSidecar -replace [regex]::Escape($tviUrl), $vmaisUrl) -replace 'BANDWIDTH=2480050', 'BANDWIDTH=1732503') -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/TVI_Ficcao.m3u8') -Value (($tviSidecar -replace [regex]::Escape($tviUrl), $tviFiccaoUrl) -replace 'BANDWIDTH=2480050,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"', 'BANDWIDTH=1609118,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"') -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $root 'M3U/TVI_Reality.m3u8') -Value (($tviSidecar -replace [regex]::Escape($tviUrl), $tviRealityUrl) -replace 'BANDWIDTH=2480050,FRAME-RATE=25,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"', 'BANDWIDTH=1414170,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"') -Encoding utf8NoBOM

$decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($token))
if ($ShowDecodedToken) {
    Write-Host "Updated IOL token: $decoded"
} else {
    Write-Host 'Updated IOL token.'
}
