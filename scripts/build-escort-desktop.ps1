$repoRoot = Split-Path -Parent $PSScriptRoot
$uiPath = Join-Path $repoRoot 'desktop/ui'
$iconPath = Join-Path $uiPath 'art/mini-program-logo.ico'
$localPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
$pythonExe = if (Test-Path -LiteralPath $localPython) { $localPython } else { 'python' }
Push-Location $repoRoot
try {
    & $pythonExe -c "import PyInstaller, webview" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw '打包需要 PyInstaller 和 pywebview。先运行：python -m pip install pyinstaller pywebview'
    }
    & $pythonExe -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name '押镖账本' `
        --icon $iconPath `
        --paths $repoRoot `
        --add-data "${uiPath};ui" `
        desktop/escort_web_app.py
    if ($LASTEXITCODE -ne 0) {
        throw '押镖账本打包失败，请查看上方 PyInstaller 错误。'
    }
} finally {
    Pop-Location
}
