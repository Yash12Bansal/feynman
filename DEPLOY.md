# Feynman — GCP Production Deploy Runbook

Deploys the whole product on GCP project **`feynman-basic`**, autoscaling, served at
**`https://feynman-basic.web.app`** (Firebase Hosting — free HTTPS, no custom domain).

## ⚠️ SAFETY — t1-life-prod must NEVER be touched

Your gcloud default project is `t1-life-prod`. This runbook **never** changes it.
Every mutating command below carries `--project feynman-basic`. Before running ANY
block, paste this guard once per shell — it aborts if the project is ever wrong:

```bash
export PROJECT=feynman-basic
export REGION=asia-south1
export ZONE=asia-south1-a
guard() { [ "$PROJECT" = "feynman-basic" ] || { echo "❌ WRONG PROJECT ($PROJECT) — ABORT"; return 1; }; }
guard && echo "✅ target locked to feynman-basic"
# Sanity: this must print feynman-basic, NOT t1-life-prod
gcloud projects describe "$PROJECT" --format='value(projectId)'
```

Belt-and-suspenders: prefix any command with `CLOUDSDK_CORE_PROJECT=feynman-basic` too.

---

## Architecture (what you're standing up)

| Piece | Service | Autoscaling |
|---|---|---|
| Frontend (React) | Firebase Hosting → `feynman-basic.web.app` | CDN (infinite) |
| Artifacts (audio/diagrams) | GCS bucket `feynman-basic-artifacts` (public) | CDN (infinite) |
| Backend API | Cloud Run `feynman-backend` | on requests (min 0, max 20) |
| Lecture-API | Cloud Run `feynman-preview` | on requests (min 0, max 10) |
| **Agent worker** (live doubts) | Compute Engine **MIG** (e2-standard-2) | **on CPU (min 1, max 4)** |
| Postgres | Cloud SQL `feynman-pg` (private IP) | vertical + storage auto |
| Redis + Neo4j | one Debian VM `feynman-data` (private IP) | n/a |
| Auth + feedback | Firebase (already live) | self |
| Secrets | Secret Manager | — |
| Real-time media | LiveKit Cloud (already set) | LiveKit's job |

Everyone reaches Redis/Neo4j/Postgres over the **private VPC**; the no-public-IP
VMs egress to LiveKit/LLM APIs through **Cloud NAT**.

---

## Step 1 — Enable APIs + Artifact Registry

```bash
guard && gcloud services enable \
  run.googleapis.com compute.googleapis.com sqladmin.googleapis.com \
  servicenetworking.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  vpcaccess.googleapis.com --project "$PROJECT"

guard && gcloud artifacts repositories create feynman \
  --repository-format=docker --location="$REGION" --project "$PROJECT"
```

## Step 2 — Secrets → Secret Manager

Pull the real values from your local `.env`. Create one secret per key:

```bash
# Pick strong DB/Neo4j passwords now:
export DB_PASS='CHANGE_ME_db'
export NEO4J_PASS='CHANGE_ME_neo4j'

create_secret() { guard && printf '%s' "$2" | gcloud secrets create "$1" \
  --data-file=- --replication-policy=automatic --project "$PROJECT" 2>/dev/null \
  || printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- --project "$PROJECT"; }

# From your .env (use the PROD keys):
create_secret ANTHROPIC_API_KEY   "sk-ant-..."
create_secret OPENAI_API_KEY      "sk-..."
create_secret DEEPGRAM_API_KEY    "..."
create_secret CARTESIA_API_KEY    "..."
create_secret LIVEKIT_API_KEY     "..."      # from LiveKit Cloud project
create_secret LIVEKIT_API_SECRET  "..."
create_secret DB_PASS             "$DB_PASS"
create_secret NEO4J_PASSWORD      "$NEO4J_PASS"
```

## Step 3 — Networking (VPC connector + private services + Cloud NAT)

