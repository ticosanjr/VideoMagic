param(
    [ValidateSet("Menu", "Install", "Repair", "Start", "Stop", "Restart", "Status", "Doctor", "Diagnose", "Logs", "Autostart", "Uninstall", "Benchmark", "Supervisor", "SelfTest")]
    [string]$Action = "Menu",
    [switch]$Silent,
    [switch]$Json,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
} catch {
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$BootstrapLog = Join-Path $LogDir "bootstrap.log"
$InstallLog = Join-Path $LogDir ("install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$WorkerLog = Join-Path $LogDir "worker.log"
$WorkerErr = Join-Path $LogDir "worker-error.log"
$EnvFile = Join-Path $Root "worker.env"
$EnvBackup = Join-Path $Root "worker.env.bak"
$StateFile = Join-Path $Root "install-state.json"
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$WorkerExe = Join-Path $VenvDir "Scripts\videoflow-gpu-worker.exe"
$WheelsDir = Join-Path $Root "wheels"
$RequirementsFile = Join-Path $Root "requirements-windows.txt"
$ExpectedVersionFile = Join-Path $Root "expected_version.txt"
$ExpectedVersion = "__VERSION__"
$RuntimeRev = "__VERSION__"
if (Test-Path $ExpectedVersionFile) {
    $fromFile = ([string](Get-Content -Path $ExpectedVersionFile -Raw)).Trim()
    if ($fromFile) {
        $ExpectedVersion = $fromFile
        $RuntimeRev = $fromFile
    }
}
$script:EnvMap = @{}
$script:Uv = ""
$script:LastError = $null
$script:CurrentStep = ""
$script:JobAvailable = $false
$script:TranscriptStarted = $false

function Initialize-Logs {
    try {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    } catch {
        $script:LogDir = Join-Path $env:TEMP "VideoFlowGPU-logs"
        New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
        $script:BootstrapLog = Join-Path $script:LogDir "bootstrap.log"
        $script:InstallLog = Join-Path $script:LogDir ("install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
        $script:WorkerLog = Join-Path $script:LogDir "worker.log"
        $script:WorkerErr = Join-Path $script:LogDir "worker-error.log"
    }
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $safe = $Message -replace "(VF_GPU_TOKEN=)\S+", '$1***'
    $line = "$stamp [$Level] $safe"
    try { Add-Content -Path $BootstrapLog -Value $line -Encoding UTF8 } catch { }
    try { Add-Content -Path $InstallLog -Value $line -Encoding UTF8 } catch { }
    if (-not $Silent) {
        switch ($Level) {
            "ERROR" { Write-Host $line -ForegroundColor Red }
            "WARN" { Write-Host $line -ForegroundColor Yellow }
            "OK" { Write-Host $line -ForegroundColor Green }
            default { Write-Host $line }
        }
    }
}

function Write-Step {
    param([string]$Message)
    Write-Log ("==> {0}" -f $Message) "INFO"
}

function Write-Ok {
    param([string]$Message)
    Write-Log $Message "OK"
}

function Write-Warn {
    param([string]$Message)
    Write-Log $Message "WARN"
}

function Fail {
    param(
        [string]$Code,
        [string]$Message,
        [string]$FixHint = "",
        [string]$Command = "",
        [string]$Output = ""
    )
    $script:LastError = [pscustomobject]@{
        code = $Code
        message = $Message
        fix_hint = $FixHint
        command = $Command
        output = $Output
        step = $script:CurrentStep
        at = (Get-Date).ToString("o")
    }
    Write-Log ("[{0}] {1}" -f $Code, $Message) "ERROR"
    if ($Command) { Write-Log ("Command: {0}" -f $Command) "ERROR" }
    if ($Output) { Write-Log $Output "ERROR" }
    throw $Message
}

function Show-ErrorPanel {
    $err = $script:LastError
    if ($null -eq $err) {
        $err = [pscustomobject]@{
            code = "E_UNKNOWN"
            message = "Erro desconhecido"
            fix_hint = ""
            command = ""
            output = ""
            step = $script:CurrentStep
            at = ""
        }
    }
    Write-Host ""
    Write-Host ("=== ERRO [{0}] ===" -f $err.code) -ForegroundColor Red
    Write-Host ("Etapa: {0}" -f $err.step)
    Write-Host ("Mensagem: {0}" -f $err.message)
    if ($err.command) { Write-Host ("Comando: {0}" -f $err.command) }
    if ($err.output) {
        Write-Host "--- saida (ultimas linhas) ---"
        $lines = ($err.output -split "`n")
        $lines | Select-Object -Last 30 | ForEach-Object { Write-Host $_ }
    }
    Write-Host ("Log: {0}" -f $BootstrapLog)
    if ($err.fix_hint) { Write-Host ("Correcao: {0}" -f $err.fix_hint) -ForegroundColor Yellow }
    try {
        $err | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $LogDir "last-error.json") -Encoding UTF8
    } catch { }
    if (-not $Silent) {
        Read-Host "Pressione Enter para voltar ao menu" | Out-Null
    }
}

function Invoke-Native {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [switch]$AllowFailure
    )
    $display = "$Exe $($Arguments -join ' ')"
    Write-Log ("> {0}" -f $display) "INFO"
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        try {
            $raw = & $Exe @Arguments 2>&1
            $code = $LASTEXITCODE
        } catch {
            $raw = @($_.Exception.Message)
            $code = 127
        }
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    $lines = @()
    foreach ($item in @($raw)) {
        if ($null -ne $item) { $lines += $item.ToString() }
    }
    $text = ($lines -join "`n")
    if ($text) {
        try { Add-Content -Path $InstallLog -Value $text -Encoding UTF8 } catch { }
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        Fail "E_COMMAND_FAILED" ("Comando falhou com exit code {0}." -f $code) ("Veja {0}" -f $InstallLog) $display $text
    }
    return [pscustomobject]@{ ExitCode = $code; Output = $text }
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    $script:CurrentStep = $Name
    $script:LastError = $null
    Write-Step $Name
    $started = Get-Date
    & $Body
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    Write-Ok ("{0} concluido em {1}s" -f $Name, $seconds)
}

function Set-UnexpectedError {
    param([object]$ErrorRecord)
    $message = "Erro inesperado"
    $output = ""
    if ($null -ne $ErrorRecord) {
        $message = [string]$ErrorRecord.Exception.Message
        $output = [string]$ErrorRecord.ScriptStackTrace
    }
    $script:LastError = [pscustomobject]@{
        code = "E_UNEXPECTED"
        message = $message
        fix_hint = "Veja o log e o diagnostico completo."
        command = ""
        output = $output
        step = $script:CurrentStep
        at = (Get-Date).ToString("o")
    }
}

function Invoke-MenuAction {
    param([string]$Name, [scriptblock]$Body)
    try {
        Invoke-Step $Name $Body
    } catch {
        if ($null -eq $script:LastError) { Set-UnexpectedError $_ }
        Show-ErrorPanel
    }
}

function Test-Admin {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function New-Token {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Read-EnvMap {
    $map = @{}
    if (-not (Test-Path $EnvFile)) { return $map }
    foreach ($line in Get-Content -Path $EnvFile) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith("#") -or -not $text.Contains("=")) { continue }
        $index = $text.IndexOf("=")
        $key = $text.Substring(0, $index).Trim()
        $value = $text.Substring($index + 1).Trim()
        if ($key) { $map[$key] = $value }
    }
    return $map
}

function Write-EnvMap {
    param([hashtable]$Map)
    $order = @(
        "VF_GPU_TOKEN", "VF_GPU_HOST", "VF_GPU_PORT", "VF_GPU_WORKER_ID",
        "VF_GPU_MAX_VRAM_MB", "VF_GPU_MODEL_TTL_SEC", "VF_GPU_BUILTIN_HANDLERS",
        "VF_GPU_DISCOVERY", "VF_GPU_ADVERTISE_PORT", "VF_GPU_MAX_UPLOAD_MB",
        "VF_GPU_ASR_MODEL", "VF_GPU_ASR_DEVICE", "VF_GPU_ASR_COMPUTE_TYPE",
        "VF_GPU_SHARED_ROOT"
    )
    $lines = @("# VideoFlow Windows GPU worker. Keep this file private.")
    foreach ($key in $order) {
        if ($Map.ContainsKey($key) -and $Map[$key]) {
            $lines += ("{0}={1}" -f $key, $Map[$key])
        }
    }
    foreach ($key in $Map.Keys) {
        if (($order -notcontains $key) -and $Map[$key]) {
            $lines += ("{0}={1}" -f $key, $Map[$key])
        }
    }
    $temporary = "$EnvFile.tmp"
    Set-Content -Path $temporary -Value $lines -Encoding UTF8
    Move-Item -Path $temporary -Destination $EnvFile -Force
    Copy-Item -Path $EnvFile -Destination $EnvBackup -Force
    try {
        & icacls.exe $EnvFile /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(R,W)" | Out-Null
    } catch {
        Write-Warn "Nao foi possivel restringir as permissoes de worker.env."
    }
}

function Ensure-EnvFile {
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path $EnvBackup) {
            Copy-Item -Path $EnvBackup -Destination $EnvFile -Force
            Write-Log "worker.env restaurado do backup."
        } else {
            $map = @{}
            $map["VF_GPU_TOKEN"] = New-Token
            $map["VF_GPU_WORKER_ID"] = "vf-gpu-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
            Write-EnvMap $map
            Write-Warn "worker.env criado com um novo token. Repareie na UI do VideoFlow."
        }
    }
    $map = Read-EnvMap
    if (-not $map.ContainsKey("VF_GPU_TOKEN") -or -not $map["VF_GPU_TOKEN"]) {
        if (Test-Path $EnvBackup) {
            Copy-Item -Path $EnvBackup -Destination $EnvFile -Force
            $map = Read-EnvMap
            Write-Log "Token restaurado do backup."
        } else {
            $map["VF_GPU_TOKEN"] = New-Token
            Write-Warn "Token ausente; novo token gerado. Repareie na UI."
        }
    }
    if (-not $map.ContainsKey("VF_GPU_HOST") -or -not $map["VF_GPU_HOST"]) { $map["VF_GPU_HOST"] = "0.0.0.0" }
    if (-not $map.ContainsKey("VF_GPU_PORT") -or -not $map["VF_GPU_PORT"]) { $map["VF_GPU_PORT"] = "8766" }
    if (-not $map.ContainsKey("VF_GPU_WORKER_ID") -or -not $map["VF_GPU_WORKER_ID"]) {
        $map["VF_GPU_WORKER_ID"] = "vf-gpu-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
    }
    if (-not $map.ContainsKey("VF_GPU_MAX_VRAM_MB") -or -not $map["VF_GPU_MAX_VRAM_MB"]) { $map["VF_GPU_MAX_VRAM_MB"] = "10240" }
    if (-not $map.ContainsKey("VF_GPU_MODEL_TTL_SEC") -or -not $map["VF_GPU_MODEL_TTL_SEC"]) { $map["VF_GPU_MODEL_TTL_SEC"] = "300" }
    if (-not $map.ContainsKey("VF_GPU_BUILTIN_HANDLERS") -or -not $map["VF_GPU_BUILTIN_HANDLERS"]) { $map["VF_GPU_BUILTIN_HANDLERS"] = "1" }
    if (-not $map.ContainsKey("VF_GPU_DISCOVERY") -or -not $map["VF_GPU_DISCOVERY"]) { $map["VF_GPU_DISCOVERY"] = "1" }
    if (-not $map.ContainsKey("VF_GPU_ALLOW_LAN_OPEN") -or -not $map["VF_GPU_ALLOW_LAN_OPEN"]) { $map["VF_GPU_ALLOW_LAN_OPEN"] = "1" }
    if (-not $map.ContainsKey("VF_GPU_ADVERTISE_PORT") -or -not $map["VF_GPU_ADVERTISE_PORT"]) { $map["VF_GPU_ADVERTISE_PORT"] = "8767" }
    if (-not $map.ContainsKey("VF_GPU_LOG_FILE") -or -not $map["VF_GPU_LOG_FILE"]) { $map["VF_GPU_LOG_FILE"] = $WorkerLog }
    if (-not $map.ContainsKey("VF_GPU_MAX_UPLOAD_MB") -or -not $map["VF_GPU_MAX_UPLOAD_MB"]) { $map["VF_GPU_MAX_UPLOAD_MB"] = "8192" }
    if (-not $map.ContainsKey("VF_GPU_ASR_MODEL") -or -not $map["VF_GPU_ASR_MODEL"]) { $map["VF_GPU_ASR_MODEL"] = "large-v3-turbo" }
    if (-not $map.ContainsKey("VF_GPU_ASR_DEVICE") -or -not $map["VF_GPU_ASR_DEVICE"]) { $map["VF_GPU_ASR_DEVICE"] = "cuda" }
    if (-not $map.ContainsKey("VF_GPU_ASR_COMPUTE_TYPE") -or -not $map["VF_GPU_ASR_COMPUTE_TYPE"]) { $map["VF_GPU_ASR_COMPUTE_TYPE"] = "float16" }
    Write-EnvMap $map
    $script:EnvMap = $map
    foreach ($key in $map.Keys) {
        [Environment]::SetEnvironmentVariable($key, [string]$map[$key], "Process")
    }
    $localFfmpeg = Join-Path $Root "bin\ffmpeg.exe"
    if (Test-Path $localFfmpeg) {
        [Environment]::SetEnvironmentVariable("VF_GPU_FFMPEG", $localFfmpeg, "Process")
        $localProbe = Join-Path $Root "bin\ffprobe.exe"
        if (Test-Path $localProbe) {
            [Environment]::SetEnvironmentVariable("VF_GPU_FFPROBE", $localProbe, "Process")
        }
    }
}

