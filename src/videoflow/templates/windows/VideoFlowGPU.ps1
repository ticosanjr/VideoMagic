param(
    [ValidateSet("Menu", "Install", "Start", "Stop", "Restart", "Status", "Doctor", "Repair", "Logs", "Autostart", "Uninstall", "Supervisor")]
    [string]$Action = "Menu",
    [switch]$Silent
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$BootstrapLog = Join-Path $LogDir "bootstrap.log"
$WorkerLog = Join-Path $LogDir "worker.log"
$WorkerErr = Join-Path $LogDir "worker-error.log"
$EnvFile = Join-Path $Root "worker.env"
$EnvBackup = Join-Path $Root "worker.env.bak"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$WorkerExe = Join-Path $Root ".venv\Scripts\videoflow-gpu-worker.exe"
$ExpectedVersionFile = Join-Path $Root "expected_version.txt"
$ExpectedVersion = "__VERSION__"
$script:EnvMap = @{}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $safe = $Message -replace "(VF_GPU_TOKEN=)\S+", '$1***'
    $line = "$stamp [$Level] $safe"
    Add-Content -Path $BootstrapLog -Value $line -Encoding UTF8
    if (-not $Silent) { Write-Host $line }
}

function Fail {
    param([string]$Message)
    Write-Log $Message "ERROR"
    throw $Message
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-Token {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Write-EnvFile {
    param([string]$Token, [string]$WorkerId)
    $lines = @(
        "# VideoFlow Windows GPU worker. Keep this file private.",
        "VF_GPU_TOKEN=$Token",
        "VF_GPU_HOST=0.0.0.0",
        "VF_GPU_PORT=8766",
        "VF_GPU_WORKER_ID=$WorkerId",
        "VF_GPU_MAX_VRAM_MB=10240",
        "VF_GPU_MODEL_TTL_SEC=300",
        "VF_GPU_BUILTIN_HANDLERS=1",
        "VF_GPU_DISCOVERY=1",
        "VF_GPU_ADVERTISE_PORT=8767"
    )
    Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
    Copy-Item -Path $EnvFile -Destination $EnvBackup -Force
    try {
        & icacls.exe $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    } catch {
        Write-Log "Could not restrict worker.env permissions." "WARN"
    }
}

function Ensure-EnvFile {
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path $EnvBackup) {
            Copy-Item -Path $EnvBackup -Destination $EnvFile -Force
            Write-Log "Restored worker.env from backup."
        } else {
            $workerId = "vf-gpu-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
            Write-EnvFile -Token (New-Token) -WorkerId $workerId
            Write-Log "Generated a new worker.env and pairing token."
        }
    }
    $rawEnv = Get-Content -Path $EnvFile -Raw
    if ($rawEnv -notmatch "VF_GPU_TOKEN=\S+") {
        if (Test-Path $EnvBackup) {
            Copy-Item -Path $EnvBackup -Destination $EnvFile -Force
            Write-Log "worker.env had no token; restored the backup."
        } else {
            $workerId = "vf-gpu-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
            Write-EnvFile -Token (New-Token) -WorkerId $workerId
            Write-Log "worker.env had no token; generated a new pairing token."
        }
    }
    $map = @{}
    foreach ($line in Get-Content -Path $EnvFile) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith("#") -or -not $text.Contains("=")) { continue }
        $index = $text.IndexOf("=")
        $key = $text.Substring(0, $index).Trim()
        $value = $text.Substring($index + 1).Trim()
        if ($key) { $map[$key] = $value }
    }
    if (-not $map.ContainsKey("VF_GPU_PORT")) { $map["VF_GPU_PORT"] = "8766" }
    if (-not $map.ContainsKey("VF_GPU_HOST")) { $map["VF_GPU_HOST"] = "0.0.0.0" }
    if (-not $map.ContainsKey("VF_GPU_TOKEN")) { Fail "worker.env has no VF_GPU_TOKEN." }
    $script:EnvMap = $map
    foreach ($key in $map.Keys) {
        [Environment]::SetEnvironmentVariable($key, [string]$map[$key], "Process")
    }
}

function Ensure-Uv {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Log "Installing uv..."
        try {
            Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" | Invoke-Expression
        } catch {
            Fail "Could not install uv. Install it from https://astral.sh/uv and rerun."
        }
        $env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail "uv is still unavailable after installation."
    }
}

