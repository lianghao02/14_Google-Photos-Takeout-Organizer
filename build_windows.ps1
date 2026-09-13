# PowerShell script to build Windows Portable onedir package using PyInstaller
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$TargetName = "Google-Photos-Takeout-Organizer-v1.1.0-Windows-x64"
$TargetDir = Join-Path $DistDir $TargetName
$ZipPath = Join-Path $DistDir "$TargetName.zip"
$ExeName = "Google Photos Takeout 整理工具.exe"

function Safe-RemoveDir($dirPath) {
    if (Test-Path $dirPath) {
        $tempEmpty = New-Item -ItemType Directory -Path "$env:TEMP\empty_del_$([guid]::NewGuid().ToString('N'))" -Force
        robocopy $tempEmpty.FullName $dirPath /MIR /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        Remove-Item $dirPath -Force -Recurse
        Remove-Item $tempEmpty.FullName -Force
    }
}

Write-Host "=== 1. 清理舊有打包暫存 ==="
Safe-RemoveDir $BuildDir
Safe-RemoveDir $TargetDir
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

Write-Host "=== 2. 執行 PyInstaller onedir 打包 ==="
$EntryScript = Join-Path $ProjectRoot "src\google_photos_takeout_organizer\gui.py"
$IconPath = Join-Path $ProjectRoot "src\google_photos_takeout_organizer\resources\app_icon.ico"
$ResDir = Join-Path $ProjectRoot "src\google_photos_takeout_organizer\resources"

pyinstaller `
    --noconfirm `
    --onedir `
    --windowed `
    --name "Google Photos Takeout 整理工具" `
    --icon "$IconPath" `
    --add-data "${ResDir};google_photos_takeout_organizer/resources" `
    --paths (Join-Path $ProjectRoot "src") `
    --collect-all "PIL" `
    --collect-all "pillow_heif" `
    --collect-all "PySide6" `
    --distpath $DistDir `
    $EntryScript

# PyInstaller creates $DistDir\"Google Photos Takeout 整理工具"
$RawOutDir = Join-Path $DistDir "Google Photos Takeout 整理工具"
if (Test-Path $RawOutDir) {
    Rename-Item -Path $RawOutDir -NewName $TargetName
}

$ExePath = Join-Path $TargetDir $ExeName
if (-not (Test-Path $ExePath)) {
    throw "打包失敗：找不到預期執行檔 $ExePath"
}

Write-Host "=== 3. 建立使用說明 ==="
$ReadmeLines = @(
    "Google 相簿 Takeout 整理工具 (v1.1.0 Windows x64 可攜版)",
    "===================================================",
    "",
    "【使用說明】",
    "1. 雙擊執行「Google Photos Takeout 整理工具.exe」。",
    "2. 點擊「選擇 ZIP」，選取您自 Google Takeout 下載的 ZIP 檔案（若有多個分卷，可全部選取或點擊「加入更多」）。",
    "3. 點擊「選擇」，指定要輸出存放整理後照片的資料夾。",
    "4. 點擊「開始整理」。",
    "5. 整理與驗證完成後，可直接點擊「開啟整理結果」查看依年月歸檔的照片。",
    "   若有拍攝日期衝突或中繼資料歧義的檔案，可點擊「開啟人工確認」進行檢視。",
    "",
    "【安全原則】",
    "本工具一律採複製（Copy-only）方式整理，絕不會移動、修改或刪除您的原始 Takeout ZIP 壓縮檔。"
)
$ReadmeContent = $ReadmeLines -join "`r`n"
$ReadmePath = Join-Path $TargetDir "使用說明.txt"
[System.IO.File]::WriteAllText($ReadmePath, $ReadmeContent, [System.Text.Encoding]::UTF8)

Write-Host "=== 4. 計算產物 SHA-256 Checksum ==="
$Hash = (Get-FileHash -Path $ExePath -Algorithm SHA256).Hash
Write-Host "產物主執行檔：$ExePath"
Write-Host "SHA-256：$Hash"

Write-Host "=== 5. 封裝為 Portable ZIP 發布包 ==="
tar.exe -a -c -f $ZipPath -C $DistDir $TargetName
$ZipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash
Write-Host "發布壓縮包：$ZipPath"
Write-Host "ZIP SHA-256：$ZipHash"

Write-Host "=== 打包完成！ ==="