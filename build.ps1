param(
    [string]$DistPath = (Join-Path $PSScriptRoot "dist"),
    [string]$WorkPath = (Join-Path $PSScriptRoot "build")
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run: uv venv --python 3.12 .venv; uv pip install --python .venv\Scripts\python.exe -r requirements-desktop.txt"
}

# Keep tools on the caller's PATH from supplying DLLs to the bundle.
$originalPath = $env:Path
try {
    $env:Path = (Split-Path -Parent $python), [Environment]::SystemDirectory, $env:SystemRoot -join ";"
    & $python -m PyInstaller (Join-Path $root "emit_desktop.spec") --noconfirm --clean --distpath $DistPath --workpath $WorkPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
} finally {
    $env:Path = $originalPath
}

Write-Host "Built: $(Join-Path $DistPath 'EMITDesktop\EMITDesktop.exe')"
