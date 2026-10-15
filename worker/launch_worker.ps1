$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workerScript = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "worker.py"))
$batchScript = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "run_worker.bat"))
$launcherScript = [System.IO.Path]::GetFullPath($MyInvocation.MyCommand.Path)
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir ".."))

$env:API_BASE_URL = "https://focused-ambition-production-66f5.up.railway.app"
$env:WORKER_CODE = "worker-cn-001"
$env:WORKER_DISPLAY_NAME = "worker-cn-001"
$env:WORKER_MACHINE_INFO = "Windows 11 / RTX 4060 / Clash"
$env:WORKER_CAPABILITIES = "yt-dlp,ffmpeg,ffprobe,upload-r2"
$env:WORKER_IDLE_STATUS = "idle"
$env:WORKER_POLL_INTERVAL_SECONDS = "10"
$env:WORKER_HEARTBEAT_INTERVAL_SECONDS = "5"
$env:WORKER_ROOT_DIR = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "runtime"))
$env:WORKER_SOURCE_TYPE_DEFAULT = "youtube"
$env:YTDLP_BIN = "C:\Program Files\Python314\Scripts\yt-dlp.exe"
$env:FFMPEG_BIN = [System.IO.Path]::Combine($projectRoot, "ffmpeg.exe")
$env:FFPROBE_BIN = [System.IO.Path]::Combine($projectRoot, "ffprobe.exe")
$env:S3_BUCKET = "creator-cockpit"
$env:S3_REGION = "auto"
$env:S3_ENDPOINT = "https://add8c6a31d7f4609f15311cd42b9631b.r2.cloudflarestorage.com"
$env:S3_ACCESS_KEY = "29e26be2d825afabaf668d16d40cab41"
$env:S3_SECRET_KEY = "e73958808d187a80f90776364c454b1ec4604f23110bbeddd08b2d99f50baf27"

$currentPowerShell = Get-CimInstance Win32_Process -Filter "ProcessId = $PID"
$currentCmdPid = $currentPowerShell.ParentProcessId

$workerPattern = [Regex]::Escape($workerScript)
$batchPattern = [Regex]::Escape($batchScript)
$launcherPattern = [Regex]::Escape($launcherScript)

$oldWorkerHosts = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    (
        ($_.Name -in @("powershell.exe", "pwsh.exe") -and $_.CommandLine -match $launcherPattern) -or
        ($_.Name -eq "cmd.exe" -and $_.ProcessId -ne $currentCmdPid -and $_.CommandLine -match $batchPattern) -or
        ($_.Name -eq "python.exe" -and $_.CommandLine -match $workerPattern)
    )
}

$oldWorkerIds = @(
    $oldWorkerHosts |
        Select-Object -ExpandProperty ProcessId -Unique
)

foreach ($processId in $oldWorkerIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Write-Host ("Stopped previous worker processes: {0}" -f $oldWorkerIds.Count)
Write-Host ("Starting worker: {0}" -f $workerScript)

& py -3 $workerScript
exit $LASTEXITCODE
