# AGRISCAN backup for Windows (XAMPP). Same contents as backup.sh.
#
#   powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 E:\agriscan-backups
#
# Run from the backend folder. Reads the database settings from backend\.env.
# Restore instructions: docs\RESTORE.md
#
# To run it every night: Task Scheduler > Create Basic Task > Daily > Start a program,
#   Program:   powershell.exe
#   Arguments: -ExecutionPolicy Bypass -File "C:\path\to\agriscan\backend\scripts\backup.ps1" "E:\agriscan-backups"
#   Start in:  C:\path\to\agriscan\backend

param([string]$Dest = ".\backups")

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $PSScriptRoot
Set-Location $Backend

# --- read backend\.env -------------------------------------------------------------
$envVals = @{}
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envVals[$Matches[1]] = $Matches[2] }
    }
}
function Val($name, $default) { if ($envVals[$name]) { $envVals[$name] } else { $default } }

$DbHost = Val "AGRISCAN_DB_HOST" "127.0.0.1"
$DbPort = Val "AGRISCAN_DB_PORT" "3306"
$DbUser = Val "AGRISCAN_DB_USER" "agriscan"
$DbPass = Val "AGRISCAN_DB_PASSWORD" ""
$DbName = Val "AGRISCAN_DB_NAME" "agriscan"
$ImageRoot = Val "AGRISCAN_IMAGE_ROOT" ".\data\images"
$ModelRoot = Val "AGRISCAN_MODEL_ROOT" ".\ml\models"

$dump = "C:\xampp\mysql\bin\mysqldump.exe"
if (-not (Test-Path $dump)) { $dump = "mysqldump" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Out = Join-Path $Dest "agriscan-$Stamp"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Write-Host "Backing up to $Out"

Write-Host "  1/4 database"
# Password through the environment, not the command line, so it is not visible in the
# process list.
$env:MYSQL_PWD = $DbPass
& $dump --host=$DbHost --port=$DbPort --user=$DbUser --single-transaction `
        --routines --triggers --events --result-file="$Out\database.sql" $DbName
Remove-Item Env:\MYSQL_PWD
if ($LASTEXITCODE -ne 0) { throw "mysqldump failed. Is MySQL running in XAMPP?" }

Write-Host "  2/4 images"
if (Test-Path $ImageRoot) {
    Compress-Archive -Path $ImageRoot -DestinationPath "$Out\images.zip" -CompressionLevel Fastest
} else { Write-Host "     (no image directory at $ImageRoot, skipped)" }

Write-Host "  3/4 models"
if (Test-Path $ModelRoot) {
    Compress-Archive -Path $ModelRoot -DestinationPath "$Out\models.zip" -CompressionLevel Fastest
} else { Write-Host "     (no models yet, skipped)" }

Write-Host "  4/4 configuration"
# .env holds secrets. Keep the backup drive somewhere you would keep the laptop itself.
if (Test-Path ".env") { Copy-Item ".env" "$Out\env.backup" }

@"
AGRISCAN backup $Stamp
database:  $DbName @ ${DbHost}:$DbPort
images:    $ImageRoot
models:    $ModelRoot
host:      $env:COMPUTERNAME
"@ | Set-Content "$Out\MANIFEST.txt"

$size = "{0:N1} MB" -f ((Get-ChildItem $Out -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "Done. $size in $Out"
Write-Host "Check the dump is readable before trusting it: Get-Content $Out\database.sql -TotalCount 5"
