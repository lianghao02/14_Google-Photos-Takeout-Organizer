[CmdletBinding()]
param([switch]$NoLaunch)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirementsFile = Join-Path $projectRoot 'requirements.txt'

function Show-LaunchError {
    param([string]$Message)

    $logPath = Join-Path ([System.IO.Path]::GetTempPath()) 'GooglePhotosTakeoutOrganizer-startup.log'
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n$Message" | Set-Content -LiteralPath $logPath -Encoding utf8
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, 'Google 相簿 Takeout 整理工具', [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Error) | Out-Null
}

function Test-RequiredModules {
    param([string]$PythonExe)
    & $PythonExe -c 'import PySide6, PIL, pillow_heif' 2>$null
    return $LASTEXITCODE -eq 0
}

function Find-Python313 {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3.13 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($pyLauncher.Source, '-3.13') }
    }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & $pythonCommand.Source -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($pythonCommand.Source) }
    }
    return $null
}

try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $pythonCommand = Find-Python313
        if (-not $pythonCommand) {
            Show-LaunchError '找不到 Python 3.13 以上版本。請先安裝 Python 3.13（64 位元）後，再重新雙擊 RUN.bat。'
            exit 1
        }
        Write-Host '[1/3] 首次啟動：正在建立專案 Python 環境…' -ForegroundColor Cyan
        $pythonArgs = @()
        if ($pythonCommand.Count -gt 1) {
            $pythonArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
        }
        & $pythonCommand[0] @pythonArgs -m venv $venvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) { throw '無法建立 .venv 虛擬環境。' }
    }

    if (-not (Test-RequiredModules -PythonExe $venvPython)) {
        if (-not (Test-Path -LiteralPath $requirementsFile)) { throw '找不到 requirements.txt。' }
        Write-Host '[2/3] 正在安裝必要套件，首次啟動可能需要幾分鐘…' -ForegroundColor Cyan
        & $venvPython -m pip install --disable-pip-version-check -r $requirementsFile
        if ($LASTEXITCODE -ne 0 -or -not (Test-RequiredModules -PythonExe $venvPython)) { throw '必要套件安裝失敗。請確認網路連線後重試。' }
    }

    if ($NoLaunch) {
        Write-Host '[3/3] 啟動環境檢查完成。' -ForegroundColor Green
        exit 0
    }

    Write-Host '[3/3] 正在啟動 Google 相簿 Takeout 整理工具…' -ForegroundColor Green
    $pythonwExe = Join-Path $venvDir 'Scripts\pythonw.exe'
    $guiPython = if (Test-Path -LiteralPath $pythonwExe) { $pythonwExe } else { $venvPython }
    $escapedSrc = (Join-Path $projectRoot 'src').Replace("'", "\\'")
    $bootstrap = "import sys; sys.path.insert(0, '$escapedSrc'); from google_photos_takeout_organizer.gui import main; main()"
    Start-Process -FilePath $guiPython -ArgumentList @('-c', $bootstrap) -WorkingDirectory $projectRoot -WindowStyle Hidden
} catch {
    Show-LaunchError "啟動器發生錯誤：$($_.Exception.Message)"
    exit 1
}
