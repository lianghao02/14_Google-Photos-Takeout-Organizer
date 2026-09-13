[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Show-LaunchError {
    param([string]$Message)

    $logPath = Join-Path ([System.IO.Path]::GetTempPath()) 'GooglePhotosTakeoutOrganizer-startup.log'
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n$Message" | Set-Content -LiteralPath $logPath -Encoding utf8
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        $Message,
        'Google 相簿 Takeout 整理工具',
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
}

try {
    $pythonExe = $null
    if (Test-Path -LiteralPath $venvPython) {
        $pythonExe = $venvPython
    } else {
        $systemCmd = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($systemCmd) {
            $pythonExe = $systemCmd.Source
        }
    }

    if (-not $pythonExe) {
        Show-LaunchError '找不到可執行的 Python 環境。請確認已安裝 Python 3.13+，或建立專案的 .venv 後再啟動。'
        exit 1
    }

    & $pythonExe -c 'import PySide6, PIL, pillow_heif' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Show-LaunchError '缺少必要 Python 套件。請在專案資料夾執行：python -m pip install -r requirements.txt'
        exit 1
    }

    $pythonwExe = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
    $guiExe = if (Test-Path -LiteralPath $pythonwExe) { $pythonwExe } else { $pythonExe }
    $srcPath = (Join-Path $projectRoot 'src').Replace('\', '\\').Replace("'", "\'")
    $bootstrap = "import sys; sys.path.insert(0, '$srcPath'); from google_photos_takeout_organizer.gui import main; main()"
    & $guiExe -c $bootstrap
    if ($LASTEXITCODE -ne 0) {
        Show-LaunchError "程式啟動失敗（結束代碼：$LASTEXITCODE）。詳細資訊已寫入：$([System.IO.Path]::GetTempPath())GooglePhotosTakeoutOrganizer-startup.log"
        exit $LASTEXITCODE
    }
} catch {
    Show-LaunchError "啟動器發生錯誤：$($_.Exception.Message)"
    exit 1
}