function Read-InstallState {
    if (Test-Path $StateFile) {
        try {
            $state = Get-Content -Path $StateFile -Raw | ConvertFrom-Json
            if ($null -ne $state) {
                if ($null -eq $state.steps) { $state | Add-Member -NotePropertyName steps -NotePropertyValue ([pscustomobject]@{}) -Force }
                if ($state.steps -is [hashtable]) { $state.steps = [pscustomobject]$state.steps }
                return $state
            }
        } catch { }
    }
    return [pscustomobject]@{
        schema = 1
        kit_version = $ExpectedVersion
        steps = [pscustomobject]@{}
    }
}

function Set-InstallStep {
    param([string]$Name, [bool]$Ok, [hashtable]$Data = @{})
    $state = Read-InstallState
    if ($state.steps -is [hashtable]) { $state.steps = [pscustomobject]$state.steps }
    $entry = [pscustomobject]@{ ok = $Ok; at = (Get-Date).ToString("o") }
    foreach ($key in $Data.Keys) {
        $entry | Add-Member -NotePropertyName $key -NotePropertyValue $Data[$key] -Force
    }
    $state.steps | Add-Member -NotePropertyName $Name -NotePropertyValue $entry -Force
    $state | Add-Member -NotePropertyName schema -NotePropertyValue 1 -Force
    $state | Add-Member -NotePropertyName kit_version -NotePropertyValue $ExpectedVersion -Force
    $state | ConvertTo-Json -Depth 8 | Set-Content -Path $StateFile -Encoding UTF8
}

