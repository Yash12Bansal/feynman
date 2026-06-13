# 14 — GCP Deployment, Architecture & Operations

**Status:** LIVE in production. Single-author deploy (June 2026).
**Live URL:** https://feynman-basic.web.app
**GCP project:** `feynman-basic` (project number `46859730090`)
**Region / zone:** `asia-south1` (Mumbai) / `asia-south1-a`

This is the single source of truth for how Feynman is deployed on GCP, how the pieces
communicate, the build/deploy flow, every incident/issue encountered (with root cause), and the
operational runbook. Companion to `00-system-overview.md` (which describes the code, not the
hosting).

> ⚠️ The deploy artifacts and several code changes referenced here live in the **working tree and
> are currently UNCOMMITTED** (Dockerfiles, `cloudbuild.yaml`, `.dockerignore`, `.gcloudignore`,
> `firebase.json` hosting block, `frontend/.env.production`, the preview/`chapter_loader` Neo4j
> changes, the frontend bundle-split, `db/engine.py` pool sizing). Prod was built from this working
> tree. **Commit them** to make prod reproducible.

---

## 1. Architecture — what runs where

```
        ┌─────────────────────── user's browser ───────────────────────────┐
        │  https://feynman-basic.web.app                                     │
        └───┬──────────────┬───────────────┬───────────────┬────────────────┘
            │ HTTPS        │ HTTPS         │ HTTPS         │ WebRTC (voice)
            ▼              ▼               ▼               ▼
     ┌────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────────────┐
     │  FIREBASE  │ │  GCS bucket  │ │  FIREBASE  │ │  LiveKit Cloud   │
     │  HOSTING   │ │  artifacts   │ │ Auth + FS  │ │ (EXTERNAL — not  │
     │ (React+CDN)│ │ (audio/svg)  │ │            │ │  on GCP)         │
     └──┬──────┬──┘ └──────────────┘ └────────────┘ └────────┬─────────┘
 /api/* │      │ /lecture-api/*                              │ dispatches doubt jobs
        ▼      ▼                                             ▼
  ┌──────────┐ ┌──────────┐                        ┌──────────────────┐
  │ Cloud Run│ │ Cloud Run│                        │ Compute Engine   │
  │ backend  │ │ preview  │                        │ worker (MIG VM)  │
  └────┬─────┘ └────┬─────┘                        └────────┬─────────┘
       │  (private VPC: connector for Cloud Run, same network for the VMs)  │
       └──────┬─────┴───────────────────┬────────────────────┬─────────────┘
              ▼                          ▼                    ▼ (internet via Cloud NAT)
   ┌──────────────────────┐  ┌──────────────────────────┐  LLM/STT/TTS + LiveKit APIs
   │ Cloud SQL (Postgres) │  │ data VM: Neo4j + Redis    │
   │  10.93.0.3 (private) │  │  10.160.0.2 (private)     │
   └──────────────────────┘  └──────────────────────────┘
```

### Component inventory (exact)

