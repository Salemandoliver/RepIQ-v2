<#
  CallIQ recording uploader (PowerShell) — for Windows machines without Python.
  Watches a folder for new call recordings and uploads each to the CallIQ endpoint.
  Works on Windows PowerShell 5.1 and PowerShell 7+ (uses .NET HttpClient for multipart).

  Files are extensionless WAVs named like  calliq_2026-06-19_09-30-00 . The script detects
  the real format from the file's contents (defaults to WAV), reads the recording time from
  the filename, uploads with the rep's email, then moves the file into  processed\ .

  Example:
    powershell -ExecutionPolicy Bypass -File CallIQUploader.ps1 `
      -ApiKey "SAME_AS_RAILWAY" -RepEmail "rep@oxfordandbucks.com" -WatchDir "C:\CallIQ\recordings"
  Run once and exit (e.g. a scheduled task every few minutes):  add  -Once
#>
param(
  [string]$ApiUrl   = "https://repiq.co.uk/api/recordings/upload",
  [string]$ApiKey   = $env:CALLIQ_API_KEY,
  [string]$RepEmail = $env:CALLIQ_REP_EMAIL,
  [string]$WatchDir = $(if ($env:CALLIQ_WATCH_DIR) { $env:CALLIQ_WATCH_DIR } else { "C:\CallIQ\recordings" }),
  [string]$DefaultExt = "wav",
  [int]   $PollSeconds   = 10,
  [int]   $StableSeconds = 15,
  [switch]$Once
)

$ProcessedDir = "processed"
$CType = @{ wav="audio/wav"; mp3="audio/mpeg"; m4a="audio/mp4"; mp4="video/mp4"; ogg="audio/ogg"; webm="audio/webm" }
Add-Type -AssemblyName System.Net.Http

function Write-Log($msg) { Write-Host ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) }

function Get-AudioExt($file) {
  # detect from magic bytes; fall back to DefaultExt
  try {
    $fs = [System.IO.File]::OpenRead($file.FullName)
    $buf = New-Object byte[] 16
    [void]$fs.Read($buf, 0, 16); $fs.Dispose()
  } catch { return $DefaultExt }
  $ascii = -join ($buf[0..3] | ForEach-Object { [char]$_ })
  $ascii8 = -join ($buf[8..11] | ForEach-Object { [char]$_ })
  if ($ascii -eq "RIFF" -and $ascii8 -eq "WAVE") { return "wav" }
  if (($buf[0] -eq 0x49 -and $buf[1] -eq 0x44 -and $buf[2] -eq 0x33)) { return "mp3" }       # ID3
  if ($buf[0] -eq 0xFF -and ($buf[1] -band 0xE0) -eq 0xE0) { return "mp3" }                   # MPEG sync
  $ftyp = -join ($buf[4..7] | ForEach-Object { [char]$_ })
  if ($ftyp -eq "ftyp") { return "mp4" }
  if ($ascii -eq "OggS") { return "ogg" }
  if ($DefaultExt) { return $DefaultExt }
  return "wav"
}

function Get-RecordedAt($file) {
  if ($file.Name -match "(\d{4}-\d{2}-\d{2})[ _T](\d{2})[-:](\d{2})[-:](\d{2})") {
    try {
      $local = Get-Date -Year $Matches[1].Substring(0,4) -Month $Matches[1].Substring(5,2) -Day $Matches[1].Substring(8,2) `
                        -Hour $Matches[2] -Minute $Matches[3] -Second $Matches[4]
      return $local.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } catch {}
  }
  return $file.CreationTimeUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Get-Rep($file) {
  if ($file.BaseName -match "^([^@\s]+@[^@\s_]+)__") { return $Matches[1].ToLower() }
  $parent = Split-Path $file.DirectoryName -Leaf
  if ($parent -match "^[^@\s]+@[^@\s]+$" -and $file.DirectoryName -ne $WatchDir) { return $parent.ToLower() }
  if ($RepEmail) { return $RepEmail.ToLower() }
  return $null
}