function Test-InstallStep {
    param([string]$Name)
    $state = Read-InstallState
    if ($null -eq $state.steps) { return $false }
    $property = $state.steps.PSObject.Properties[$Name]
    if ($null -eq $property) { return $false }
    return [bool]$property.Value.ok
}

function Resolve-Uv {
    if ($script:Uv -and (Test-Path $script:Uv)) { return $script:Uv }
    $local = Join-Path $Root "tools\uv\uv.exe"
    if (Test-Path $local) {
        $probe = Invoke-Native $local @("--version") -AllowFailure
        if ($probe.ExitCode -eq 0) {
            $script:Uv = $local
            return $script:Uv
        }
    }
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command uv -ErrorAction SilentlyContinue }
    if ($command) {
        $script:Uv = $command.Source
        return $script:Uv
    }
    $tools = Join-Path $Root "tools\uv"
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $zip = Join-Path $env:TEMP "uv-windows.zip"
    try {
        Write-Log "Baixando uv..."
        Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tools -Force
        $found = Get-ChildItem -Path $tools -Recurse -Filter uv.exe | Select-Object -First 1
        if ($found) {
            $script:Uv = $found.FullName
            return $script:Uv
        }
    } catch {
        Write-Warn ("Download direto do uv falhou: {0}" -f $_.Exception.Message)
    }
    try {
        & winget.exe install --id astral-sh.uv -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    } catch { }
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command uv -ErrorAction SilentlyContinue }
    if ($command) {
        $script:Uv = $command.Source
        return $script:Uv
    }
    Fail "E_UV_MISSING" "Nao foi possivel instalar o uv." "Baixe o ZIP oficial em https://github.com/astral-sh/uv/releases e coloque uv.exe em tools\uv\uv.exe."
}

function Ensure-Python {
    $uv = Resolve-Uv
    Invoke-Native $uv @("python", "install", "3.11") -AllowFailure | Out-Null
    if (Test-Path $VenvPython) {
        $probe = Invoke-Native $VenvPython @("-c", "import sys; print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))") -AllowFailure
        if ($probe.ExitCode -eq 0 -and ([string]$probe.Output).Trim() -eq "3.11") { return }
    }
    if (Test-Path $VenvDir) {
        Write-Log "Removendo .venv quebrado."
        Remove-Item -Recurse -Force $VenvDir
    }
    Invoke-Native $uv @("venv", $VenvDir, "--python", "3.11", "--python-preference", "only-managed", "--seed") | Out-Null
    if (-not (Test-Path $VenvPython)) {
        Fail "E_VENV_MISSING" "O venv nao tem python.exe." "Rode Repair como administrador e verifique o espaco em disco."
    }
}