| Component | GCP resource | Key config | Address |
|---|---|---|---|
| Frontend + front door | **Firebase Hosting**, site `feynman-basic` | rewrites `/api/**`→backend, `/lecture-api/**`→preview, `**`→`/index.html`; `/assets` cached immutably (`firebase.json`) | `feynman-basic.web.app` / `.firebaseapp.com` |
| Audio + diagrams | **GCS** `gs://feynman-basic-artifacts` | public-read (`allUsers` objectViewer); ~14,198 objects (~521 MB); served direct (no Cloud CDN) | `storage.googleapis.com/feynman-basic-artifacts/artifacts/...` |
| API server | **Cloud Run** `feynman-backend` | image `…/feynman/backend:latest`; **min 1 / max 30**, concurrency 60, cpu 1, mem 1Gi, `--no-cpu-throttling`, `--session-affinity`, `--vpc-connector feynman-conn`, `--vpc-egress private-ranges-only`, `--allow-unauthenticated` | `feynman-backend-46859730090.asia-south1.run.app` |
| Lecture API | **Cloud Run** `feynman-preview` | image `…/feynman/preview:latest`; **min 1 / max 10**, concurrency 80, cpu 1, mem 512Mi, VPC connector, `--allow-unauthenticated` | `feynman-preview-46859730090.asia-south1.run.app` |
| Live-doubt worker | **Compute Engine MIG** `feynman-worker` | template `feynman-worker-tpl`, **e2-standard-2** (2 vCPU/8 GB), runs backend image w/ cmd `python -m feynman.livekit.worker start`, no public IP; autoscale **min 1 / max 10**, target-CPU 0.6, slow scale-in | instance e.g. `feynman-worker-d80n` |
| Postgres | **Cloud SQL** `feynman-pg` | POSTGRES_17, **ENTERPRISE** edition, `db-custom-1-3840` (1 vCPU/3.75 GB), private IP, `max_connections=200`; db `feynman`, user `feynman` | `10.93.0.3:5432` (private) |
| Neo4j + Redis | **VM** `feynman-data` | **e2-medium** (2 vCPU/4 GB), Debian 12, no public IP; Docker: `neo4j:5`+APOC (7687/7474, data on `/var/lib/neo4j-data`, `--restart=always`) and `redis:7-alpine` (6379) | `10.160.0.2` (private) |
| Auth + feedback | **Firebase Auth** (Google) + **Firestore** | collections: `users` (profiles), `feedback` (`type:submission` + `type:bounce`); rules require sign-in to write | Firebase console |
| Real-time voice | **LiveKit Cloud** (external) | project `feynman-qz4fiboi`, region "India West" | `wss://feynman-qz4fiboi.livekit.cloud` |
| Secrets | **Secret Manager** | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DB_PASS`, `NEO4J_PASSWORD` | — |
| Images | **Artifact Registry** repo `feynman` (asia-south1) | `backend`, `preview` | `asia-south1-docker.pkg.dev/feynman-basic/feynman/…` |
| Migrations | **Cloud Run job** `feynman-migrate` | backend image, `alembic upgrade head` | one-off |

### Networking
- **VPC connector** `feynman-conn` (asia-south1, range `10.8.0.0/28`, default network) — lets Cloud
  Run reach the private DBs.
- **Private services peering** (`google-managed-services-default`, /16) — gives Cloud SQL its private IP.
- **Cloud NAT** (router `feynman-router` + nat `feynman-nat`) — outbound internet for the no-public-IP
  VMs (worker → LiveKit/LLM APIs; data VM → pull images).
- **Firewall:** `feynman-allow-internal` (tcp 6379/7687/7474 from `10.0.0.0/8`), `feynman-allow-iap-ssh`
  (tcp 22 from `35.235.240.0/20`, for IAP SSH).
- **The databases (Neo4j, Redis, Postgres) have NO public IP** — reachable only inside the VPC. Not
  internet-attackable.
- **IAM:** default compute SA `46859730090-compute@developer.gserviceaccount.com` granted
  `roles/secretmanager.secretAccessor` + `roles/artifactregistry.reader`. `USE_NEO4J_CURRICULUM=false`
  (the flag is vestigial — read nowhere in code).

---

## 2. How components communicate (request flows)

### Watching a lecture (the ~95% path — cheap, no backend/worker/LiveKit)
1. Browser loads the app from **Firebase Hosting**; signs in via **Firebase Auth** (Google).
2. Home screen `GET /lecture-api/chapters` → Hosting rewrite → **preview** → **Neo4j** → chapter list.
3. Click a lecture → `GET /lecture-api/chapter/{id}` → preview → Neo4j → the playback **manifest**.
4. Playback pulls audio + diagrams **directly from the GCS bucket**. Fully client-side.

### Ask Feynman (the live-doubt path)
1. Tap "Ask Feynman" → `POST /api/sessions` → **backend** → creates a session (**Cloud SQL**),
   creates a **LiveKit** room, returns a token.
2. Browser joins the LiveKit room. **LiveKit Cloud** dispatches the room to the **worker** (registered).
3. User speaks → worker: STT (OpenAI) → loads chapter context from **Neo4j** → plans (Anthropic
   Claude) → generates a diagram (uses `design_agent/backend/prompts.py`) → TTS (OpenAI) → streams
   voice + visuals back over LiveKit.
4. Feedback/profiles → **Firestore** (direct from browser).

### Who talks to whom
- Browser ↔ Firebase Hosting (HTTPS; serves app + proxies `/api`,`/lecture-api`).
- Browser ↔ GCS bucket (HTTPS; media). Browser ↔ LiveKit Cloud (WebRTC; voice). Browser ↔ Firebase Auth/Firestore.
- Cloud Run (backend, preview) ↔ Neo4j/Redis (private, via VPC connector) + Cloud SQL (private IP).
- Worker VM ↔ Neo4j/Redis/Cloud SQL (private VPC) + LiveKit/LLM/STT/TTS (internet via Cloud NAT).

---

## 3. Build & deploy flow

```
code (Dockerfile.backend / Dockerfile.preview)
  └─► Cloud Build (cloudbuild.yaml, substitutions _DOCKERFILE/_IMAGE)
        └─► Artifact Registry (backend:latest, preview:latest)
              ├─► Cloud Run services (backend, preview) — `gcloud run deploy/update --image`
              └─► Worker MIG VM — pulls backend:latest on boot (konlet)
