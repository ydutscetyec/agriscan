# AGRISCAN -- pull the latest code and apply it.
#
#   powershell -ExecutionPolicy Bypass -File update.ps1
#
# Replaces the sequence of pull / build / seed commands that has to be run in the
# right order after every change. Safe to run repeatedly; does nothing if there is
# nothing new.
#
# It force-syncs to origin/main rather than merging, because a plain `git pull` has
# twice now reported success while leaving the working tree on older code. Everything
# the project actually keeps -- backend\.env, backend\data, backend\logs, the virtual
# environment, node_modules, the database -- is gitignored and is not touched.
#
# It REFUSES to run if you have uncommitted changes to tracked files, so your own
# edits are never silently discarded.

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Note($text) { Write-Host "    $text" -ForegroundColor DarkGray }

$python = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "No virtual environment at backend\.venv" -ForegroundColor Red
    Write-Host "Create it first:" -ForegroundColor Red
    Write-Host "    cd backend; python -m venv .venv; " +
               ".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

# --- 1. refuse to clobber your own work --------------------------------------
Step 'Checking for local changes'
$dirty = git status --porcelain --untracked-files=no
if ($dirty) {
    Write-Host "You have uncommitted changes to tracked files:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Write-Host "`nCommit or stash them first. Nothing was changed." -ForegroundColor Yellow
    exit 1
}
Note 'working tree clean'

# --- 2. sync to origin/main --------------------------------------------------
Step 'Fetching'
$before = git rev-parse HEAD
git fetch origin --quiet
git checkout --quiet main 2>$null
git reset --hard --quiet origin/main
$after = git rev-parse HEAD

if ($before -eq $after) {
    Note 'already up to date'
} else {
    Note "$($before.Substring(0,7)) -> $($after.Substring(0,7))"
    git --no-pager log --oneline "$before..$after"
}
$changed = git --no-pager diff --name-only $before $after

# --- 3. rebuild the frontend if it changed -----------------------------------
Step 'Frontend'
if ($before -eq $after -and (Test-Path 'web\dist\index.html')) {
    Note 'no changes, existing build kept'
} elseif ($changed -match '^web/') {
    Push-Location web
    if (-not (Test-Path 'node_modules')) { Note 'installing dependencies'; npm ci }
    npm run build
    Pop-Location
    Note 'rebuilt -- hard-reload the browser with Ctrl+F5'
} else {
    Note 'no frontend changes'
}

# --- 4. database: schema, taxonomy, knowledge base ---------------------------
Step 'Database'
Push-Location backend
& $python -m migrations.run_migrations

$csv = 'scripts\conditions_modelA_v2.csv'
if (Test-Path $csv) { & $python -m scripts.import_conditions $csv }

& $python -m scripts.seed_knowledge
& $python -m scripts.load_knowledge_drafts
Pop-Location

# --- 5. what the system thinks of itself -------------------------------------
Step 'Preflight'
Push-Location backend
& $python serve.py --check
Pop-Location

Write-Host "`nDone. Restart the website and worker to pick up backend changes." -ForegroundColor Green
