$ErrorActionPreference = "SilentlyContinue"

$plugin = Split-Path -Parent $PSScriptRoot
$state = Join-Path $PSScriptRoot "state.json"
$position = Join-Path $PSScriptRoot "position.json"
$settings = Join-Path $PSScriptRoot "settings.json"
$sprite = Join-Path $plugin "assets\spritesheet.png"
$script = Join-Path $PSScriptRoot "pet-window.pyw"
$bundledExe = $null
$versionedExe = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "mint-budgie-*.exe" -File -ErrorAction SilentlyContinue |
  ForEach-Object {
    $versionText = $_.BaseName.Substring("mint-budgie-".Length)
    try {
      [pscustomobject]@{ Path = $_.FullName; Version = [version]$versionText }
    } catch {
    }
  } |
  Sort-Object Version -Descending |
  Select-Object -First 1
if ($versionedExe) {
  $bundledExe = $versionedExe.Path
} else {
  $legacyExe = Join-Path $PSScriptRoot "mint-budgie.exe"
  if (Test-Path $legacyExe) {
    $bundledExe = $legacyExe
  }
}
$pidFile = Join-Path $PSScriptRoot "pet.pid"
$dshPidFile = Join-Path $PSScriptRoot "dsh.pid"
$hiddenFlag = Join-Path $PSScriptRoot "hidden.flag"

if (-not (Test-Path $sprite) -or (-not (Test-Path $script) -and -not $bundledExe)) {
  exit 1
}

if (Test-Path $hiddenFlag) {
  Remove-Item -LiteralPath $hiddenFlag -Force -ErrorAction SilentlyContinue
}

if (Test-Path $pidFile) {
  $oldPid = [int](Get-Content $pidFile -Raw).Trim()
  if ($oldPid -gt 0) {
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
  }
}

$dshPid = $null
if (Test-Path $dshPidFile) {
  $saved = (Get-Content $dshPidFile -Raw).Trim()
  if ($saved -match '^\d+$' -and (Get-Process -Id ([int]$saved) -ErrorAction SilentlyContinue)) {
    $dshPid = [int]$saved
  }
}
if (-not $dshPid) {
  for ($attempt = 0; $attempt -lt 20 -and -not $dshPid; $attempt++) {
    $dsh = Get-Process -Name "DeepSeek Harness" -ErrorAction SilentlyContinue |
      Where-Object { $_.MainWindowHandle -ne 0 } |
      Select-Object -First 1
    if ($dsh) { $dshPid = $dsh.Id; break }
    Start-Sleep -Milliseconds 500
  }
}
if ($dshPid) {
  Set-Content -LiteralPath $dshPidFile -Value $dshPid -Encoding ascii
}

$arguments = @(
  "--sprite", $sprite,
  "--state", $state,
  "--position", $position,
  "--settings", $settings,
  "--parent-pid", "0",
  "--anchor-pid", $(if ($dshPid) { [string]$dshPid } else { "0" })
)
if ($bundledExe) {
  $executable = $bundledExe
} else {
  $python = $null
  foreach ($candidate in @($env:DSH_PET_PYTHON, "pyw.exe", "pythonw.exe", "py.exe", "python.exe")) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
      $python = $command.Source
      break
    }
  }
  if (-not $python) { exit 2 }
  $executable = $python
  $arguments = @($script) + $arguments
}
$p = Start-Process -FilePath $executable -ArgumentList $arguments -PassThru -WindowStyle Hidden -WorkingDirectory $PSScriptRoot
if (-not $p) { exit 3 }
$deadline = (Get-Date).AddSeconds(5)
$petPid = $p.Id
while ((Get-Date) -lt $deadline) {
  $running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.ProcessId -ne $p.Id -and
      (
        $_.CommandLine -like "*$script*" -or
        $_.ExecutablePath -eq $bundledExe
      )
    } |
    Select-Object -First 1
  if ($running) {
    $petPid = $running.ProcessId
    break
  }
  Start-Sleep -Milliseconds 200
}
Set-Content -LiteralPath $pidFile -Value $petPid -Encoding ascii
