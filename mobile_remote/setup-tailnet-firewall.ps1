$ErrorActionPreference = "Stop"

$listenAddress = "100.94.205.69"
$listenPort = "8765"
$ruleName = "ChatBoks Remote Tailnet"

Write-Host "Configuring Windows Firewall for ChatBoks Remote tailnet fallback..."
Write-Host "Allowing TCP $listenAddress`:$listenPort from Tailscale CGNAT peers only."

netsh advfirewall firewall delete rule name="$ruleName" 2>$null | Out-Null
netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localip=$listenAddress localport=$listenPort remoteip=100.64.0.0/10

Write-Host ""
Write-Host "Firewall rule:"
netsh advfirewall firewall show rule name="$ruleName"
Write-Host ""
Write-Host "Done. Try Pair again in ChatBoks Remote."
Read-Host "Press Enter to close"
