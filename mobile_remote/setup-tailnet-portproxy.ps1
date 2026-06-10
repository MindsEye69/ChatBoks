$ErrorActionPreference = "Stop"

$listenAddress = "100.94.205.69"
$listenPort = "8765"
$connectAddress = "127.0.0.1"
$connectPort = "8765"
$ruleName = "ChatBoks Remote Tailnet"

Write-Host "Configuring ChatBoks Remote tailnet fallback..."
Write-Host "Forwarding http://$listenAddress`:$listenPort -> http://$connectAddress`:$connectPort"

netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$listenPort 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenaddress=$listenAddress listenport=$listenPort connectaddress=$connectAddress connectport=$connectPort

netsh advfirewall firewall delete rule name="$ruleName" 2>$null | Out-Null
netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localip=$listenAddress localport=$listenPort remoteip=100.64.0.0/10

Write-Host ""
Write-Host "Current portproxy rules:"
netsh interface portproxy show v4tov4
Write-Host ""
Write-Host "Done. You can close this window."
Read-Host "Press Enter to close"