function Get-WorkerWheel {
    $wheels = @(Get-ChildItem -Path $WheelsDir -Filter "videoflow_gpu_worker-*.whl" -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    if ($wheels.Count -eq 0) {
        Fail "E_WHEEL_MISSING" "O wheel do worker nao esta em wheels\." "Reextraia o ZIP do kit ou rode Install novamente."
    }
    return $wheels[0]
}

function Test-Checksum {
    param([string]$Path)
    $checks = Join-Path $Root "checksums.txt"
    if (-not (Test-Path $checks)) { return $true }
    $name = Split-Path -Leaf $Path
    $line = Get-Content -Path $checks | Where-Object { $_ -match [regex]::Escape($name) } | Select-Object -First 1
    if (-not $line) { return $true }
    $expected = (($line -split "\s+")[0]).ToLower()
    $actual = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()
    if ($expected -ne $actual) {
        Fail "E_WHEEL_INVALID" ("Checksum invalido para {0}." -f $name) "Reextraia o kit."
    }
    return $true
}

function Test-WheelChecksums {
    $checks = Join-Path $Root "checksums.txt"
    if (-not (Test-Path $checks)) { return }
    foreach ($line in Get-Content -Path $checks) {
        $text = $line.Trim()
        if (-not $text) { continue }
        $parts = $text -split "\s+"
        if ($parts.Count -lt 2) { continue }
        $expected = $parts[0].ToLower()
        $name = $parts[1]
        $path = Join-Path $WheelsDir $name
        if (-not (Test-Path $path)) {
            Fail "E_WHEEL_MISSING" ("Falta {0} em wheels\." -f $name) "Reextraia o kit."
        }
        $actual = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
        if ($actual -ne $expected) {
            Fail "E_WHEEL_INVALID" ("Checksum invalido para {0}." -f $name) "Reextraia o kit."
        }
    }
}

function Ensure-Worker {
    param([switch]$Force)
    $wheel = Get-WorkerWheel
    Test-Checksum $wheel.FullName | Out-Null
    $installed = ""
    if (Test-Path $VenvPython) {
        $probe = Invoke-Native $VenvPython @("-c", "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))") -AllowFailure
        if ($probe.ExitCode -eq 0) { $installed = ([string]$probe.Output).Trim() }
    }
    if (-not $Force -and $installed -eq $ExpectedVersion -and (Test-Path $WorkerExe)) { return }
    $uv = Resolve-Uv
    $cmdArgs = @("pip", "install", "--python", $VenvPython, "--no-index", "--find-links", $WheelsDir, "--reinstall", $wheel.FullName)
    $result = Invoke-Native $uv $cmdArgs -AllowFailure
    if ($result.ExitCode -ne 0) {
        Write-Warn "uv pip install falhou; tentando pip do venv."
        $fallback = Invoke-Native $VenvPython @("-m", "pip", "install", "--no-index", "--find-links", $WheelsDir, "--force-reinstall", $wheel.FullName) -AllowFailure
        if ($fallback.ExitCode -ne 0) {
            Fail "E_WORKER_INSTALL" "Falha ao instalar o worker." ("Veja {0}. O wheel e as dependencias estao em wheels\." -f $InstallLog) ("$uv $($cmdArgs -join ' ')") $result.Output
        }
    }
    $check = Invoke-Native $VenvPython @("-c", "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))") -AllowFailure
    $version = ([string]$check.Output).Trim()
    if ($version -ne $ExpectedVersion) {
        Fail "E_WORKER_VERSION" ("Worker instalado {0}, esperado {1}." -f $version, $ExpectedVersion) "Rode Repair."
    }
    $import = Invoke-Native $VenvPython @("-c", "import gpu_worker; print('ok')") -AllowFailure
    if ($import.ExitCode -ne 0) {
        Fail "E_WORKER_IMPORT" "O worker foi instalado mas gpu_worker nao importa." ("Veja {0}." -f $InstallLog) "" $import.Output
    }
    if (-not (Test-Path $WorkerExe)) {
        Fail "E_WORKER_EXE" "videoflow-gpu-worker.exe nao foi criado." "Rode Repair."
    }
    Set-InstallStep "worker" $true @{ version = $version }
}

function Test-PythonImport {
    param([string]$Module)
    if (-not (Test-Path $VenvPython)) { return $false }
    $probe = Invoke-Native $VenvPython @("-c", "import $Module") -AllowFailure
    return ($probe.ExitCode -eq 0)
}

function Get-PythonExpr {
    param([string]$Expression)
    if (-not (Test-Path $VenvPython)) { return "" }
    $probe = Invoke-Native $VenvPython @("-c", $Expression) -AllowFailure
    if ($probe.ExitCode -eq 0) { return ([string]$probe.Output).Trim() }
    return ""
}

function Ensure-CudaDlls {
    $site = Join-Path $VenvDir "Lib\site-packages"
    if (-not (Test-Path $site)) { return }
    $file = Join-Path $site "sitecustomize.py"
    $marker = "# VideoFlow CUDA DLL paths"
    $existing = ""
    if (Test-Path $file) { $existing = [string](Get-Content -Path $file -Raw) }
    if ($existing -notmatch [regex]::Escape($marker)) {
        $code = @'
# VideoFlow CUDA DLL paths
import os, glob
_here = os.path.dirname(__file__)
for _base in glob.glob(os.path.join(_here, "torch", "lib")):
    if os.path.isdir(_base):
        try:
            os.add_dll_directory(_base)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = _base + os.pathsep + os.environ.get("PATH", "")
for _base in glob.glob(os.path.join(_here, "nvidia", "*", "bin")):
    if os.path.isdir(_base):
        try:
            os.add_dll_directory(_base)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = _base + os.pathsep + os.environ.get("PATH", "")
'@
        Add-Content -Path $file -Value $code -Encoding UTF8
    }
}

function Ensure-Runtime {
    param([switch]$Force)
    $runtimeStep = "runtime-" + $RuntimeRev
    $importsOk = $true
    foreach ($module in @("faster_whisper", "rembg", "cv2", "onnxruntime", "torch")) {
        if (-not (Test-PythonImport $module)) { $importsOk = $false }
    }
    if ((Test-InstallStep $runtimeStep) -and $importsOk -and -not $Force) {
        $providers = Get-PythonExpr "import onnxruntime; print(','.join(onnxruntime.get_available_providers()))"
        if ($providers -notmatch "CUDAExecutionProvider") {
            Write-Warn "ONNX Runtime sem CUDAExecutionProvider; reparando o pacote GPU."
            $uv = Resolve-Uv
            Invoke-Native $uv @("pip", "uninstall", "--python", $VenvPython, "onnxruntime") -AllowFailure | Out-Null
            Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--upgrade", "--no-deps", "onnxruntime-gpu") -AllowFailure | Out-Null
            Ensure-CudaDlls
        }
        $cuda = Get-PythonExpr "import torch; print(1 if torch.cuda.is_available() else 0)"
        $ct2 = Get-PythonExpr "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
        if ($cuda -ne "1") {
            Write-Warn "Runtime instalado, mas PyTorch CUDA esta indisponivel. Rode Repair apos instalar o driver NVIDIA."
            return
        }
        if ($ct2 -ne "0" -and $ct2 -ne "") {
            return
        }
        Write-Warn "CTranslate2 CUDA indisponivel; reparando runtime."
    }
    $uv = Resolve-Uv
    if (Test-Path $RequirementsFile) {
        Write-Log "Instalando runtime Windows a partir de requirements-windows.txt."
        $result = Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--index-strategy", "unsafe-best-match", "-r", $RequirementsFile) -AllowFailure
        if ($result.ExitCode -ne 0) {
            Write-Warn "requirements-windows.txt falhou; instalando pacotes individualmente."
            Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--index-strategy", "unsafe-best-match", "--upgrade", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121", "--extra-index-url", "https://pypi.org/simple") | Out-Null
            Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--upgrade", "faster-whisper", "ctranslate2", "rembg", "opencv-python-headless", "numpy<2") | Out-Null
        }
    } else {
        Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--index-strategy", "unsafe-best-match", "--upgrade", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121", "--extra-index-url", "https://pypi.org/simple") | Out-Null
        Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--upgrade", "faster-whisper", "ctranslate2", "rembg", "opencv-python-headless", "numpy<2") | Out-Null
    }
    Invoke-Native $uv @("pip", "uninstall", "--python", $VenvPython, "onnxruntime") -AllowFailure | Out-Null
    Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--upgrade", "--no-deps", "onnxruntime-gpu") -AllowFailure | Out-Null
    Ensure-CudaDlls
    $cuda = Get-PythonExpr "import torch; print(1 if torch.cuda.is_available() else 0)"
    $ct2 = Get-PythonExpr "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
    if ($cuda -ne "1") { Write-Warn "PyTorch CUDA indisponivel; o worker pode cair para CPU." }
    if ($ct2 -eq "0" -or $ct2 -eq "") {
        Write-Warn "CTranslate2 CUDA indisponivel; instalando cuDNN/cuBLAS como fallback."
        Invoke-Native $uv @("pip", "install", "--python", $VenvPython, "--upgrade", "nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-runtime-cu12") -AllowFailure | Out-Null
        Ensure-CudaDlls
        $ct2 = Get-PythonExpr "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
    }
    $providers = Get-PythonExpr "import onnxruntime; print(','.join(onnxruntime.get_available_providers()))"
    if ($providers -notmatch "CUDAExecutionProvider") {
        Write-Warn "ONNX Runtime sem CUDAExecutionProvider; matte pode cair para CPU."
    }
    Set-InstallStep $runtimeStep $true @{ cuda = $cuda; ct2 = $ct2; providers = $providers }
}

function Test-Nvenc {
    param([string]$Ffmpeg)
    if (-not (Test-Path $Ffmpeg)) { return $false }
    $probe = Invoke-Native $Ffmpeg @(
        "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=128x72:d=0.1",
        "-c:v", "h264_nvenc", "-f", "null", "-"
    ) -AllowFailure
    return ($probe.ExitCode -eq 0)
}

function Install-Ffmpeg {
    $zip = Join-Path $env:TEMP "videoflow-ffmpeg.zip"
    $temporary = Join-Path $env:TEMP "videoflow-ffmpeg"
    if (Test-Path $temporary) { Remove-Item -Recurse -Force $temporary }
    $urls = @(
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    )
    $downloaded = $false
    foreach ($url in $urls) {
        try {
            Write-Log ("Baixando FFmpeg: {0}" -f $url)
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath $temporary -Force
            $downloaded = $true
            break
        } catch {
            Write-Warn ("Falha no download do FFmpeg: {0}" -f $_.Exception.Message)
        }
    }
    if (-not $downloaded) {
        Fail "E_FFMPEG_DOWNLOAD" "Nao foi possivel baixar o FFmpeg." "Baixe um build com NVENC e coloque ffmpeg.exe/ffprobe.exe em bin\."
    }
    $bin = Join-Path $Root "bin"
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    $ffmpeg = Get-ChildItem -Path $temporary -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    $ffprobe = Get-ChildItem -Path $temporary -Recurse -Filter ffprobe.exe | Select-Object -First 1
    if (-not $ffmpeg) { Fail "E_FFMPEG_ARCHIVE" "O ZIP do FFmpeg nao tem ffmpeg.exe." }
    Copy-Item -Path $ffmpeg.FullName -Destination (Join-Path $bin "ffmpeg.exe") -Force
    if ($ffprobe) {
        Copy-Item -Path $ffprobe.FullName -Destination (Join-Path $bin "ffprobe.exe") -Force
    }
}

