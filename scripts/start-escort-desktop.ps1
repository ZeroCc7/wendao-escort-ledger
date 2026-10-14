$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $localPythonw = Join-Path $repoRoot '.venv/Scripts/pythonw.exe'
    $pythonwExe = if (Test-Path -LiteralPath $localPythonw) { $localPythonw } else { 'pythonw' }
    & $pythonwExe -m desktop.escort_web_app
} finally {
    Pop-Location
}
