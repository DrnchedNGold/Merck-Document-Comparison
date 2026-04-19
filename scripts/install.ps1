Param(
  [switch]$Dev,
  [switch]$Help
)

if ($Help) {
  @"
Usage: .\scripts\install.ps1 [-Dev]

Creates .venv, installs the repo (pip install -e .).
-Dev also installs requirements-dev.txt (pytest, etc.).
"@ | Write-Output
  exit 0
}

$ErrorActionPreference = "Stop"

function Fail($msg) {
  Write-Error $msg
  exit 1
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Find-Python {
  $candidates = @("python3.13", "python3.12", "python")
  foreach ($c in $candidates) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Name }
  }
  return $null
}

$Py = Find-Python
if (-not $Py) {
  Fail @"
Python not found.

Install Python 3.12+ (recommended via winget), then re-run:
  winget install --id Python.Python.3.12 -e
"@
}

$verOk = & $Py -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
if ($LASTEXITCODE -ne 0) {
  Fail "Detected $Py but it is older than Python 3.12. Please install Python 3.12+."
}

if (-not (Test-Path ".venv")) {
  & $Py -m venv .venv
}

$VenvPy = Join-Path ".venv" "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
  Fail "Expected venv python at $VenvPy but it was not found."
}

& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -e .

if ($Dev) {
  & $VenvPy -m pip install -r requirements-dev.txt
}

& $VenvPy -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Warning @"
tkinter could not be imported.

The CLI will still work. Desktop GUI requires Tk/tkinter.
If you installed Python via winget/python.org and still see this, re-run the installer
and ensure Tcl/Tk is included.
"@
}

@"

Install complete.

Activate venv:
  .\.venv\Scripts\Activate.ps1

Run CLI (installed entrypoint):
  merck-compare --original a.docx --revised b.docx --output out.docx

Run CLI (module form; from repo root):
  $VenvPy -m engine.compare_cli --original a.docx --revised b.docx --output out.docx

Run Desktop GUI (Tk):
  $VenvPy -m desktop

Docs:
  docs\INSTALL.md
  docs\CLI-MERCK-COMPARE.md
"@ | Write-Output

