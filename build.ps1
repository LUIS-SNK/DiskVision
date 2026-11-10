param(
    [string]$Python = "python",
    [string]$InnoSetup,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$originalPath = $env:Path
Push-Location -LiteralPath $PSScriptRoot
try {
    $pythonExe = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
    # Limit native dependency discovery to Python, Qt and Windows.
    $env:Path = "$(Split-Path -Parent $pythonExe);$env:SystemRoot\System32;$env:SystemRoot"
    try {
        & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name DiskVision main.py
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar DiskVision.exe." }
    } finally {
        $env:Path = $originalPath
    }

    if ($Installer) {
        if (-not $InnoSetup) {
            $default = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
            if (Test-Path -LiteralPath $default) {
                $InnoSetup = $default
            } else {
                $InnoSetup = (Get-Command ISCC.exe -ErrorAction Stop).Source
            }
        }
        & $InnoSetup (Join-Path $PSScriptRoot "installer\DiskVision.iss")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
    }
} finally {
    Pop-Location
}
