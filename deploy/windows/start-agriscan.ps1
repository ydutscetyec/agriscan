# Start AGRISCAN on a Windows laptop: website, analysis worker, and the HTTPS tunnel,
# each in its own window so you can see what each one is doing.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows\start-agriscan.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\windows\start-agriscan.ps1 -Tunnel named
#
# -Tunnel quick   (default) free https://<random>.trycloudflare.com address, new every start
# -Tunnel named   your own domain, after the one-time setup in DEPLOY.md
# -Tunnel none    website and worker only
#
# Before running: XAMPP Control Panel > MySQL > Start.

param([ValidateSet("quick", "named", "none")][string]$Tunnel = "quick")

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "No virtual environment at backend\.venv. See DEPLOY.md step 2." }
if (-not (Test-Path (Join-Path $Root "web\dist\index.html"))) {
    throw "No web build. Run: cd web; npm ci; npm run build"
}

Write-Host "Checking the server is ready..."
& $Python (Join-Path $Backend "serve.py") --check
if ($LASTEXITCODE -ne 0) { throw "Preflight failed. Fix the FAIL lines above, then run this again." }

Start-Process powershell -WorkingDirectory $Backend -ArgumentList @(
    "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AGRISCAN website'; & '$Python' serve.py")
Start-Process powershell -WorkingDirectory $Backend -ArgumentList @(
    "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AGRISCAN worker'; & '$Python' -m worker.run")

$port = 8080
if ($Tunnel -eq "quick") {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle='AGRISCAN tunnel'; cloudflared tunnel --url http://localhost:$port")
    Write-Host "Look in the 'AGRISCAN tunnel' window for the https://....trycloudflare.com address."
} elseif ($Tunnel -eq "named") {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AGRISCAN tunnel'; cloudflared tunnel run agriscan")
}
Write-Host "Started. Close a window to stop that part. The worker exits by itself if no model is in production yet; that is expected."