function Ensure-Ffmpeg {
    param([switch]$Force)
    $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    if (-not (Test-Path $ffmpeg)) {
        $system = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if ($system) { $ffmpeg = $system.Source }
    }
    if (-not (Test-Path $ffmpeg)) {
        Install-Ffmpeg
        $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    }
    if (-not (Test-Path $ffmpeg)) {
        Fail "E_FFMPEG_MISSING" "ffmpeg.exe nao encontrado." "Coloque um build com NVENC em bin\."
    }
    $nvenc = Test-Nvenc $ffmpeg
    if (-not $nvenc -and $Force) {
        Write-Warn "FFmpeg local sem NVENC; baixando um build novo."
        Install-Ffmpeg
        $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
        $nvenc = Test-Nvenc $ffmpeg
    }
    if (-not $nvenc) {
        $probe = Invoke-Native $ffmpeg @(
            "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=128x72:d=0.1",
            "-c:v", "h264_nvenc", "-f", "null", "-"
        ) -AllowFailure
        $detail = ($probe.Output -split "`n" | Select-Object -Last 1)
        Write-Warn ("FFmpeg sem NVENC: {0}" -f $detail)
        Write-Warn "O worker pode ser usado com libx264; o render remoto continua disponivel."
    }
    $env:VF_GPU_FFMPEG = $ffmpeg
    $ffprobe = Join-Path $Root "bin\ffprobe.exe"
    if (Test-Path $ffprobe) { $env:VF_GPU_FFPROBE = $ffprobe }
    Set-InstallStep "ffmpeg" $true @{ nvenc = $nvenc }
}

function Get-NvidiaInfo {
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $smi) {
        $programFiles = $env:ProgramFiles
        if (-not $programFiles) { $programFiles = "C:\Program Files" }
        $systemRoot = $env:SystemRoot
        if (-not $systemRoot) { $systemRoot = "C:\Windows" }
        $candidates = @(
            (Join-Path $programFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
            (Join-Path $systemRoot "System32\nvidia-smi.exe")
        )
        foreach ($candidate in $candidates) {
            try {
                if (Test-Path $candidate) {
                    $smi = [pscustomobject]@{ Source = $candidate }
                    break
                }
            } catch { }
        }
    }
    if (-not $smi) {
        return [pscustomobject]@{ available = $false; name = ""; driver = ""; vram_mb = 0 }
    }
    $probe = Invoke-Native $smi.Source @("--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits") -AllowFailure
    if ($probe.ExitCode -ne 0 -or -not $probe.Output) {
        return [pscustomobject]@{ available = $false; name = ""; driver = ""; vram_mb = 0 }
    }
    $line = (($probe.Output -split "`n")[0]).Trim()
    $parts = $line -split ","
    $name = ""
    $driver = ""
    $vram = 0
    if ($parts.Count -ge 1) { $name = $parts[0].Trim() }
    if ($parts.Count -ge 2) { $driver = $parts[1].Trim() }
    if ($parts.Count -ge 3) { [int]::TryParse($parts[2].Trim(), [ref]$vram) | Out-Null }
    return [pscustomobject]@{ available = $true; name = $name; driver = $driver; vram_mb = $vram }
}

function Ensure-Nvidia {
    $info = Get-NvidiaInfo
    if (-not $info.available) {
        Fail "E_NVIDIA_DRIVER" "nvidia-smi nao encontrado." "Instale o driver NVIDIA e reinicie o Windows."
    }
    Write-Log ("GPU: {0}, driver {1}, {2} MiB" -f $info.name, $info.driver, $info.vram_mb)
    Set-InstallStep "nvidia" $true @{ name = $info.name; driver = $info.driver; vram_mb = $info.vram_mb }
}

function Ensure-Firewall {
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    if (-not (Test-Admin)) {
        Write-Warn "Firewall precisa de Administrator; o Windows pode pedir permissao na primeira conexao."
        return
    }
    $rules = @(
        @{ Name = "VideoFlow GPU Worker TCP"; Protocol = "TCP"; Port = $port },
        @{ Name = "VideoFlow GPU Worker UDP"; Protocol = "UDP"; Port = 8767 }
    )
    foreach ($rule in $rules) {
        $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
        if (-not $existing) {
            New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Protocol $rule.Protocol -LocalPort $rule.Port -Action Allow -Profile Any | Out-Null
            Write-Log ("Regra de firewall criada: {0} {1} (qualquer perfil)" -f $rule.Protocol, $rule.Port)
        } else {
            Set-NetFirewallRule -DisplayName $rule.Name -Profile Any -Action Allow -Enabled True | Out-Null
        }
    }
    try {
        $connectionProfile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($connectionProfile -and $connectionProfile.NetworkCategory -eq "Public") {
            Write-Log "Rede Public detectada; a regra agora cobre Public, Private e Domain."
        }
    } catch { }
    Set-InstallStep "firewall" $true
}

function Ensure-Port {
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $listener = $null
    try {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch { }
    if (-not $listener) { return }
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -like "videoflow-gpu-worker*") {
        Write-Warn ("Worker antigo na porta {0}; parando." -f $port)
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        return
    }
    $name = "unknown"
    if ($process) { $name = $process.ProcessName }
    Fail "E_PORT_IN_USE" ("A porta {0} esta em uso por {1} (PID {2})." -f $port, $name, $listener.OwningProcess) "Feche o processo ou mude VF_GPU_PORT em worker.env."
}

function Ensure-SharedMount {
    $shared = $script:EnvMap["VF_GPU_SHARED_ROOT"]
    if (-not $shared) { return }
    try {
        if (-not (Test-Path $shared)) { throw "path does not exist" }
        $probe = Join-Path $shared ".videoflow-probe"
        Set-Content -Path $probe -Value "ok" -Encoding ASCII
        Remove-Item -Path $probe -Force
        Write-Log "Shared mount gravavel: $shared"
    } catch {
        Write-Warn "Shared mount indisponivel; usando HTTP."
        [Environment]::SetEnvironmentVariable("VF_GPU_SHARED_ROOT", $null, "Process")
        $script:EnvMap["VF_GPU_SHARED_ROOT"] = ""
    }
}

function Install-Worker {
    param([switch]$Force)
    Stop-Worker -Quiet
    Ensure-EnvFile
    Test-WheelChecksums
    Resolve-Uv | Out-Null
    Ensure-Python
    Ensure-Worker -Force:$Force
    Ensure-Runtime
    Ensure-Ffmpeg -Force:$Force
    $gpu = Get-NvidiaInfo
    if ($gpu.available) {
        Set-InstallStep "nvidia" $true @{ name = $gpu.name; driver = $gpu.driver; vram_mb = $gpu.vram_mb }
        Write-Log ("GPU: {0}, driver {1}, {2} MiB" -f $gpu.name, $gpu.driver, $gpu.vram_mb)
    } else {
        Write-Warn "Driver NVIDIA nao encontrado; instale antes de iniciar o worker."
    }
    Ensure-Firewall
    Ensure-SharedMount
    Set-InstallStep "install" $true @{ version = $ExpectedVersion }
    Write-Ok "Instalacao/reparo concluido."
}

