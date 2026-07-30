$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing virtual environment. Run python -m pip install -r requirements.txt first."
}

& $python -m pip install -r requirements-build.txt

# Bundle only mobile_remote/www — the sole path read at runtime
# (remote_control.WORKBENCH_WWW_ROOT). The rest of mobile_remote is the
# Capacitor build tree: node_modules and android/ add ~65 MB that --onefile
# re-extracts to a temp dir on every launch. The destination path is kept
# identical so WORKBENCH_WWW_ROOT resolves unchanged inside the bundle.
& $python -m PyInstaller --noconfirm --clean --noconsole --onefile --name ChatBoks --add-data "mobile_remote/www;mobile_remote/www" desktop_app.py