function Ensure-Python {
    $ok = $false
    if (Test-Path $VenvPython) {
        try {
            $version = & $VenvPython -c "import sys; print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))" 2>$null
            if ($version.Trim() -eq "3.11") { $ok = $true }
        } catch {
            $ok = $false
        }
    }
    if (-not $ok) {
        Write-Log "Creating a clean Python 3.11 virtual environment."
        if (Test-Path (Join-Path $Root ".venv")) {
            Remove-Item -Recurse -Force (Join-Path $Root ".venv")
        }
        & uv venv (Join-Path $Root ".venv") --python 3.11
        if ($LASTEXITCODE -ne 0) { Fail "uv venv failed." }
    }
    if (-not (Test-Path $VenvPython)) { Fail "The virtual environment has no python.exe." }
}

function Invoke-UvPip {
    param([string[]]$Packages)
    & uv pip install --python $VenvPython @Packages
    if ($LASTEXITCODE -ne 0) {
        Fail ("uv pip install failed: " + ($Packages -join " "))
    }
}

function Test-PythonImport {
    param([string]$Module)
    & $VenvPython -c "import $Module" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Worker {
    param([switch]$Force)
    $installed = ""
    try {
        $installed = (& $VenvPython -c "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))" 2>$null).Trim()
    } catch {
        $installed = ""
    }
    if ($Force -or $installed -ne $ExpectedVersion) {
        $wheel = Get-ChildItem (Join-Path $Root "wheels\videoflow_gpu_worker-*.whl") -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($wheel) {
            Write-Log "Installing worker from $($wheel.Name)."
            Invoke-UvPip @("--reinstall", $wheel.FullName)
        } else {
            Write-Log "Installing worker from the local worker\ directory."
            Invoke-UvPip @("--reinstall", (Join-Path $Root "worker"))
        }
    }
    if (-not (Test-PythonImport "gpu_worker")) {
        Fail "videoflow-gpu-worker is installed but gpu_worker cannot be imported."
    }
}

function Ensure-Dependencies {
    param([switch]$Force)
    $missing = $false
    foreach ($module in @("faster_whisper", "rembg", "cv2", "onnxruntime", "torch")) {
        if (-not (Test-PythonImport $module)) { $missing = $true }
    }
    $cuda = "0"
    try {
        $cuda = (& $VenvPython -c "import torch; print(1 if torch.cuda.is_available() else 0)" 2>$null).Trim()
    } catch {
        $cuda = "0"
    }
    if ($Force -or $missing -or $cuda -ne "1") {
        Write-Log "Installing CUDA PyTorch and the worker dependencies."
        Invoke-UvPip @("--upgrade", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121")
        Invoke-UvPip @("--upgrade", "faster-whisper", "rembg[gpu]", "onnxruntime-gpu", "opencv-python-headless")
    }
}

function Install-Ffmpeg {
    Write-Log "Downloading an FFmpeg build with NVENC."
    $zip = Join-Path $env:TEMP "videoflow-ffmpeg.zip"
    $tmp = Join-Path $env:TEMP "videoflow-ffmpeg"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    try {
        Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
    } catch {
        Fail "Could not download FFmpeg. Copy an NVENC build to bin\ffmpeg.exe."
    }
    $bin = Join-Path $Root "bin"
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    $ffmpeg = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    $ffprobe = Get-ChildItem -Path $tmp -Recurse -Filter ffprobe.exe | Select-Object -First 1
    if (-not $ffmpeg) { Fail "The downloaded FFmpeg archive has no ffmpeg.exe." }
    Copy-Item -Path $ffmpeg.FullName -Destination (Join-Path $bin "ffmpeg.exe") -Force
    if ($ffprobe) {
        Copy-Item -Path $ffprobe.FullName -Destination (Join-Path $bin "ffprobe.exe") -Force
    }
}

function Ensure-Ffmpeg {
    $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    if (-not (Test-Path $ffmpeg)) {
        $system = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if ($system) {
            $ffmpeg = $system.Source
        } else {
            Install-Ffmpeg
            $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
        }
    }
    if (-not (Test-Path $ffmpeg)) { Fail "ffmpeg.exe was not found." }
    $encoders = (& $ffmpeg -hide_banner -encoders 2>&1 | Out-String)
    if ($encoders -notmatch "h264_nvenc") {
        Fail "FFmpeg has no h264_nvenc. Install a build with NVENC in bin\ffmpeg.exe."
    }
    $env:VF_GPU_FFMPEG = $ffmpeg
    $ffprobe = Join-Path $Root "bin\ffprobe.exe"
    if (Test-Path $ffprobe) { $env:VF_GPU_FFPROBE = $ffprobe }
}

function Ensure-Nvidia {
    if (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
        Fail "NVIDIA driver/nvidia-smi not found. Install the NVIDIA driver and reboot."
    }
    $gpu = (& nvidia-smi.exe --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null | Select-Object -First 1)
    if (-not $gpu) { Fail "nvidia-smi returned no GPU information." }
    Write-Log "GPU: $gpu"
}

function Ensure-SharedMount {
    $shared = [Environment]::GetEnvironmentVariable("VF_GPU_SHARED_ROOT", "Process")
    if (-not $shared) { return }
    try {
        if (-not (Test-Path $shared)) { throw "path does not exist" }
        $probe = Join-Path $shared ".videoflow-probe"
        Set-Content -Path $probe -Value "ok" -Encoding ASCII
        Remove-Item -Path $probe -Force
        Write-Log "Shared mount is writable: $shared"
    } catch {
        Write-Log "Shared mount is unavailable; continuing with HTTP transport." "WARN"
        [Environment]::SetEnvironmentVariable("VF_GPU_SHARED_ROOT", $null, "Process")
    }
}

function Ensure-Firewall {
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    if (-not (Test-Admin)) {
        Write-Log "Firewall rule needs Administrator; Windows may prompt on first LAN connection." "WARN"
        return
    }
    $existing = Get-NetFirewallRule -DisplayName "VideoFlow GPU Worker" -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName "VideoFlow GPU Worker" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Private | Out-Null
        Write-Log "Added private firewall rule for TCP $port."
    }
}

function Install-Worker {
    param([switch]$Force)
    Ensure-EnvFile
    Ensure-Uv
    Ensure-Python
    Ensure-Worker -Force:$Force
    Ensure-Dependencies -Force:$Force
    Ensure-Ffmpeg
    Ensure-SharedMount
    Ensure-Firewall
    Write-Log "Installation/repair complete. Expected worker version: $ExpectedVersion"
}

function Wait-Health {
    param([int]$TimeoutSec = 45)
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
            if ($health.available) { return $health }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    $tail = ""
    if (Test-Path $WorkerErr) { $tail = (Get-Content $WorkerErr -Tail 20 | Out-String) }
    Fail "Worker did not become healthy. $tail"
}

function Start-Worker {
    Ensure-EnvFile
    Ensure-Nvidia
    if (-not (Test-Path $WorkerExe)) {
        Install-Worker
    } else {
        Ensure-Worker
        Ensure-Dependencies
    }
    Ensure-Ffmpeg
    Ensure-SharedMount
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -like "videoflow-gpu-worker*") {
            Stop-Process -Id $process.Id -Force
        } else {
            Fail "Port $port is already used by $($process.ProcessName)."
        }
    }
    $pidFile = Join-Path $LogDir "supervisor.pid"
    if (Test-Path $pidFile) {
        $existing = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Log "Supervisor is already running (PID $($existing.Id))."
            Wait-Health
            return
        }
    }
    Write-Log "Starting supervisor..."
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Action", "Supervisor", "-Silent")
    $supervisor = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
    Set-Content -Path $pidFile -Value $supervisor.Id -Encoding ASCII
    $health = Wait-Health
    Write-Log "Worker healthy: $($health.gpu_name) on port $port."
}