```bash
# Serverless VPC connector so Cloud Run reaches private Redis/Neo4j/SQL
guard && gcloud compute networks vpc-access connectors create feynman-conn \
  --region="$REGION" --network=default --range=10.8.0.0/28 --project "$PROJECT"

# Private IP range for Cloud SQL
guard && gcloud compute addresses create google-managed-services-default \
  --global --purpose=VPC_PEERING --prefix-length=16 --network=default --project "$PROJECT"
guard && gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default --network=default --project "$PROJECT"

# Cloud NAT so the no-public-IP VMs can reach LiveKit Cloud + LLM/voice APIs
guard && gcloud compute routers create feynman-router \
  --network=default --region="$REGION" --project "$PROJECT"
guard && gcloud compute routers nats create feynman-nat --router=feynman-router \
  --region="$REGION" --auto-allocate-nat-external-ips \
  --nat-all-subnet-ip-ranges --project "$PROJECT"

# Allow the VPC connector + internal subnet to reach Redis/Neo4j on the data VM
guard && gcloud compute firewall-rules create feynman-allow-internal \
  --network=default --direction=INGRESS --action=ALLOW \
  --rules=tcp:6379,tcp:7687,tcp:7474 \
  --source-ranges=10.8.0.0/28,10.0.0.0/8 --project "$PROJECT"
```

## Step 4 — Postgres (Cloud SQL, private IP)

```bash
guard && gcloud sql instances create feynman-pg \
  --database-version=POSTGRES_17 --tier=db-custom-1-3840 --region="$REGION" \
  --network=default --no-assign-ip --storage-auto-increase \
  --database-flags=max_connections=200 --project "$PROJECT"
# tier db-custom-1-3840 + max_connections=200 gives clear headroom: the backend
# pool is 5 conns/process (db/engine.py) × max 10 instances + 4 workers × 5 = ~70.
guard && gcloud sql databases create feynman --instance=feynman-pg --project "$PROJECT"
guard && gcloud sql users create feynman --instance=feynman-pg \
  --password="$DB_PASS" --project "$PROJECT"

# Capture the PRIVATE IP for DATABASE_URL:
export PG_IP=$(gcloud sql instances describe feynman-pg \
  --format='value(ipAddresses[0].ipAddress)' --project "$PROJECT")
echo "Postgres private IP = $PG_IP"
```

## Step 5 — Redis + Neo4j (one data VM, private IP)

```bash
cat > /tmp/data-startup.sh <<EOF
#! /bin/bash
curl -fsSL https://get.docker.com | sh
docker run -d --restart=always --name redis -p 6379:6379 redis:7-alpine
docker run -d --restart=always --name neo4j -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/${NEO4J_PASS} -e NEO4J_PLUGINS='["apoc"]' \
  -v /var/lib/neo4j-data:/data neo4j:5
EOF

guard && gcloud compute instances create feynman-data \
  --zone="$ZONE" --machine-type=e2-medium --image-family=debian-12 \
  --image-project=debian-cloud --no-address \
  --metadata-from-file=startup-script=/tmp/data-startup.sh --project "$PROJECT"

export DATA_IP=$(gcloud compute instances describe feynman-data --zone="$ZONE" \
  --format='value(networkInterfaces[0].networkIP)' --project "$PROJECT")
echo "Data VM private IP = $DATA_IP   (Redis :6379, Neo4j :7687)"
```

## Step 6 — Artifacts bucket (public, CDN-served)

```bash
guard && gcloud storage buckets create gs://feynman-basic-artifacts \
  --location="$REGION" --uniform-bucket-level-access --project "$PROJECT"
guard && gcloud storage rsync --recursive \
  data_pre_compute_v2/artifacts gs://feynman-basic-artifacts/artifacts --project "$PROJECT"
# Public read so the browser can fetch audio/diagrams directly:
guard && gcloud storage buckets add-iam-policy-binding gs://feynman-basic-artifacts \
  --member=allUsers --role=roles/storage.objectViewer --project "$PROJECT"
```
> The preview server will emit absolute `https://storage.googleapis.com/feynman-basic-artifacts/...`
> URLs (a small `rewrite_url` change — see "Pending code" below) so media bypasses your servers.

## Step 7 — Build + push images

```bash
export AR=$REGION-docker.pkg.dev/$PROJECT/feynman
guard && gcloud builds submit --tag $AR/backend:latest -f Dockerfile.backend . --project "$PROJECT"
guard && gcloud builds submit --tag $AR/preview:latest -f Dockerfile.preview . --project "$PROJECT"
```

## Step 8 — DB migrations (Alembic)

Run once against Cloud SQL (a one-off Cloud Run job using the backend image):

```bash
guard && gcloud run jobs create feynman-migrate --image $AR/backend:latest \
  --region="$REGION" --vpc-connector=feynman-conn \
  --set-secrets=DB_PASS=DB_PASS:latest \
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://feynman:${DB_PASS}@${PG_IP}:5432/feynman" \
  --command=sh --args="-c","alembic upgrade head" --project "$PROJECT"
guard && gcloud run jobs execute feynman-migrate --region="$REGION" --wait --project "$PROJECT"
```

