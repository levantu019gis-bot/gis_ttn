param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir",

    [string]$EnvName = $(if ($env:TTN_CONDA_ENV) { $env:TTN_CONDA_ENV } else { "ttn-env" }),

    [switch]$InstallMissingTools,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Error "Windows .exe packaging must be run on Windows. PyInstaller cannot cross-compile a Windows executable from Linux."
}

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SpecPath = Join-Path $ProjectRoot "scripts\pyinstaller\thucthengay_windows.spec"

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda was not found in PATH. Open an Anaconda/Miniconda PowerShell prompt or add conda to PATH."
}

Set-Location $ProjectRoot

$EnvListJson = (& conda env list --json)
if ($LASTEXITCODE -ne 0 -or -not $EnvListJson) {
    Write-Error "Could not inspect conda environments."
}

$EnvList = $EnvListJson | ConvertFrom-Json
$CondaPrefix = $EnvList.envs |
    Where-Object { (Split-Path -Leaf $_) -eq $EnvName } |
    Select-Object -First 1

if (-not $CondaPrefix) {
    Write-Error "Could not find conda environment '$EnvName'. Run: conda env create -f environment.yml"
}

& conda run -n $EnvName python -c "import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    if (-not $InstallMissingTools) {
        Write-Error "PyInstaller is not installed in '$EnvName'. Run: conda install -n $EnvName -c conda-forge pyinstaller"
    }
    & conda install -y -n $EnvName -c conda-forge pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install PyInstaller into '$EnvName'."
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:UV_PROJECT_ENVIRONMENT = $CondaPrefix
$env:TTN_PYINSTALLER_ONEFILE = if ($Mode -eq "onefile") { "1" } else { "0" }

$ProjShare = Join-Path $CondaPrefix "Library\share\proj"
$GdalShare = Join-Path $CondaPrefix "Library\share\gdal"
if (Test-Path $ProjShare) {
    $env:PROJ_LIB = $ProjShare
    $env:PROJ_DATA = $ProjShare
}
if (Test-Path $GdalShare) {
    $env:GDAL_DATA = $GdalShare
}

$DistPath = Join-Path $ProjectRoot "dist"
$WorkPath = Join-Path $ProjectRoot "build\pyinstaller"

& conda run -n $EnvName python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistPath `
    --workpath $WorkPath `
    $SpecPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
}

$ExePath = if ($Mode -eq "onefile") {
    Join-Path $DistPath "ThucTheNgay.exe"
} else {
    Join-Path $DistPath "ThucTheNgay\ThucTheNgay.exe"
}

if (-not (Test-Path $ExePath)) {
    Write-Error "Build finished but executable was not found: $ExePath"
}

if (-not $SkipSmoke) {
    & $ExePath --smoke
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Packaged executable smoke check failed."
    }
}

Write-Host "Packaged executable ready: $ExePath"
