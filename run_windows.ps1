param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvName = if ($env:TTN_CONDA_ENV) { $env:TTN_CONDA_ENV } else { "ttn-env" }

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda was not found in PATH. Open an Anaconda/Miniconda PowerShell prompt or add conda to PATH."
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

$CondaPrefix = (conda run -n $EnvName python -c "import os; print(os.environ['CONDA_PREFIX'])").Trim()
$env:PROJ_LIB = Join-Path $CondaPrefix "Library\share\proj"
$env:PROJ_DATA = $env:PROJ_LIB

conda run -n $EnvName python -m thucthengay @AppArgs
