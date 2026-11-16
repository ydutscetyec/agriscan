# AGRISCAN 2.0 — web dashboard (Prompt 3)

React + Vite, Leaflet with OpenStreetMap, Chart.js. Talks to the Flask backend from
Prompts 1 and 2; it holds no logic that affects a diagnosis.

## Run

```bash
cd backend && python run.py          # terminal 1
cd backend && python -m worker.run   # terminal 2
cd web && npm install && npm run dev # terminal 3 → http://localhost:5173
```

No `.env` is needed: the app calls `/api` on its own origin, which the Vite proxy
forwards in development and `backend/serve.py` mounts in production.

For a deployed server: `npm ci && npm run build`, then `python serve.py` in `backend`
serves `dist/`. See `DEPLOY.md` in the project root.

## Pages

Overview · Map · Detections · Detection detail · Fields · Drone missions · Farmers ·
Models · Users.

There is deliberately **no** navigation for 3D terrain, irrigation, soil or outbreak
risk. Those subsystems have no data source, and an empty page in a demo invites a
question the system cannot answer.

## One component renders every detection

`src/components/Detection.jsx` is the only place verification state becomes pixels:
`StatusBadge`, `SeverityTag`, `ConfidenceLabel`, `markerIcon`, `MapLegend`. If you write
`detection.status` into JSX anywhere else, that is a bug.

Shape carries the meaning, not colour alone, so the distinction survives greyscale
printing and colour-blind readers:

| Status | Marker | Label |
| --- | --- | --- |
| `ai_detected` | outlined, grey border | AI detected |
| `low_confidence` | grey dashed | Low confidence |
| `farmer_confirmed` | half-filled | Farmer confirmed |
| `technician_verified` | solid | Technician verified |
| `rejected` | hollow, struck through | Rejected |

Severity renders as colour + word + number (`● Moderate 18.7%`). Confidence renders only
as `91.4% model confidence`; the words are part of the value, never a caption.

### Severity bands

`0–0.5% None · <10% Mild · <30% Moderate · ≥30% Severe`, matching the AGRISCAN visual
design system, where 18.7% affected area is Moderate. Bands are presentation only; the
stored number is what a technician checks.

## Aggregates and unverified data

The map's **verified-only** toggle defaults to ON. Switching it off replaces the panel
note with a warning that marker density is not a measure of disease presence until a
technician has reviewed the cases. The Overview charts carry the same toggle, and every
count states the filter that produced it.

## Performance

The detections request is bounded by the map viewport (`min_lat`/`max_lat`/`min_lon`/
`max_lon`) and capped at 500 rows, so the whole table is never loaded into the browser.
Markers cluster above 200. Leaflet and Chart.js are code-split and load only with their
page: first paint is ~107 kB gzipped, the map adds ~18 kB, the charts ~59 kB.

## Known gaps

- Severity is filtered in the browser; there is no server-side severity filter yet, and
  the Detections page says so rather than implying the server did it.
- Verification and farmer feedback are read-only here. Writing them is Prompt 4.
- Reports has no page yet: PDF generation is not built.

## Field client (Prompt 5)

Routes under `/field`, sharing this codebase and component library. A **mobile-responsive
web app, not a native app**. A farmer signing in lands here automatically; technicians and
researchers land on the dashboard.

Three screens, no more:

| Route | Screen |
| --- | --- |
| `/field` | Capture — camera button, field picker, optional drone zone reference, note |
| `/field/results` | My results — newest first, queued and synced together |
| `/field/results/:id` | Result — six answers, large type, English beside Hiligaynon |

### The six answers, in order

What was found · Where · How bad · How sure the model is · What to do · When to call a
technician. Nothing else is on that screen: anything extra competes with the decision the
farmer is making.

If no approved recommendation exists, "What to do" shows **Pending technician review** and
no advice text at all — not even a draft.

### Offline

- `src/field/db.js` — IndexedDB store, keyed by a client-generated UUID, holding the image
  blob and metadata. Nothing is deleted until the server returns a record id.
- `src/field/sync.js` — drains oldest-first, exponential backoff from 2s capped at 5min,
  retries on reconnect and on a 15s timer.
- `public/sw.js` — caches the app shell and already-seen approved recommendations.
  It deliberately does **not** cache detection lists: a stale crop result shown as current
  is worse than an honest "cannot reach the server".

Idempotency has two layers: the client UUID (sent as `client_uuid`, unique-indexed
server-side) and the content hash. The UUID catches a retry whose bytes were re-encoded;
the hash catches the same file sent twice.

A capture made offline reads **Queued — will analyse when connected**. There is no spinner
suggesting the phone is analysing anything; inference is server-side and the copy says so.

### Feedback

The result screen's two buttons record whether the model was right. The screen states
plainly that this is not approving the advice — only a technician does that.

### Tests

```bash
npm test          # vitest: 12 tests covering the offline queue
```

Covers persistence across a reload, oldest-first draining, backoff growth and capping,
the same UUID on every retry, refusing to mark synced without a server record id, and
keeping the local blob when an upload fails.

## Drone camera setup (p7)

Browsers only allow the camera, GPS and screen wake-lock on **HTTPS** pages. A phone
opening `http://192.168.x.x` would have its camera blocked. So the phone needs the
field mode of the dev server.

**On the laptop**

```powershell
cd web
npm run dev:field
```

Windows will ask whether Node.js may use the network. Allow it on **private** networks.

Find the laptop's address:

```powershell
ipconfig
```

Use the IPv4 address of the Wi-Fi adapter, e.g. `192.168.1.23`.

**On the drone phone** (same Wi-Fi or the laptop's hotspot)

1. Open Chrome at `https://192.168.1.23:5173/camera`
2. Chrome warns about the certificate. Tap **Advanced → Proceed**. This happens once;
   the certificate is self-signed by the dev server.
3. Sign in as a technician. You return to /camera automatically.
4. Name and pair the phone.
5. Allow camera and location when asked.

The phone appears on the dashboard's **Drone camera** page within a few seconds.

**Before each flight**

- Battery above 50%, location accuracy under ±10 m (wait in the open), screen timeout
  set to its maximum as a backup to the wake lock.
- Start the session from the dashboard **on the ground**. Confirm the phone shows
  Capturing. Then take off.
- After landing, keep the page open near Wi-Fi until "Waiting to upload" reaches zero.

The backend stays on `127.0.0.1:5000`. Only the Vite server is visible on the network,
and it forwards `/api` to the backend, so the phone never talks to Flask directly.