function Stop-Worker {
    $stopFile = Join-Path $LogDir "stop.flag"
    Set-Content -Path $stopFile -Value "stop" -Encoding ASCII
    foreach ($name in @("supervisor.pid", "worker.pid")) {
        $path = Join-Path $LogDir $name
        if (Test-Path $path) {
            $processId = [int](Get-Content $path)
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }
    Get-Process -Name "videoflow-gpu-worker" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Remove-Item -Path $stopFile -Force -ErrorAction SilentlyContinue
    Write-Log "Worker stopped."
}

function Show-Status {
    Ensure-EnvFile
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $pidFile = Join-Path $LogDir "supervisor.pid"
    $running = $false
    if (Test-Path $pidFile) {
        $running = $null -ne (Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue)
    }
    Write-Host "Supervisor: $running"
    Write-Host "Port: $port"
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
        Write-Host "Health: $($health.status)"
        Write-Host "GPU: $($health.gpu_name)"
        Write-Host "VRAM: $($health.vram_used_mb)/$($health.vram_total_mb) MB"
        Write-Host "Capabilities: $($health.capabilities -join ', ')"
        Write-Host "Models: $($health.models -join ', ')"
    } catch {
        Write-Host "Health: offline"
    }
    if (Test-Path $WorkerErr) {
        Write-Host "Last error log: $WorkerErr"
    }
}