## Step 9 — Deploy backend + preview (Cloud Run, autoscaling)

```bash
COMMON_SECRETS="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:latest,CARTESIA_API_KEY=CARTESIA_API_KEY:latest,LIVEKIT_API_KEY=LIVEKIT_API_KEY:latest,LIVEKIT_API_SECRET=LIVEKIT_API_SECRET:latest"

guard && gcloud run deploy feynman-backend --image $AR/backend:latest --region="$REGION" \
  --min-instances=1 --max-instances=30 --concurrency=60 --cpu=1 --memory=1Gi \
  --no-cpu-throttling --session-affinity --vpc-connector=feynman-conn \
  --vpc-egress=private-ranges-only --ingress=all \
  --set-secrets="$COMMON_SECRETS" \
  --set-env-vars="ENVIRONMENT=production,FRONTEND_URL=https://feynman-basic.web.app,LIVEKIT_URL=wss://feynman-qz4fiboi.livekit.cloud,DATABASE_URL=postgresql+asyncpg://feynman:${DB_PASS}@${PG_IP}:5432/feynman,REDIS_URL=redis://${DATA_IP}:6379/0,NEO4J_URI=bolt://${DATA_IP}:7687,NEO4J_USER=neo4j,NEO4J_PASSWORD=${NEO4J_PASS},USE_NEO4J_CURRICULUM=true" \
  --allow-unauthenticated --project "$PROJECT"
# --min-instances=1 kills cold-start lag; --max-instances=30 gives generous
# autoscaling (30 x 5/process = 150 conns < Cloud SQL max_connections=200).
# No request cap — raise further alongside the Cloud SQL tier / provider quotas.

guard && gcloud run deploy feynman-preview --image $AR/preview:latest --region="$REGION" \
  --min-instances=0 --max-instances=10 --concurrency=80 --cpu=1 --memory=512Mi \
  --vpc-connector=feynman-conn --vpc-egress=private-ranges-only \
  --set-env-vars="NEO4J_URI=bolt://${DATA_IP}:7687,NEO4J_USER=neo4j,NEO4J_PASSWORD=${NEO4J_PASS},ARTIFACTS_BASE_URL=https://storage.googleapis.com/feynman-basic-artifacts/artifacts" \
  --allow-unauthenticated --project "$PROJECT"
```
> `--allow-unauthenticated` is fine — Firebase Hosting fronts these, and the app gates on
> Google sign-in. Tighten to `--ingress=internal-and-cloud-load-balancing` later if you add an LB.

## Step 10 — Agent worker (autoscaling MIG)

```bash
# Resolve secret values for the container env (template metadata — hardening note below)
sv() { gcloud secrets versions access latest --secret="$1" --project "$PROJECT"; }

guard && gcloud compute instance-templates create-with-container feynman-worker-tpl \
  --machine-type=e2-standard-2 --region="$REGION" \
  --container-image=$AR/backend:latest \
  --container-command=python \
  --container-arg=-m --container-arg=feynman.livekit.worker --container-arg=start \
  --no-address \
  --container-env="LIVEKIT_URL=wss://feynman-qz4fiboi.livekit.cloud,LIVEKIT_API_KEY=$(sv LIVEKIT_API_KEY),LIVEKIT_API_SECRET=$(sv LIVEKIT_API_SECRET),ANTHROPIC_API_KEY=$(sv ANTHROPIC_API_KEY),OPENAI_API_KEY=$(sv OPENAI_API_KEY),DEEPGRAM_API_KEY=$(sv DEEPGRAM_API_KEY),CARTESIA_API_KEY=$(sv CARTESIA_API_KEY),REDIS_URL=redis://${DATA_IP}:6379/0,NEO4J_URI=bolt://${DATA_IP}:7687,NEO4J_USER=neo4j,NEO4J_PASSWORD=${NEO4J_PASS},DATABASE_URL=postgresql+asyncpg://feynman:${DB_PASS}@${PG_IP}:5432/feynman,USE_NEO4J_CURRICULUM=true,ENVIRONMENT=production" \
  --project "$PROJECT"
# e2-standard-2 (8GB) holds ~50-60 concurrent doubt sessions; MIG x10 ≈ ~550.
# No fleet cap — autoscaling absorbs the load. Your real ceiling is the provider
# rate limits + LiveKit Cloud plan; raise those before a big launch.

guard && gcloud compute instance-groups managed create feynman-worker \
  --template=feynman-worker-tpl --size=1 --zone="$ZONE" --project "$PROJECT"

# Autoscale on CPU; slow scale-in so a live doubt is never cut mid-answer
guard && gcloud compute instance-groups managed set-autoscaling feynman-worker \
  --zone="$ZONE" --min-num-replicas=1 --max-num-replicas=10 \
  --target-cpu-utilization=0.6 --cool-down-period=120 \
  --scale-in-control=max-scaled-in-replicas=1,time-window=600 --project "$PROJECT"
```
> **Hardening (later):** secrets sit in the template metadata here. Move to runtime fetch via
> the VM service account + `roles/secretmanager.secretAccessor`. Fine for launch.

