$ErrorActionPreference = "Stop"

$sdkDir = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$adbPath = Join-Path $sdkDir "platform-tools\adb.exe"
$apkPath = Join-Path $PSScriptRoot "android\app\build\outputs\apk\debug\app-debug.apk"

if (-not (Test-Path $adbPath)) {
    throw "adb not found at $adbPath"
}

& (Join-Path $PSScriptRoot "build-debug.ps1")

$adbOutput = & $adbPath devices
$deviceLines = $adbOutput | Select-Object -Skip 1 | Where-Object { $_.Trim() }
if ($deviceLines.Count -eq 0) {
    throw "No Android devices detected by adb. Connect a device with USB debugging enabled and authorize this PC."
}

& $adbPath install -r $apkPath
