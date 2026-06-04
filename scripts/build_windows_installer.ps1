param(
    [string]$EnvName = $(if ($env:TTN_CONDA_ENV) { $env:TTN_CONDA_ENV } else { "ttn-env" }),

    [string]$AppVersion = "",

    [string]$IsccPath = "",

    [switch]$SkipExeBuild,
    [switch]$SkipExeSmoke,
    [switch]$InstallMissingPyInstaller
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Error "Windows installer packaging must be run on Windows."
}

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExeBuildScript = Join-Path $ProjectRoot "scripts\build_windows_exe.ps1"
$InstallerSpec = Join-Path $ProjectRoot "scripts\installer\thucthengay_inno.iss"
$BundleDir = Join-Path $ProjectRoot "dist\ThucTheNgay"
$BundleExe = Join-Path $BundleDir "ThucTheNgay.exe"
$InstallerOutputDir = Join-Path $ProjectRoot "dist\installer"

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda was not found in PATH. Open an Anaconda/Miniconda PowerShell prompt or add conda to PATH."
}

Set-Location $ProjectRoot

if (-not $SkipExeBuild) {
    $exeArgs = @("-Mode", "onedir", "-EnvName", $EnvName)
    if ($SkipExeSmoke) {
        $exeArgs += "-SkipSmoke"
    }
    if ($InstallMissingPyInstaller) {
        $exeArgs += "-InstallMissingTools"
    }
    & $ExeBuildScript @exeArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Executable build failed."
    }
}

if (-not (Test-Path $BundleExe)) {
    Write-Error "Installer source was not found. Expected executable: $BundleExe"
}

if (-not $AppVersion) {
    $AppVersion = (& conda run -n $EnvName python -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); print(data['project']['version'])").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $AppVersion) {
        Write-Error "Could not read project version from pyproject.toml."
    }
}

$ResolvedIscc = $null
if ($IsccPath) {
    if (-not (Test-Path $IsccPath)) {
        Write-Error "ISCC.exe was not found at: $IsccPath"
    }
    $ResolvedIscc = (Resolve-Path $IsccPath).Path
} else {
    $IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($IsccCommand) {
        $ResolvedIscc = $IsccCommand.Source
    } else {
        $Candidates = @()
        if (${env:ProgramFiles(x86)}) {
            $Candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        }
        if ($env:ProgramFiles) {
            $Candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
        }
        foreach ($Candidate in $Candidates) {
            if ($Candidate -and (Test-Path $Candidate)) {
                $ResolvedIscc = $Candidate
                break
            }
        }
    }
}

if (-not $ResolvedIscc) {
    Write-Error "ISCC.exe was not found. Install Inno Setup 6 and rerun this script, or pass -IsccPath."
}

New-Item -ItemType Directory -Force -Path $InstallerOutputDir | Out-Null

& $ResolvedIscc `
    "/DAppVersion=$AppVersion" `
    "/DSourceDir=$BundleDir" `
    "/DOutputDir=$InstallerOutputDir" `
    $InstallerSpec

if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup build failed."
}

$InstallerExe = Join-Path $InstallerOutputDir "ThucTheNgay-Setup-$AppVersion.exe"
if (-not (Test-Path $InstallerExe)) {
    Write-Error "Installer build finished but output was not found: $InstallerExe"
}

Write-Host "Installer ready: $InstallerExe"
