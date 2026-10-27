$ErrorActionPreference = "Stop"

$plugin = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "start-pet.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Mint Budgie.lnk"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
$shortcut.WorkingDirectory = $plugin
$shortcut.WindowStyle = 7
$shortcut.Description = "Mint Budgie desktop pet for DeepSeek Harness"
$shortcut.Save()

Write-Output $shortcutPath