function Move-Into($file, $sub) {
  $destDir = Join-Path $WatchDir $sub
  if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
  $dest = Join-Path $destDir $file.Name
  $i = 1
  while (Test-Path $dest) { $dest = Join-Path $destDir ("{0}_{1}{2}" -f $file.BaseName, $i, $file.Extension); $i++ }
  try { Move-Item -LiteralPath $file.FullName -Destination $dest -Force }
  catch { Write-Log ("  couldn't move {0}: {1}" -f $file.Name, $_.Exception.Message) }
}

function Upload-File($file, $rep) {
  $ext = Get-AudioExt $file
  $sendName = if ($file.Extension.TrimStart('.').ToLower() -eq $ext) { $file.Name } else { "$($file.Name).$ext" }
  $ctype = if ($CType.ContainsKey($ext)) { $CType[$ext] } else { "audio/wav" }
  $client = New-Object System.Net.Http.HttpClient
  $client.Timeout = [TimeSpan]::FromMinutes(10)
  try {
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $stream  = [System.IO.File]::OpenRead($file.FullName)
    $fileContent = New-Object System.Net.Http.StreamContent($stream)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new($ctype)
    $content.Add($fileContent, "file", $sendName)
    $content.Add((New-Object System.Net.Http.StringContent($rep)), "repId")
    $content.Add((New-Object System.Net.Http.StringContent((Get-RecordedAt $file))), "recordedAt")
    $client.DefaultRequestHeaders.Add("X-Api-Key", $ApiKey)
    $resp = $client.PostAsync($ApiUrl, $content).GetAwaiter().GetResult()
    $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $stream.Dispose()
    $code = $resp.StatusCode.value__
    if ($code -eq 202 -or $code -eq 200) { Write-Log ("  uploaded {0} ({1}) -> {2}" -f $file.Name, $ext, $body); return "ok" }
    $permanent = @(400,401,403,404,413,415,422) -contains $code
    Write-Log ("  upload failed {0}: HTTP {1} {2}" -f $file.Name, $code, $body)
    if ($permanent) { return "permanent" } else { return "retry" }
  } catch {
    Write-Log ("  network error on {0}: {1}" -f $file.Name, $_.Exception.Message); return "retry"
  } finally { $client.Dispose() }
}

function Process-Once {
  if (-not (Test-Path $WatchDir)) { Write-Log "watch_dir not found: $WatchDir"; return }
  $files = Get-ChildItem -Path $WatchDir -Recurse -File |
    Where-Object { $_.FullName -notmatch "\\($ProcessedDir|failed|uploaded)\\" -and
                   $_.Name -notmatch "\.(tmp|part|partial|log|ini|txt|json|db)$" -and
                   ($_.Extension -eq "" -or @(".wav",".mp3",".m4a",".mp4",".ogg",".webm") -contains $_.Extension.ToLower()) }
  foreach ($f in $files) {
    if (((Get-Date) - $f.LastWriteTime).TotalSeconds -lt $StableSeconds -or $f.Length -eq 0) { continue }
    $rep = Get-Rep $f
    if (-not $rep) { Write-Log "  no rep email for $($f.Name) — set -RepEmail. Skipping."; Move-Into $f "failed"; continue }
    switch (Upload-File $f $rep) {
      "ok"        { Move-Into $f $ProcessedDir }
      "permanent" { Move-Into $f "failed" }
      "retry"     { }
    }
  }
}

if (-not $ApiKey)   { Write-Log "ERROR: ApiKey not set (-ApiKey or CALLIQ_API_KEY)."; exit 2 }
if (-not $WatchDir) { Write-Log "ERROR: WatchDir not set (-WatchDir or CALLIQ_WATCH_DIR)."; exit 2 }
if (-not (Test-Path $WatchDir)) { New-Item -ItemType Directory -Path $WatchDir -Force | Out-Null }

if ($Once) { Process-Once; Write-Log "Done."; exit 0 }

Write-Log "Watching $WatchDir every ${PollSeconds}s (Ctrl+C to stop)…"
while ($true) { Process-Once; Start-Sleep -Seconds $PollSeconds }
