# drscreen deploy/run script  -  native Windows PowerShell equivalent of deploy.sh.
#
# deploy.sh needs bash (Git Bash or WSL) to run on Windows. This script does the
# same job  -  create/locate .venv, install dependencies, set up .env, then launch
# drscreen  -  using only PowerShell, so no extra tooling is required.
#
# Usage (run from PowerShell, in this folder):
#   .\deploy.ps1                    # set up the environment, then launch the web app
#   .\deploy.ps1 setup               # only set up the environment, don't run anything
#   .\deploy.ps1 doctor               # set up, then run `drscreen doctor`
#   .\deploy.ps1 predict img.png       # set up, then forward args to `drscreen`
#   .\deploy.ps1 -SkipSetup web         # skip the setup check (fast path, once installed)
#
# If PowerShell refuses to run this script ("running scripts is disabled on this
# system"), run once: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# and confirm, then re-run .\deploy.ps1.

param(
    [switch]$SkipSetup,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args_ = @()
)

$ErrorActionPreference = "Stop"

function Info($msg)  { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[deploy] $msg" -ForegroundColor Green }
function WarnMsg($msg) { Write-Host "[deploy] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[deploy] $msg" -ForegroundColor Red; exit 1 }

# -- resolve paths relative to this script, not the caller's cwd --------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Info "Detected platform: Windows (native PowerShell)"

# -- find a usable Python (3.10+) ------------------------------------------------------
function Find-Python {
    foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "py -3.10", "py -3", "python", "python3")) {
        $parts = $candidate.Split(" ")
        $exe = $parts[0]
        $cmdArgs = if ($parts.Length -gt 1) { $parts[1..($parts.Length - 1)] } else { @() }
        $found = Get-Command $exe -ErrorAction SilentlyContinue
        if ($found) {
            try {
                & $exe @cmdArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    return $candidate
                }
            } catch {}
        }
    }
    return $null
}

$PythonCmd = Find-Python
if (-not $PythonCmd) {
    Fail "No Python 3.10+ found on PATH. Install it from https://python.org/downloads (check `"Add python.exe to PATH`" during install), then re-run this script."
}
$PyParts = $PythonCmd.Split(" ")
$PyExe = $PyParts[0]
$PyArgs = if ($PyParts.Length -gt 1) { $PyParts[1..($PyParts.Length - 1)] } else { @() }
$VersionOutput = (& $PyExe @PyArgs --version) 2>&1
Info "Using Python: $PythonCmd ($VersionOutput)"

# -- create / locate the virtualenv ----------------------------------------------------
$VenvDir = Join-Path $ScriptDir ".venv"
if (-not (Test-Path $VenvDir)) {
    Info "Creating virtual environment at .venv ..."
    & $PyExe @PyArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to create the virtual environment."
    }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvDrscreen = Join-Path $VenvDir "Scripts\drscreen.exe"
if (-not (Test-Path $VenvPython)) {
    Fail "Could not find $VenvPython. Delete the .venv folder and re-run this script to recreate it."
}
Info "Virtual environment ready: $VenvDir"

# -- install / update the project and its dependencies ---------------------------------
if (-not $SkipSetup) {
    & $VenvPython -m pip --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Info "pip isn't available in this virtual environment; bootstrapping it ..."
        & $VenvPython -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) {
            Fail "Couldn't bootstrap pip into .venv. Delete the .venv folder and re-run this script to recreate it from scratch."
        }
    }

    Info "Installing dependencies (this can take a few minutes the first time) ..."
    & $VenvPython -m pip install --upgrade --quiet pip
    & $VenvPython -m pip install --quiet -e "${ScriptDir}[all]"
    if ($LASTEXITCODE -ne 0) {
        Fail "Dependency installation failed  -  see the pip output above."
    }
    Ok "Dependencies installed."
} else {
    Info "Skipping dependency install (-SkipSetup)."
}

# -- .env: create from the example on first run, never overwrite an existing one -------
$EnvFile = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    WarnMsg "Created .env from .env.example. Edit it to set your clinic name, SMS provider credentials, etc.  -  see README.md."
}

# -- web UI: build the static export once, then reuse it -------------------------------
# `drscreen web` serves frontend\out itself, so the UI needs Node only at
# build time - never at runtime.
$UiDir = Join-Path $ScriptDir "frontend"
$UiOut = Join-Path $UiDir "out"
if ((-not $SkipSetup) -and (-not (Test-Path $UiOut))) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Info "Building the web UI (first run only; a few minutes) ..."
        Push-Location $UiDir
        if (-not (Test-Path (Join-Path $UiDir "node_modules"))) {
            npm install --no-audit --no-fund
        }
        npm run build
        Pop-Location
        if (Test-Path $UiOut) {
            Ok "Web UI built."
        } else {
            WarnMsg "UI build failed - the API will still start, but there'll be no interface. Fix it with: cd frontend; npm install; npm run build"
        }
    } else {
        WarnMsg "Node.js/npm not found, so the web UI can't be built. Install Node 20+ from https://nodejs.org and re-run, or use the CLI commands (predict, batch-screen)."
    }
}

# -- database: create the file/schema so first run isn't an empty-table error ----------
# The default is a SQLite file under data\, which needs no server and no
# credentials, so a fresh machine has a working database with no setup. Point
# DRS_DATABASE_URL at MySQL/Postgres in .env to use one instead.
if (-not $SkipSetup) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ScriptDir "data") | Out-Null
    & $VenvDrscreen init-db 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Ok "Database ready."
    } else {
        WarnMsg "Could not initialise the database. Check DRS_DATABASE_URL in .env; run 'drscreen init-db' to see the error."
    }
}

# -- model weights: warn, don't fail (some commands don't need them) -------------------
# Not in git: it's a ~240 MB binary. Set DRS_MODEL_URL in .env (or the
# environment) to a direct download and this fetches it automatically.
$ModelFile = Join-Path $ScriptDir "models\classifier.pt"
if ((-not (Test-Path $ModelFile)) -and $env:DRS_MODEL_URL) {
    Info "Downloading model weights from DRS_MODEL_URL ..."
    New-Item -ItemType Directory -Force -Path (Join-Path $ScriptDir "models") | Out-Null
    try {
        Invoke-WebRequest -Uri $env:DRS_MODEL_URL -OutFile "$ModelFile.part" -UseBasicParsing
        Move-Item "$ModelFile.part" $ModelFile -Force
        Ok "Model weights downloaded."
    } catch {
        Remove-Item "$ModelFile.part" -ErrorAction SilentlyContinue
        WarnMsg "Download failed - see models\README.md."
    }
}

if (-not (Test-Path $ModelFile)) {
    WarnMsg "models\classifier.pt not found. The app will still start, but screening stays disabled until it's there. Copy the file into models\, set DRS_MODEL_URL in .env, or see models\README.md."
}

Ok "Setup complete."

# -- run ---------------------------------------------------------------------------------
if ($Args_.Count -eq 1 -and $Args_[0] -eq "setup") {
    # "setup" isn't a real `drscreen` subcommand  -  it means what it says here:
    # do the environment setup above, then stop.
    exit 0
} elseif ($Args_.Count -eq 0) {
    Write-Host ""
    Write-Host "  Open http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "  First time? Create your operator account from the sign-in page."
    Write-Host "  Stop the server with Ctrl+C."
    Write-Host ""
    & $VenvDrscreen web
} else {
    Info "Running: drscreen $($Args_ -join ' ')"
    & $VenvDrscreen @Args_
}
exit $LASTEXITCODE
