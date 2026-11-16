# Deploying AGRISCAN

Two ways to put AGRISCAN on the internet. **Use A** unless you have a reason not to.

| | A. Laptop + Cloudflare Tunnel | B. Linux VPS + Caddy |
|---|---|---|
| Cost | Free (a domain is optional, about ₱600/year) | ₱300–₱1,200/month |
| HTTPS (camera works) | Yes | Yes |
| Works behind PLDT/Globe CGNAT | Yes, no port forwarding | Not relevant, VPS has a public IP |
| Photos and database live on | Your laptop | Someone else's server |
| Runs YOLO | On your laptop's CPU or GPU | Needs a 2 GB+ RAM plan for torch |
| Weak point | Laptop must stay on and online during field work | Monthly bill; uploads to a datacentre |

Why HTTPS matters: browsers only give a page the camera, GPS and screen wake lock over
HTTPS. Over plain `http://` the drone phone cannot take a single photo.

Why the phone works offline anyway: the field client and the drone camera queue
photos on the phone and upload when the connection returns. A tunnel dropping during a
flight loses nothing.

---

## A. Windows laptop + Cloudflare Tunnel

### 1. One-time: prepare the laptop

- **Power:** Settings > System > Power > *When plugged in, put my device to sleep* >
  **Never**. A sleeping laptop is an offline website.
- **XAMPP:** start MySQL. Optional: in XAMPP Control Panel tick the *Service* box next to
  MySQL so it starts with Windows.
- **cloudflared:** open PowerShell and run
  ```powershell
  winget install --id Cloudflare.cloudflared
  ```
  Close and reopen PowerShell, then check `cloudflared --version`.

### 2. One-time: install AGRISCAN

Extract `agriscan-p21.zip`, then copy your existing `backend\.env` into the new
`backend` folder. In PowerShell from the project folder:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m migrations.run_migrations      # applies 010_deployment.sql
python -m scripts.seed                   # taxonomy; safe to re-run
python -m scripts.create_admin           # your real admin account, password typed in
cd ..\web
npm ci
npm run build                            # creates web\dist, which serve.py serves
```

### 3. One-time: production settings in `backend\.env`

```ini
AGRISCAN_ENV=production
AGRISCAN_PROXY_HOPS=1
AGRISCAN_SECRET_KEY=<new value, see below>
```

Generate a **new** secret. The old one has been inside a zip you sent around:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Changing it signs everyone out once. That is the point.

Then check:

```powershell
cd backend
.venv\Scripts\python serve.py --check
```

Every line must be `ok` or `warn`. Typical `FAIL`s and the fix:

| FAIL | Fix |
|---|---|
| Demo accounts still use the published demo password | Users page > Deactivate each DEMO account |
| No real (non-demo) administrator | `python -m scripts.create_admin` |
| Migrations not applied | `python -m migrations.run_migrations` |
| No web build | `cd web`, `npm run build` |
| Database not reachable | Start MySQL in XAMPP; check `AGRISCAN_DB_*` |

### 4. Every time: start it

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\start-agriscan.ps1
```

Three windows open: **website**, **worker**, **tunnel**. The tunnel window prints an
address like `https://quiet-river-abc.trycloudflare.com`. That is the site. Open it on a
phone over mobile data to confirm.

Until a trained model is registered, the worker window says *no model in production*
and stops. That is correct: uploads still work and wait in the queue, and the dashboard
banner says so.

### 5. Permanent address (when you have a domain)

The quick address changes **every** start. Fine for testing, not for farmers who have
added the app to their home screen. With a domain on Cloudflare (free plan):

```powershell
cloudflared tunnel login                       # browser opens, pick your domain
cloudflared tunnel create agriscan             # prints a tunnel ID, writes a .json
cloudflared tunnel route dns agriscan agriscan.yourdomain.com
```

Copy `deploy\cloudflared\config.example.yml` to `C:\Users\<you>\.cloudflared\config.yml`,
put in your tunnel ID and hostname, then start with:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\start-agriscan.ps1 -Tunnel named
```

---

## B. Linux VPS + Caddy

Ubuntu 24.04, 2 GB RAM or more if the worker runs YOLO there.

```bash
sudo apt install -y mariadb-server python3-venv nodejs npm caddy
sudo useradd -r -m -d /opt/agriscan agriscan
# copy the project to /opt/agriscan, backend/.env included, owned by agriscan
cd /opt/agriscan/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m migrations.run_migrations && .venv/bin/python -m scripts.seed
.venv/bin/python -m scripts.create_admin
cd ../web && npm ci && npm run build
```

Same `.env` settings as A step 3. Point the domain's A record at the VPS, then:

```bash
sudo cp deploy/linux/Caddyfile /etc/caddy/Caddyfile        # edit the hostname first
sudo cp deploy/linux/agriscan-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now agriscan-web agriscan-worker
sudo systemctl reload caddy
```

---

## Updating to a new version

```powershell
# stop the three windows, extract the new package over the old one, keep backend\.env
cd backend; .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m migrations.run_migrations
cd ..\web; npm ci; npm run build
# start again
```

Open tabs reload themselves once onto the new version. Nobody has to clear a cache.

## When a model is trained

```powershell
cd backend
.venv\Scripts\pip install -r requirements-ml.txt
.venv\Scripts\python -m scripts.register_model --weights path\to\best.pt `
    --name AGRISCAN-YOLO26n-cls-v1 --architecture YOLO26n-cls `
    --dataset-version gdrive-2026-10-19 --mode ground --production `
    --write-missing missing_conditions.csv
```

Your 43 training folders are named like *Leaf Folder* and *Healthy Rice plant*; the
taxonomy has codes like `healthy`. The worker drops any class that is not a condition
code, so `register_model` refuses to promote until they match. Either rename the
folders to codes and retrain, or fill in `missing_conditions.csv` (common name and
category for each) and run `python -m scripts.import_conditions missing_conditions.csv`.

Then set `AGRISCAN_DETECTOR_IMPL=yolo` in `.env` and restart the worker.

## Backups

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\backup.ps1 E:\agriscan-backups
```

Database, photos, models and `.env`. The script header shows how to schedule it nightly
in Task Scheduler. Restore steps: `docs\RESTORE.md`.

## Where to look when something is wrong

| Symptom | Look at |
|---|---|
| Blank or error page | F12 > Console, or the *Copy details* button on the error screen |
| API errors | `backend\logs\agriscan.log` (every API request is logged with its status) |
| Photos never analysed | The worker window; the dashboard banner says how long they have waited |
| Phone cannot open the camera | The address must start with `https://` |
| Everyone signed out at once | Expected after changing `AGRISCAN_SECRET_KEY` |
