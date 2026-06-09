$ErrorActionPreference = "Stop"

$androidDir = Join-Path $PSScriptRoot "android"
$sdkDir = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$jdkDir = Join-Path $env:LOCALAPPDATA "Programs\MicrosoftJDK\21.0.10\jdk-21.0.10+7"
$localPropsPath = Join-Path $androidDir "local.properties"
$keystorePropsPath = Join-Path $androidDir "keystore.properties"

if (-not (Test-Path $jdkDir)) {
    throw "Expected JDK not found at $jdkDir"
}

if (-not (Test-Path $sdkDir)) {
    throw "Expected Android SDK not found at $sdkDir"
}

$requiredVars = @(
    "CHATBOKS_ANDROID_KEYSTORE_PATH",
    "CHATBOKS_ANDROID_KEYSTORE_PASSWORD",
    "CHATBOKS_ANDROID_KEY_ALIAS",
    "CHATBOKS_ANDROID_KEY_PASSWORD"
)

$missing = $requiredVars | Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}

$keystorePath = $env:CHATBOKS_ANDROID_KEYSTORE_PATH
if (-not (Test-Path $keystorePath)) {
    throw "Keystore not found at $keystorePath"
}
$keystorePathForGradle = $keystorePath.Replace("\", "/")

$sdkDirEscaped = $sdkDir.Replace("\", "\\")
"sdk.dir=$sdkDirEscaped" | Set-Content -Path $localPropsPath -Encoding ascii

@"
storeFile=$keystorePathForGradle
storePassword=$($env:CHATBOKS_ANDROID_KEYSTORE_PASSWORD)
keyAlias=$($env:CHATBOKS_ANDROID_KEY_ALIAS)
keyPassword=$($env:CHATBOKS_ANDROID_KEY_PASSWORD)
"@ | Set-Content -Path $keystorePropsPath -Encoding ascii

$env:JAVA_HOME = $jdkDir
$env:PATH = "$jdkDir\bin;$env:PATH"
$env:ANDROID_HOME = $sdkDir
$env:ANDROID_SDK_ROOT = $sdkDir

Push-Location $androidDir
try {
    .\gradlew.bat assembleRelease
}
finally {
    Pop-Location
}
