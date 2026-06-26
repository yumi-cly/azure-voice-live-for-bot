param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Fill Azure settings before running the full demo."
}

if (-not (Test-Path $VenvPython)) {
    py -3 -m venv ".venv"
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

$uvicornArgs = @("app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

& $VenvPython -m uvicorn @uvicornArgs
