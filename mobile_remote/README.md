# ChatBoks Remote Android Shell

This is a thin Capacitor shell for the secure desktop bridge in `remote_control.py`.

## Early Development Notice

This remote-control path is still early and experimental. Using it is your own responsibility. Even with the current
loopback, pairing, token, and private-network safeguards, this project is not presented as a production-grade remote
administration system.

If you enable phone access to a desktop session that can read, write, or execute on your machine, you are responsible
for how that access is exposed, which devices can reach it, and what damage a mistake or compromise could cause.

Security model:

- The desktop bridge stays loopback-only on the PC.
- The Android app pairs with a one-time desktop code and receives a short-lived session token.
- The intended network path is a private URL such as a Tailscale Serve address, not a public internet endpoint.

## Desktop side

Start the bridge on the desktop:

```bash
python remote_control.py chatboks
```

The desktop bridge prints:

- a one-time pairing code
- the session-token lifetime
- an admin token only if you explicitly pass `--show-admin-token`

Recommended remote access path:

```bash
tailscale serve --bg localhost:8765
```

Then use the private `https://<device>.<tailnet>.ts.net` URL inside the Android app and pair with the one-time code.

## Android build

From this directory:

```bash
npm install
npx cap add android
npx cap sync android
npx cap open android
```

Build the APK from Android Studio after the project opens.

For this desktop, a local helper script is also available:

```powershell
./build-debug.ps1
```

That script expects:

- Android CLI / SDK under `%LOCALAPPDATA%\Android\Sdk`
- Microsoft Build of OpenJDK 21 under `%LOCALAPPDATA%\Programs\MicrosoftJDK\21.0.10\jdk-21.0.10+7`

It writes `android/local.properties` locally, sets `JAVA_HOME`, and runs `gradlew assembleDebug`.

To install that debug APK onto a USB-connected Android device:

```powershell
./install-debug.ps1
```

That script rebuilds the debug APK, checks `adb`, and installs with `adb install -r`.

For a signed release build, set these environment variables first:

```powershell
$env:CHATBOKS_ANDROID_KEYSTORE_PATH="C:\path\to\chatboks-release.jks"
$env:CHATBOKS_ANDROID_KEYSTORE_PASSWORD="..."
$env:CHATBOKS_ANDROID_KEY_ALIAS="chatboks"
$env:CHATBOKS_ANDROID_KEY_PASSWORD="..."
./build-release.ps1
```

`build-release.ps1` writes `android/keystore.properties` locally, which is ignored by git.

## Notes

- The bridge only allows API origins from the app container (`capacitor://localhost`, `http://localhost`, `https://localhost`).
- `allowNavigation` includes `*.ts.net` so the Android webview can talk to private Tailscale-hosted bridge URLs.
- Do not point the app at a public Funnel URL or any directly exposed public port.