frontend:  `pnpm exec vite build` → dist/ ─► Firebase Hosting (REST API deploy — see incident #3)
secrets:   Secret Manager → injected into Cloud Run at runtime / baked into worker template
data:      curriculum loaded into Neo4j once via `lecture-pipeline-v2 load-extraction` over an IAP tunnel
```

Notes:
- `gcloud builds submit` uploads context per **`.gcloudignore`** (NOT `.dockerignore`) — that file
  keeps the 521 MB artifacts out of the upload.
- Cloud Run `--image …:latest` pulls a fresh image; the worker MIG pulls `:latest` on instance
  recreate (`rolling-action`/`recreate-instances`).
- Frontend is built with **`vite build` directly** (not `pnpm build`) to skip a pre-existing
  `tsc -b` failure (incident #6).
- 15 chapters are loaded in Neo4j (9th/10th/11th/12th/CA tabs).

---

## 4. Issues & incidents (complete)

### 🔴 INCIDENT 1 — Lectures stopped loading (production outage, ~June 12–14 2026)
**Symptom:** home screen rendered but lecture cards were empty; `/lecture-api/chapters` returned
`HTTP 000` after a 35 s client timeout.

**Root-cause chain:**
1. The **data VM rebooted (~June 12)** — routine GCP host maintenance (`onHostMaintenance: MIGRATE`,
   but a reboot still occurred; VM uptime confirmed ~45 h vs ~69 h since creation).
2. The reboot **severed all open TCP connections to the VM**, including the preview service's open
   Neo4j (bolt) connections.
3. **Neo4j itself recovered fine** (`--restart=always`; verified up 45 h, 15 chapters intact, no
   recent errors, memory healthy). The database never broke.
4. The **preview Cloud Run instance kept running** (`min-instances=1`, no restart) holding a
   **module-level singleton Neo4j driver** whose pooled connections were now all dead.
5. The driver had **no liveness check**, so it kept failing to acquire a connection →
   `neo4j.exceptions.ConnectionAcquisitionTimeoutError: failed to obtain a connection from the pool
   within 60.0s` on every request.
6. → `/lecture-api/chapters` hung → empty cards.
7. **No monitoring/alert existed** → undetected for ~2 days until a user noticed.

**Not the cause (ruled out with evidence):** VM reboot of the *compute* (no — `lastStartTimestamp`
== creation), preemption (not preemptible), host kernel OOM (no `oom-killer` in serial log),
**attack/scraping** (peak ~85 req/hr; top clients all `66.249.82.x` = Googlebot).

**Regression owner:** the singleton driver was introduced during this deploy (to cut connection
churn) in `preview_server.py::_get_neo4j_driver` and `chapter_loader.py::_get_driver`. The original
code opened a driver per request, which self-heals after a reboot. The optimization removed that.

**Temporary fix applied:** bounced the preview service
(`gcloud run services update feynman-preview --update-env-vars _BOUNCE=<ts>`) → fresh driver →
reconnected → 15 chapters again (warm latency ~0.4–0.5 s; chapter manifest ~0.75 s).

**Permanent fix (PENDING — see §5):** add `liveness_check_timeout=30` + `max_connection_lifetime=300`
to the driver in BOTH `preview_server.py` and `chapter_loader.py` (the worker has the same pattern
→ a future reboot could otherwise wedge *doubts* the same way), rebuild + redeploy, and add a
Cloud Monitoring uptime alert on `/lecture-api/chapters`.

### 🟡 Deployment-time issues (caught + fixed during the build-out)
| # | Component | What broke | Fix |
|---|---|---|---|
| 2 | Cloud SQL | First `create` failed — `db-custom-1-3840` not allowed on default **ENTERPRISE_PLUS** edition | added `--edition=ENTERPRISE` |
| 3 | Firebase Hosting deploy | Firebase CLI not authenticated (401); ignored the `GOOGLE_APPLICATION_CREDENTIALS` SA key | deployed via the **Firebase Hosting REST API** with a `gcloud auth print-access-token` token + `x-goog-user-project` header (fixed an ADC quota-project 403) |
| 4 | Cloud Run backend | First deploy failed — compute SA lacked **Secret Manager** access | granted SA `roles/secretmanager.secretAccessor` + `roles/artifactregistry.reader` |
| 5 | Worker VM | Doubt jobs crashed: `FileNotFoundError: /app/design_agent/backend/prompts.py` — image only copied `backend/` + kernel, not `design_agent/` | added `COPY design_agent/backend/` to `Dockerfile.backend`; rebuilt + recreated the worker instance |
| 6 | Cloud Run preview | Would have failed against prod Neo4j — read DB config from baked `config.yaml` (localhost), not env | added a `NEO4J_*` env override in `preview_server.py` (caught **before** it broke) |
| 7 | Frontend build | `pnpm build` fails on **pre-existing** TypeScript errors (`tsc -b`) | build with `vite build` directly (the runtime transpile path; skips the type-check gate) |
| 8 | gcloud builds submit | Would have uploaded the 521 MB artifacts as build context | added `.gcloudignore` |

### 🟢 Looked broken but weren't (clarifications)
- **"Empty feedback documents" in Firestore** — intentional **bounce beacons** (`type:"bounce"`,
  written by `useLeaveSignals.ts` on `pagehide` when a signed-in user leaves without submitting).
  Real feedback is `type:"submission"`. Filter by `type` in the Firestore console.
- **Collaborator "couldn't use Firestore"** — their clone lacked `frontend/.env.local` (gitignored →
  never pushed) → `firebaseConfigured=false` → "Sign-in isn't configured." Fix: recreate
  `frontend/.env.local` with the (public) Firebase web config + sign in (Firestore rules require auth;
  `VITE_AUTH_DISABLED=true` does NOT help — it leaves the user unauthenticated).
- **"Site feels slow"** — not broken; the first-load JS bundle was 1.77 MB. **Fixed** by code-splitting
  (lazy-load the lecture experience `MainApp`): initial chunk **1.77 MB → 669 KB** (gzip 525→207 KB);
  the lecture engine loads on demand. (`App.tsx` + new `MainApp.tsx` + `hooks/useLectureChapterParam.ts`.)

### Performance/scaling decisions of note
- A **concurrent-doubt cap** (Redis counter, `MAX_CONCURRENT_DOUBTS`) was built then **removed per
  product decision** ("no limits"). Consequence: **no spend ceiling** on live-voice APIs — rely on a
  GCP budget alert + provider/LiveKit rate limits as the natural ceiling.
- `db/engine.py` pool capped to 5 conns/process (serverless-safe); backend `--max-instances` raised to
  30, worker MIG max to 10 (autoscaling, no user-facing throttle).
- STT/TTS run on the **OpenAI fallback** (no Deepgram/Cartesia keys present). Works; add those keys
  (secret + env) for better voice latency.

---

## 5. Pending / recommended work
1. **(Required) Neo4j-driver resilience** — add `liveness_check_timeout=30` + `max_connection_lifetime=300`
   to `AsyncGraphDatabase.driver(...)` in `data_pre_compute_v2/tools/preview_server.py` AND
   `backend/src/feynman/agent/doubt_resolution/chapter_loader.py`; rebuild both images; redeploy
   preview + backend Cloud Run; recreate the worker instance. (Prevents INCIDENT 1 from recurring.)
2. **(Required) Monitoring** — Cloud Monitoring uptime check + email alert on
   `https://feynman-basic.web.app/lecture-api/chapters`.
3. **Commit the deploy artifacts** (listed in the banner at top) so prod is reproducible / CI-able.
4. **CI/CD** — a Cloud Build trigger to rebuild+redeploy on push to `main`.
5. **Lower priority:** rate-limit the public `/lecture-api`; Cloud CDN in front of the artifacts
   bucket; consider managed **Neo4j Aura** to remove the single-VM fragility; enable Cloud Logging on
   the worker/data VMs so their container logs appear in the console (today: read via SSH).

---

## 6. Operations runbook

### Quick health check
```bash
PROJ=feynman-basic; REG=asia-south1
curl -s "https://feynman-basic.web.app/lecture-api/chapters" -w "\n[HTTP %{http_code}]\n" | head -c 200   # expect 15 chapters
gcloud run services list --region $REG --project $PROJ
gcloud compute instance-groups managed list-instances feynman-worker --zone $REG-a --project $PROJ
```

### Where to look when X breaks
| Symptom | Where |
|---|---|
| Page won't load / sign-in fails | Firebase console → Hosting + Authentication; browser DevTools |
| Lectures don't list/play | `gcloud run services logs read feynman-preview --region asia-south1` (usually a Neo4j-connection issue → see "Neo4j down" below) |
| API/session errors | `gcloud run services logs read feynman-backend --region asia-south1` |
| Ask-Feynman (voice) broken | Worker logs are **NOT** in Cloud Logging — SSH: `gcloud compute ssh <worker> --zone asia-south1-a --tunnel-through-iap --command="sudo docker logs \$(sudo docker ps -q --filter name=klt-feynman) 2>&1 | tail -50"`; also the LiveKit Cloud dashboard |
| Cost | Console → Billing → Budgets (no spend cap exists) |
| Who's visiting / users | Firebase → **Authentication → Users** (signed-in), **Analytics** (visitors, GA `G-FM6THN58W8`), **Firestore** (`users`, `feedback`) |

### Fix: "lectures down / Neo4j connection timeout" (INCIDENT 1 recurrence)
```bash
PROJ=feynman-basic; REG=asia-south1
# 1. Is Neo4j actually up + data intact? (SSH to the data VM)
NEO4J_PASS=$(gcloud secrets versions access latest --secret=NEO4J_PASSWORD --project $PROJ)
gcloud compute ssh feynman-data --zone $REG-a --tunnel-through-iap --project $PROJ \
  --command="sudo docker exec neo4j cypher-shell -u neo4j -p '$NEO4J_PASS' 'MATCH (c:Chapter) RETURN count(c);'"
#    if it's down:  sudo docker start neo4j
# 2. If Neo4j is UP but lectures still time out → the preview driver is wedged → bounce it:
gcloud run services update feynman-preview --region $REG --project $PROJ --update-env-vars "_BOUNCE=$(date +%s)"
# 3. verify
curl -s "https://feynman-basic.web.app/lecture-api/chapters" -w "\n[HTTP %{http_code}]\n" | head -c 120
```
(The permanent fix in §5 removes the need for step 2.)

### Redeploy (the standard flow)
```bash
PROJ=feynman-basic; REG=asia-south1; AR=$REG-docker.pkg.dev/$PROJ/feynman
# backend or preview image:
gcloud builds submit --config cloudbuild.yaml --substitutions=_DOCKERFILE=Dockerfile.backend,_IMAGE=$AR/backend:latest --project $PROJ .
gcloud run services update feynman-backend --region $REG --project $PROJ --image $AR/backend:latest
# worker picks up a new backend image by recreating its instance:
W=$(gcloud compute instances list --filter="name~feynman-worker" --format="value(name)" --project $PROJ | head -1)
gcloud compute instance-groups managed recreate-instances feynman-worker --zone $REG-a --instances="$W" --project $PROJ
# frontend:
cd frontend && pnpm exec vite build && cd .. && python3 /tmp/fb_deploy.py   # REST deploy (Firebase CLI isn't authed)
```

### Grant a teammate access
```bash
gcloud projects add-iam-policy-binding feynman-basic --member="user:THEIR_EMAIL" --role="roles/editor"
```
(Editor for a developer; Owner only for a co-founder. To run the app locally they also need
`frontend/.env.local` with the public Firebase config + sign in.)