function Show-Doctor {
    Ensure-EnvFile
    Write-Host "uv: $(if (Get-Command uv -ErrorAction SilentlyContinue) { 'ok' } else { 'missing' })"
    Write-Host "venv python: $(if (Test-Path $VenvPython) { 'ok' } else { 'missing' })"
    Write-Host "worker exe: $(if (Test-Path $WorkerExe) { 'ok' } else { 'missing' })"
    $workerVersion = "missing"
    if (Test-Path $VenvPython) {
        try {
            $workerVersion = (& $VenvPython -c "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))" 2>$null).Trim()
        } catch {
            $workerVersion = "unknown"
        }
    }
    Write-Host "worker version: $workerVersion"
    Write-Host "nvidia-smi: $(if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) { 'ok' } else { 'missing' })"
    Write-Host "ffmpeg: $(if (Test-Path (Join-Path $Root 'bin\ffmpeg.exe')) { 'bundled' } elseif (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) { 'system' } else { 'missing' })"
    Show-Status
}

function Install-Autostart {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action Start -Silent"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "VideoFlow GPU Worker" -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
    Write-Log "Autostart registered."
}

function Remove-Autostart {
    Unregister-ScheduledTask -TaskName "VideoFlow GPU Worker" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log "Autostart removed."
}

function Supervisor {
    $mutex = New-Object Threading.Mutex($false, "Local\VideoFlowGpuWorkerSupervisor")
    if (-not $mutex.WaitOne(0)) { return }
    try {
        Ensure-EnvFile
        $stopFile = Join-Path $LogDir "stop.flag"
        Remove-Item -Path $stopFile -Force -ErrorAction SilentlyContinue
        $backoff = @(2, 5, 15, 30, 60)
        $attempt = 0
        while (-not (Test-Path $stopFile)) {
            if (-not (Test-Path $WorkerExe)) {
                Write-Log "Worker executable is missing; supervisor stopping." "ERROR"
                break
            }
            $worker = Start-Process -FilePath $WorkerExe -WorkingDirectory $Root -RedirectStandardOutput $WorkerLog -RedirectStandardError $WorkerErr -PassThru -NoNewWindow
            Set-Content -Path (Join-Path $LogDir "worker.pid") -Value $worker.Id -Encoding ASCII
            Wait-Process -Id $worker.Id
            if (Test-Path $stopFile) { break }
            $attempt++
            if ($attempt -gt 20) {
                Write-Log "Too many worker restarts; giving up." "ERROR"
                break
            }
            $delay = $backoff[[Math]::Min($attempt - 1, $backoff.Length - 1)]
            Write-Log "Worker exited; restarting in $delay seconds."
            Start-Sleep -Seconds $delay
        }
    } finally {
        Remove-Item -Path (Join-Path $LogDir "worker.pid") -Force -ErrorAction SilentlyContinue
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "VideoFlow Windows GPU Worker"
        Write-Host "1) Install / update / repair"
        Write-Host "2) Start worker"
        Write-Host "3) Stop worker"
        Write-Host "4) Status"
        Write-Host "5) Doctor"
        Write-Host "6) Install autostart"
        Write-Host "7) Remove autostart"
        Write-Host "8) Show logs"
        Write-Host "9) Uninstall virtual environment"
        Write-Host "0) Exit"
        $choice = Read-Host "Choose"
        switch ($choice) {
            "1" { Install-Worker }
            "2" { Start-Worker }
            "3" { Stop-Worker }
            "4" { Show-Status }
            "5" { Show-Doctor }
            "6" { Install-Autostart }
            "7" { Remove-Autostart }
            "8" {
                if (Test-Path $BootstrapLog) { Get-Content $BootstrapLog -Tail 80 }
                if (Test-Path $WorkerErr) { Write-Host "--- worker error ---"; Get-Content $WorkerErr -Tail 40 }
            }
            "9" {
                Stop-Worker
                if (Test-Path (Join-Path $Root ".venv")) { Remove-Item -Recurse -Force (Join-Path $Root ".venv") }
                Write-Log "Virtual environment removed."
            }
            "0" { return }
            default { Write-Host "Unknown option." }
        }
    }
}

try {
    switch ($Action) {
        "Menu" { Show-Menu }
        "Install" { Install-Worker }
        "Start" { Start-Worker }
        "Stop" { Stop-Worker }
        "Restart" { Stop-Worker; Start-Worker }
        "Status" { Show-Status }
        "Doctor" { Show-Doctor }
        "Repair" { Install-Worker -Force; Write-Log "Repair complete." }
        "Logs" {
            if (Test-Path $BootstrapLog) { Get-Content $BootstrapLog -Tail 120 }
            if (Test-Path $WorkerErr) { Write-Host "--- worker error ---"; Get-Content $WorkerErr -Tail 60 }
        }
        "Autostart" { Install-Autostart }
        "Uninstall" { Remove-Autostart; Stop-Worker }
        "Supervisor" { Supervisor }
    }
} catch {
    Write-Log $_.Exception.Message "ERROR"
    if (-not $Silent) {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Log: $BootstrapLog"
        Read-Host "Press Enter to close"
    }
    exit 1
}