function Wait-Health {
    param([int]$TimeoutSec = 120)
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $last = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
            if ($health.available) { return $health }
            $last = "health available=false"
        } catch {
            $last = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    $tail = ""
    if (Test-Path $WorkerErr) { $tail = (Get-Content -Path $WorkerErr -Tail 60 | Out-String) }
    Fail "E_HEALTH_TIMEOUT" ("O worker nao ficou saudavel em {0}s. {1}" -f $TimeoutSec, $last) "Veja logs\worker-error.log." "" $tail
}

function Get-PowerShellExe {
    $systemRoot = $env:SystemRoot
    if (-not $systemRoot) { $systemRoot = "C:\Windows" }
    try {
        $candidate = Join-Path $systemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        if (Test-Path $candidate) { return $candidate }
    } catch { }
    $command = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return "powershell.exe"
}

function Start-Supervisor {
    $psExe = Get-PowerShellExe
    $quoted = '"' + $PSCommandPath + '"'
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $quoted, "-Action", "Supervisor", "-Silent")
    Write-Log "Iniciando supervisor..."
    $process = Start-Process -FilePath $psExe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $LogDir "supervisor.pid") -Value $process.Id -Encoding ASCII
    return $process
}

function Start-Worker {
    Ensure-EnvFile
    Ensure-Nvidia
    if (-not (Test-Path $WorkerExe)) {
        Install-Worker
    } else {
        Ensure-Worker
        Ensure-Runtime
        Ensure-Ffmpeg
    }
    Ensure-SharedMount
    Ensure-Port
    $pidFile = Join-Path $LogDir "supervisor.pid"
    if (Test-Path $pidFile) {
        $value = 0
        [int]::TryParse(([string](Get-Content -Path $pidFile -Raw)).Trim(), [ref]$value) | Out-Null
        if ($value -gt 0) {
            $existing = Get-Process -Id $value -ErrorAction SilentlyContinue
            if ($existing) {
                Write-Log ("Supervisor ja rodando (PID {0}); verificando saude." -f $value)
                $health = Wait-Health
                Write-Ok ("Worker saudavel: {0}" -f $health.gpu_name)
                return
            }
        }
    }
    Set-Content -Path (Join-Path $LogDir "desired_state") -Value "running" -Encoding ASCII
    $process = Start-Supervisor
    $health = Wait-Health
    if ($process.HasExited) {
        $tail = ""
        if (Test-Path $WorkerErr) { $tail = (Get-Content -Path $WorkerErr -Tail 60 | Out-String) }
        Fail "E_SUPERVISOR_EXIT" "O supervisor encerrou antes do worker ficar saudavel." "Veja logs\bootstrap.log e logs\worker-error.log." "" $tail
    }
    Write-Ok ("Worker saudavel: {0} na porta {1}" -f $health.gpu_name, $script:EnvMap["VF_GPU_PORT"])
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return }
    try { & taskkill.exe /PID $ProcessId /T /F 2>&1 | Out-Null } catch { }
}

function Stop-Worker {
    param([switch]$Quiet)
    Set-Content -Path (Join-Path $LogDir "desired_state") -Value "stopped" -Encoding ASCII
    foreach ($name in @("supervisor.pid", "worker.pid")) {
        $path = Join-Path $LogDir $name
        if (Test-Path $path) {
            $value = 0
            [int]::TryParse(([string](Get-Content -Path $path -Raw)).Trim(), [ref]$value) | Out-Null
            if ($value -gt 0) {
                $process = Get-Process -Id $value -ErrorAction SilentlyContinue
                if ($process) {
                    if ($name -eq "supervisor.pid" -and $process.ProcessName -notlike "powershell*") {
                        Write-Warn "PID do supervisor nao parece PowerShell; ignorando."
                    } else {
                        Stop-ProcessTree $value
                    }
                }
            }
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }
    Get-Process -Name "videoflow-gpu-worker*" -ErrorAction SilentlyContinue | ForEach-Object { Stop-ProcessTree $_.Id }
    Start-Sleep -Seconds 1
    if (-not $Quiet) { Write-Ok "Worker parado." }
}

function Get-StatusObject {
    Ensure-EnvFile
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $supervisor = $false
    $pidFile = Join-Path $LogDir "supervisor.pid"
    if (Test-Path $pidFile) {
        $value = 0
        [int]::TryParse(([string](Get-Content -Path $pidFile -Raw)).Trim(), [ref]$value) | Out-Null
        if ($value -gt 0) {
            $supervisor = $null -ne (Get-Process -Id $value -ErrorAction SilentlyContinue)
        }
    }
    $health = $null
    try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3 } catch { }
    $workerVersion = ""
    if (Test-Path $VenvPython) {
        $probe = Invoke-Native $VenvPython @("-c", "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))") -AllowFailure
        if ($probe.ExitCode -eq 0) { $workerVersion = ([string]$probe.Output).Trim() }
    }
    return [pscustomobject]@{
        ok = $true
        installed = (Test-Path $WorkerExe)
        supervisor = $supervisor
        port = $port
        health = $health
        worker_version = $workerVersion
        expected_version = $ExpectedVersion
        logs = $LogDir
        last_error = (Join-Path $LogDir "last-error.json")
    }
}

function Show-Status {
    $status = Get-StatusObject
    if ($Json) {
        $status | ConvertTo-Json -Depth 8
        return
    }
    Write-Host ("Instalado: {0}" -f $status.installed)
    Write-Host ("Supervisor: {0}" -f $status.supervisor)
    Write-Host ("Porta: {0}" -f $status.port)
    Write-Host ("Worker: {0} (esperado {1})" -f $status.worker_version, $status.expected_version)
    if ($status.health) {
        Write-Host ("Health: {0}" -f $status.health.status)
        Write-Host ("GPU: {0}" -f $status.health.gpu_name)
        Write-Host ("VRAM: {0}/{1} MB" -f $status.health.vram_used_mb, $status.health.vram_total_mb)
        Write-Host ("Capabilities: {0}" -f ($status.health.capabilities -join ", "))
        Write-Host ("Auth: {0}" -f $status.health.auth_mode)
        Write-Host ("Encoder: {0} (nvenc={1})" -f $status.health.encoder, $status.health.nvenc)
        Write-Host ("URIs: {0}" -f (($status.health.lan_urls | ForEach-Object { "http://$($_):$($status.port)" }) -join ", "))
        Write-Host ("Painel: http://127.0.0.1:{0}/" -f $status.port)
    } else {
        Write-Host "Health: offline"
    }
}

