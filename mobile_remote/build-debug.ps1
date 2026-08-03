$ErrorActionPreference = "Stop"

$androidDir = Join-Path $PSScriptRoot "android"
$sdkDir = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$jdkDir = Join-Path $env:LOCALAPPDATA "Programs\MicrosoftJDK\21.0.10\jdk-21.0.10+7"
$localPropsPath = Join-Path $androidDir "local.properties"

if (-not (Test-Path $jdkDir)) {
    $jdkRoot = Join-Path $env:LOCALAPPDATA "Programs\MicrosoftJDK"
    $jdkDir = Get-ChildItem -Path $jdkRoot -Directory -Recurse -Filter "jdk-21*" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $jdkDir -or -not (Test-Path $jdkDir)) {
    throw "Expected JDK 21 not found under $env:LOCALAPPDATA\Programs\MicrosoftJDK"
}

if (-not (Test-Path $sdkDir)) {
    throw "Expected Android SDK not found at $sdkDir"
}

$sdkDirEscaped = $sdkDir.Replace("\", "\\")
"sdk.dir=$sdkDirEscaped" | Set-Content -Path $localPropsPath -Encoding ascii

$env:JAVA_HOME = $jdkDir
$env:PATH = "$jdkDir\bin;$env:PATH"
$env:ANDROID_HOME = $sdkDir
$env:ANDROID_SDK_ROOT = $sdkDir
$appVersion = & (Join-Path $PSScriptRoot "resolve-version.ps1")

Push-Location $PSScriptRoot
try {
    npm run copy
}
finally {
    Pop-Location
}

$mobileVersionAsset = Join-Path $androidDir "app\src\main\assets\public\mobile-version.js"
"window.CHATBOKS_PACKAGED_VERSION = `"v$($appVersion.Name)`";" |
    Set-Content -Path $mobileVersionAsset -Encoding ascii

Push-Location $androidDir
try {
    .\gradlew.bat assembleDebug "-PchatboksVersionName=$($appVersion.Name)" "-PchatboksVersionCode=$($appVersion.Code)"
}
finally {
    Pop-Location
}