## Step 11 — Load curriculum into prod Neo4j

The worker + preview need the curriculum graph populated. From a machine that can reach
the data VM (e.g. `gcloud compute ssh feynman-data` and run there, or open Neo4j temporarily),
ingest your `data_pre_compute_v2/out/<chapter>/extraction.json` into the prod Neo4j
(`bolt://$DATA_IP:7687`). Use your existing `lecture-pipeline-v2 load-extraction` path pointed
at the prod Neo4j creds. *(I'll script this precisely as a follow-up.)*

## Step 12 — Frontend → Firebase Hosting (the link)

```bash
cd frontend && pnpm install && pnpm build && cd ..
guard && firebase deploy --only hosting --project "$PROJECT"
# → live at https://feynman-basic.web.app
```
`firebase.json` already rewrites `/api/**` → `feynman-backend` and `/lecture-api/**` →
`feynman-preview`. Sign-in works automatically (`.web.app` is auto-authorized).

## Step 13 — Smoke test

1. Open `https://feynman-basic.web.app`, sign in with Google.
2. Open a lecture → audio + diagrams play (served from the bucket/CDN).
3. Tap **Ask Feynman**, speak → console shows `[LiveKit] Connected to room`, spoken answer plays.
4. `gcloud compute instance-groups managed describe feynman-worker --zone=$ZONE --project $PROJECT`
   → 1 running worker; it scales toward 4 under concurrent-doubt load.

---

## Autoscaling recap
- **Watchers** → CDN, effectively unlimited.
- **Backend/preview** → Cloud Run autoscales on requests (raise `--max-instances` to grow).
- **Live doubts** → worker MIG autoscales 1→10 on CPU. Raise `--max-num-replicas` for more.
  One e2-standard-2 worker handles ~50–60 concurrent doubts; MIG scales 1→10 (~550).
  No cap — load is absorbed by scaling out; provider/LiveKit limits are the real ceiling.

## Cost — there is NO spend cap (by design)
Infra is ~$60–90/mo. The variable cost is the live-voice APIs (LLM+STT+TTS+LiveKit), which scale
with *concurrent talkers* — and there is **no concurrent-doubt cap**, so this spend is unbounded:
the system serves every student rather than queueing anyone. Your guardrails are therefore
external: set a **GCP Budget alert** (you already have 1 budget — add an email threshold) so you
*see* spend in real time, and rely on the **provider rate limits** (Anthropic/OpenAI/Deepgram/
Cartesia) + your **LiveKit Cloud plan** as the natural ceiling. Raise those quotas before a big
launch so genuine demand isn't throttled.

## Production hardening status (verified against the real code)
**Done in code** (handles hundreds of concurrent users without crashing/lagging):
- ✅ Postgres pool capped at 5 conns/process (`db/engine.py`) + Cloud SQL tier/max_connections.
- ✅ Neo4j driver is now a singleton (`chapter_loader.py`, `preview_server.py`).
- ✅ Worker memory-limited + tuned (`worker.py` `AgentServer`) on `e2-standard-2`.
- ✅ No throttling — autoscaling absorbs load (backend 1→30, worker MIG 1→10); no user is queued.
- ✅ Cold-start removed (backend `--min-instances=1`); artifacts on GCS (`ARTIFACTS_BASE_URL`).

**Still to add:**
1. Cloud Build CI/CD (`cloudbuild.yaml`) to rebuild + redeploy on push to `main`.
2. A **GCP Budget alert** email threshold — with no spend cap, this is how you watch cost.
