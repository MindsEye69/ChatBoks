@echo off
cd /d "%~dp0"
set "PATH=C:\Users\R\AppData\Roaming\npm;C:\Users\R\.local\bin;C:\Users\R\AppData\Local\Programs\Ollama;C:\Users\R\AppData\Local\Android\Sdk\platform-tools;C:\Users\R\AppData\Local\Android\Sdk\cmdline-tools\latest\bin;%PATH%"
set "ANDROID_HOME=C:\Users\R\AppData\Local\Android\Sdk"
set "ANDROID_SDK_ROOT=C:\Users\R\AppData\Local\Android\Sdk"
".venv\Scripts\python.exe" orchestrator.py --config config.yaml chatboks --tui
