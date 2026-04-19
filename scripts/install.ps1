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

function Test-PythonCandidate($exe, $args) {
  $null = & $exe @args -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" 2>$null
  return ($LASTEXITCODE -eq 0)
}

function Find-Python {
  # Prefer the Windows Python launcher (py.exe) when present.
  $candidates = @(
    @{ Exe = "py"; Args = @("-3.13") },
    @{ Exe = "py"; Args = @("-3.12") },
    @{ Exe = "python"; Args = @() },
    @{ Exe = "python3.13"; Args = @() },
    @{ Exe = "python3.12"; Args = @() }
  )

  foreach ($c in $candidates) {
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }

    # Avoid WindowsApps aliases/stubs (common for python3.x on Windows).
    if ($cmd.Source -like "*\WindowsApps\*") { continue }

    if (Test-PythonCandidate $cmd.Source $c.Args) {
      return @{ Exe = $cmd.Source; Args = $c.Args }
    }
  }

  # Fall back to trying WindowsApps commands if they are the only thing available.
  foreach ($c in $candidates) {
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    if (Test-PythonCandidate $cmd.Source $c.Args) {
      return @{ Exe = $cmd.Source; Args = $c.Args }
    }
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

$PyExe = $Py.Exe
$PyArgs = $Py.Args

if (-not (Test-Path ".venv")) {
  & $PyExe @PyArgs -m venv .venv
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

