$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python launcher py.exe is required to resolve the shared ChatBoks version."
}

Push-Location $repoRoot
try {
    $json = & $python.Source -c "import json; from version import __version__, android_version_code; print(json.dumps({'name': __version__, 'code': android_version_code(__version__)}))"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not resolve the shared ChatBoks version."
    }
}
finally {
    Pop-Location
}

$version = $json | ConvertFrom-Json
[PSCustomObject]@{
    Name = [string]$version.name
    Code = [int]$version.code
}