function Open-Dashboard {
    Ensure-EnvFile
    $port = [int]$script:EnvMap["VF_GPU_PORT"]
    $url = "http://127.0.0.1:$port/"
    Write-Log ("Abrindo painel: {0}" -f $url)
    Start-Process $url
}
function Show-Doctor {
    Ensure-EnvFile
    $uv = ""
    try { $uv = Resolve-Uv } catch { }
    $gpu = Get-NvidiaInfo
    $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    $nvenc = $false
    if (Test-Path $ffmpeg) { $nvenc = Test-Nvenc $ffmpeg }
    $torch = Get-PythonExpr "import torch; print(torch.__version__)"
    $cuda = Get-PythonExpr "import torch; print(1 if torch.cuda.is_available() else 0)"
    $ct2 = Get-PythonExpr "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
    $providers = Get-PythonExpr "import onnxruntime; print(','.join(onnxruntime.get_available_providers()))"
    Write-Host ("uv: {0}" -f $(if ($uv) { $uv } else { "missing" }))
    Write-Host ("venv: {0}" -f $(if (Test-Path $VenvPython) { "ok" } else { "missing" }))
    Write-Host ("worker: {0}" -f $(if (Test-Path $WorkerExe) { "ok" } else { "missing" }))
    Write-Host ("nvidia-smi: {0}" -f $(if ($gpu.available) { "$($gpu.name) / $($gpu.driver)" } else { "missing" }))
    Write-Host ("ffmpeg: {0}" -f $(if (Test-Path $ffmpeg) { $ffmpeg } else { "missing" }))
    Write-Host ("nvenc: {0}" -f $nvenc)
    Write-Host ("torch: {0} (cuda={1})" -f $torch, $cuda)
    Write-Host ("ctranslate2 cuda devices: {0}" -f $ct2)
    Write-Host ("onnx providers: {0}" -f $providers)
    Show-Status
}

function Show-Diagnose {
    $directory = Join-Path $LogDir ("diagnostic-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $info = [ordered]@{
        generated_at = (Get-Date).ToString("o")
        root = $Root
        powershell = $PSVersionTable.PSVersion.ToString()
        windows = [Environment]::OSVersion.VersionString
        admin = (Test-Admin)
        expected_version = $ExpectedVersion
        worker_version = (Get-PythonExpr "import importlib.metadata as m; print(m.version('videoflow-gpu-worker'))")
        torch = (Get-PythonExpr "import torch; print(torch.__version__)")
        cuda = (Get-PythonExpr "import torch; print(1 if torch.cuda.is_available() else 0)")
        ct2 = (Get-PythonExpr "import ctranslate2; print(ctranslate2.get_cuda_device_count())")
        providers = (Get-PythonExpr "import onnxruntime; print(','.join(onnxruntime.get_available_providers()))")
        gpu = (Get-NvidiaInfo)
        install_state = (Read-InstallState)
    }
    $info | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $directory "diagnostic.json") -Encoding UTF8
    foreach ($file in @($BootstrapLog, $InstallLog, $WorkerLog, $WorkerErr)) {
        if (Test-Path $file) {
            Copy-Item -Path $file -Destination (Join-Path $directory (Split-Path -Leaf $file)) -Force
        }
    }
    $zip = "$directory.zip"
    Compress-Archive -Path (Join-Path $directory "*") -DestinationPath $zip -Force
    Write-Host ("Diagnostico: {0}" -f $zip)
}

function Show-Logs {
    foreach ($file in @($BootstrapLog, $InstallLog, $WorkerErr)) {
        if (Test-Path $file) {
            Write-Host ("--- {0} ---" -f (Split-Path -Leaf $file))
            Get-Content -Path $file -Tail 80
        }
    }
}

function Install-Autostart {
    $psExe = Get-PowerShellExe
    $argument = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action Start -Silent"
    $action = New-ScheduledTaskAction -Execute $psExe -Argument $argument
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "VideoFlow GPU Worker" -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
    Write-Ok "Autostart registrado."
}

function Remove-Autostart {
    Unregister-ScheduledTask -TaskName "VideoFlow GPU Worker" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Ok "Autostart removido."
}

function Uninstall-Worker {
    Stop-Worker -Quiet
    Remove-Autostart
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
    Write-Ok "Venv removido. worker.env e logs mantidos."
}

function Invoke-Benchmark {
    Ensure-EnvFile
    $gpu = Get-NvidiaInfo
    if (-not $gpu.available) {
        Fail "E_NVIDIA_DRIVER" "Sem GPU para benchmark." "Instale o driver NVIDIA."
    }
    $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    if (-not (Test-Path $ffmpeg)) {
        Fail "E_FFMPEG_MISSING" "FFmpeg nao encontrado." "Rode Install."
    }
    $started = Get-Date
    $nvenc = Test-Nvenc $ffmpeg
    $elapsed = [int]((Get-Date) - $started).TotalMilliseconds
    $payload = [ordered]@{
        ok = $nvenc
        gpu = $gpu.name
        nvenc = $nvenc
        nvenc_ms = $elapsed
        at = (Get-Date).ToString("o")
    }
    $payload | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $LogDir "benchmark.json") -Encoding UTF8
    $payload | ConvertTo-Json -Depth 5
}

function Invoke-SelfTest {
    $results = @()
    $results += [pscustomobject]@{ name = "path"; ok = (Test-Path $Root); detail = $Root }
    $free = 0
    try {
        $driveName = (Get-Item $Root).PSDrive.Name
        $free = [math]::Round((Get-PSDrive -Name $driveName).Free / 1GB, 1)
    } catch { }
    $results += [pscustomobject]@{ name = "disk_gb"; ok = ($free -ge 12); detail = $free }
    $wheels = @(Get-ChildItem -Path $WheelsDir -Filter "videoflow_gpu_worker-*.whl" -ErrorAction SilentlyContinue)
    $results += [pscustomobject]@{ name = "worker_wheel"; ok = ($wheels.Count -gt 0); detail = ($wheels | Select-Object -First 1).Name }
    $results += [pscustomobject]@{ name = "requirements"; ok = (Test-Path $RequirementsFile); detail = $RequirementsFile }
    $gpu = Get-NvidiaInfo
    $results += [pscustomobject]@{ name = "nvidia"; ok = $gpu.available; detail = $gpu.name }
    $ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
    $results += [pscustomobject]@{ name = "ffmpeg"; ok = (Test-Path $ffmpeg); detail = $ffmpeg }
    $results | Format-Table -AutoSize
    if ($DryRun) { Write-Host "DryRun: nenhum download/instalacao executado." }
}

function Initialize-JobObject {
    try {
        $code = @"
using System;
using System.Runtime.InteropServices;
public static class VFJob {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetInformationJobObject(IntPtr hJob, int infoClass, IntPtr lpInfo, uint cbInfoLength);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);
    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }
    public static IntPtr CreateKillOnClose() {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = 0x2000;
        int length = Marshal.SizeOf(info);
        IntPtr ptr = Marshal.AllocHGlobal(length);
        try {
            Marshal.StructureToPtr(info, ptr, false);
            SetInformationJobObject(job, 9, ptr, (uint)length);
        } finally {
            Marshal.FreeHGlobal(ptr);
        }
        return job;
    }
    public static bool Assign(IntPtr job, IntPtr process) {
        return AssignProcessToJobObject(job, process);
    }
}
"@
        Add-Type -TypeDefinition $code -ErrorAction Stop
        $script:JobAvailable = $true
    } catch {
        $script:JobAvailable = $false
    }
}

