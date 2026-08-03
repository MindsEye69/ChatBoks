param(
    [string]$CertificateThumbprint = "",
    [switch]$InstallBuildDependencies,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing virtual environment. Run python -m pip install -r requirements.txt first."
}

if ($InstallBuildDependencies) {
    & $python -m pip install --requirement requirements-build.txt
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing. Re-run with -InstallBuildDependencies after reviewing requirements-build.txt."
}

if ($RequireSignature -and -not $CertificateThumbprint) {
    throw "-RequireSignature needs -CertificateThumbprint for a trusted Authenticode certificate."
}

# Bundle only mobile_remote/www - the sole path read at runtime
# (remote_control.WORKBENCH_WWW_ROOT). The rest of mobile_remote is the
# Capacitor build tree: node_modules and android/ add ~65 MB that --onefile
# re-extracts to a temp dir on every launch. The destination path is kept
# identical so WORKBENCH_WWW_ROOT resolves unchanged inside the bundle.
$versionStamp = Join-Path $PSScriptRoot "chatboks-version.txt"
try {
    $version = & $python -c "from version import __version__; print(__version__)"
    Set-Content -LiteralPath $versionStamp -Value $version.Trim() -Encoding Ascii -NoNewline
    & $python -m PyInstaller --noconfirm --clean --noconsole --noupx --onefile --name ChatBoks `
        --version-file "packaging/windows-version-info.txt" `
        --add-data "mobile_remote/www;mobile_remote/www" `
        --add-data "chatboks-version.txt;." `
        desktop_app.py
}
finally {
    Remove-Item -LiteralPath $versionStamp -Force -ErrorAction SilentlyContinue
}

$exe = Join-Path $PSScriptRoot "dist\ChatBoks.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Build completed without producing dist\ChatBoks.exe."
}

if ($CertificateThumbprint) {
    $signTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $signTool) {
        throw "signtool.exe is required for Authenticode signing. Install the Windows SDK first."
    }
    & $signTool.Source sign /sha1 $CertificateThumbprint /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $exe
    if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
}

$signature = Get-AuthenticodeSignature -LiteralPath $exe
if ($RequireSignature -and $signature.Status -ne "Valid") {
    throw "The executable is not signed with a valid trusted certificate."
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $exe
Set-Content -LiteralPath "$exe.sha256" -Value ("{0}  {1}" -f $hash.Hash, (Split-Path -Leaf $exe)) -Encoding ascii

[PSCustomObject]@{
    Executable = $exe
    Sha256 = $hash.Hash
    Signature = $signature.Status
}