function Rotate-Log {
    param([string]$Path, [int]$MaxBytes = 10485760)
    if (-not (Test-Path $Path)) { return }
    try {
        if ((Get-Item $Path).Length -lt $MaxBytes) { return }
        $backup = "$Path.1"
        if (Test-Path $backup) { Remove-Item -Path $backup -Force -ErrorAction SilentlyContinue }
        Move-Item -Path $Path -Destination $backup -Force
    } catch { }
}

function Start-WorkerProcess {
    Rotate-Log $WorkerLog
    Rotate-Log $WorkerErr
    $process = Start-Process -FilePath $WorkerExe -WorkingDirectory $Root -RedirectStandardOutput $WorkerLog -RedirectStandardError $WorkerErr -WindowStyle Hidden -PassThru
    return $process
}

function Supervisor {
    $mutex = New-Object Threading.Mutex($false, "Local\VideoFlowGpuWorkerSupervisor")
    if (-not $mutex.WaitOne(0)) { return }
    try {
        Ensure-EnvFile
        $desired = Join-Path $LogDir "desired_state"
        if (-not (Test-Path $desired)) { Set-Content -Path $desired -Value "running" -Encoding ASCII }
        $backoff = @(2, 5, 15, 30, 60)
        $attempt = 0
        while ($true) {
            $state = "running"
            if (Test-Path $desired) { $state = ([string](Get-Content -Path $desired -Raw)).Trim() }
            if ($state -eq "stopped") { break }
            if (-not (Test-Path $WorkerExe)) {
                Write-Log "Worker exe ausente; supervisor parando." "ERROR"
                break
            }
            $process = Start-WorkerProcess
            Set-Content -Path (Join-Path $LogDir "worker.pid") -Value $process.Id -Encoding ASCII
            $job = $null
            if ($script:JobAvailable) {
                try {
                    $job = [VFJob]::CreateKillOnClose()
                    [VFJob]::Assign($job, $process.Handle) | Out-Null
                } catch {
                    $job = $null
                }
            }
            $failures = 0
            while (-not $process.HasExited) {
                Start-Sleep -Seconds 5
                $state = "running"
                if (Test-Path $desired) { $state = ([string](Get-Content -Path $desired -Raw)).Trim() }
                if ($state -eq "stopped") { break }
                $healthy = $false
                try {
                    $port = [int]$script:EnvMap["VF_GPU_PORT"]
                    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
                    if ($health.available) { $healthy = $true }
                } catch { }
                if ($healthy) {
                    $failures = 0
                } else {
                    $failures++
                }
                if ($failures -ge 3) {
                    Write-Warn "Worker sem health por 15s; reiniciando."
                    Stop-ProcessTree $process.Id
                    break
                }
            }
            if ($job) {
                try { [VFJob]::CloseHandle($job) | Out-Null } catch { }
            }
            if ($state -eq "stopped") { break }
            $attempt++
            if ($attempt -gt 20) {
                Write-Log "Muitas reinicializacoes; supervisor parando." "ERROR"
                break
            }
            $delay = $backoff[[Math]::Min($attempt - 1, $backoff.Length - 1)]
            Write-Log ("Worker encerrou; reiniciando em {0}s." -f $delay)
            Start-Sleep -Seconds $delay
        }
    } finally {
        Remove-Item -Path (Join-Path $LogDir "worker.pid") -Force -ErrorAction SilentlyContinue
        try { $mutex.ReleaseMutex() } catch { }
        $mutex.Dispose()
    }
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "VideoFlow Windows GPU Worker"
        Write-Host "1) Instalar / reparar tudo"
        Write-Host "2) Iniciar worker"
        Write-Host "3) Parar worker"
        Write-Host "4) Status / saude"
        Write-Host "5) Diagnostico completo"
        Write-Host "6) Ver logs"
        Write-Host "7) Instalar autostart"
        Write-Host "8) Remover autostart"
        Write-Host "9) Benchmark rapido"
        Write-Host "10) Abrir pasta de logs"
        Write-Host "11) Desinstalar venv"
        Write-Host "12) Abrir painel do worker"
        Write-Host "0) Sair"
        $choice = Read-Host "Escolha"
        switch ($choice) {
            "1" { Invoke-MenuAction "Instalar/reparar" { Install-Worker -Force } }
            "2" { Invoke-MenuAction "Iniciar worker" { Start-Worker } }
            "3" { Invoke-MenuAction "Parar worker" { Stop-Worker } }
            "4" { Invoke-MenuAction "Status" { Show-Status } }
            "5" { Invoke-MenuAction "Diagnostico" { Show-Diagnose } }
            "6" { Invoke-MenuAction "Logs" { Show-Logs } }
            "7" { Invoke-MenuAction "Autostart" { Install-Autostart } }
            "8" { Invoke-MenuAction "Remover autostart" { Remove-Autostart } }
            "9" { Invoke-MenuAction "Benchmark" { Invoke-Benchmark } }
            "10" { Invoke-MenuAction "Abrir logs" { Start-Process explorer.exe $LogDir } }
            "11" { Invoke-MenuAction "Desinstalar" { Uninstall-Worker } }
            "12" { Invoke-MenuAction "Painel" { Open-Dashboard } }
            "0" { return }
            default { Write-Host "Opcao invalida." }
        }
    }
}

function Main {
    Initialize-Logs
    Initialize-JobObject
    if (-not $Silent -and $Action -eq "Menu") {
        try {
            Start-Transcript -Path (Join-Path $LogDir "console.log") -Append | Out-Null
            $script:TranscriptStarted = $true
        } catch { }
    }
    try {
        switch ($Action) {
            "Menu" { Show-Menu }
            "Install" { Invoke-Step "Install" { Install-Worker } }
            "Repair" { Invoke-Step "Repair" { Stop-Worker -Quiet; Install-Worker -Force } }
            "Start" { Invoke-Step "Start" { Start-Worker } }
            "Stop" { Invoke-Step "Stop" { Stop-Worker } }
            "Restart" { Invoke-Step "Restart" { Stop-Worker; Start-Worker } }
            "Status" { Invoke-Step "Status" { Show-Status } }
            "Doctor" { Invoke-Step "Doctor" { Show-Doctor } }
            "Diagnose" { Invoke-Step "Diagnose" { Show-Diagnose } }
            "Logs" { Invoke-Step "Logs" { Show-Logs } }
            "Autostart" { Invoke-Step "Autostart" { Install-Autostart } }
            "Uninstall" { Invoke-Step "Uninstall" { Uninstall-Worker } }
            "Benchmark" { Invoke-Step "Benchmark" { Invoke-Benchmark } }
            "Dashboard" { Invoke-Step "Dashboard" { Open-Dashboard } }
            "Supervisor" { Supervisor }
            "SelfTest" { Invoke-Step "SelfTest" { Invoke-SelfTest } }
        }
    } catch {
        if ($null -eq $script:LastError) { Set-UnexpectedError $_ }
        Show-ErrorPanel
        if ($Action -eq "Menu" -and -not $Silent) {
            try {
                Read-Host "Pressione Enter para tentar reabrir o menu" | Out-Null
                Show-Menu
            } catch {
                exit 1
            }
        } else {
            exit 1
        }
    } finally {
        if ($script:TranscriptStarted) {
            try { Stop-Transcript | Out-Null } catch { }
        }
    }
}

Main
