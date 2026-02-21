# Ventro — Cloud Setup Log
### Step-by-Step Tasks for Free Cloud Deployment

*This is a living log. Mark each task ✅ as you complete it.*

---

## Stack Overview

| Service | Provider | Free Limit | Task |
|---------|----------|-----------|------|
| Frontend | Vercel | Unlimited hobby | [Task A](#task-a--vercel-frontend) |
| Backend API | Render.com | 750 hrs/mo | [Task B](#task-b--render-backend) |
| LLM Inference | Groq | 30 req/min free | [Task C](#task-c--groq-api-key) |
| Vector DB | Qdrant Cloud | 1 GB free | [Task D](#task-d--qdrant-cloud) |
| PostgreSQL | Supabase | 500 MB free | [Task E](#task-e--supabase-postgresql) |
| MongoDB | Atlas | 512 MB free | [Task F](#task-f--mongodb-atlas) |
| Redis | Upstash | 10k cmd/day | [Task G](#task-g--upstash-redis) |

**Estimated total setup time: 60–90 minutes** (mostly waiting for deploys)

---

## Task C — Groq API Key

> Do this first — it's the fastest setup (< 2 min).

**Objective:** Get a free LLM inference API key to replace local Ollama.

**Steps:**
1. Go to **https://console.groq.com**
2. Click **Sign In** → use GitHub or Google
3. Navigate to **API Keys** → **Create API Key**
4. Name it `ventro-prod`
5. Copy the key: `gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`
6. **Save it** — you'll need it in Tasks B and E

**✅ Done when:** You have a `gsk_...` key saved.

---

## Task D — Qdrant Cloud

**Objective:** Create a free managed vector database for document embeddings.

**Steps:**
1. Go to **https://cloud.qdrant.io**
2. Sign up with GitHub → **Free tier** (1 GB)
3. Click **Create Cluster** → select:
   - Name: `ventro`
   - Cloud: `GCP` or `AWS`
   - Region: closest to you
   - Tier: **Free**
4. Wait ~2 minutes for cluster to start
5. Note your **Cluster URL**: `https://xxxx.us-east4-0.gcp.cloud.qdrant.io`
6. Go to **API Keys** → **Create API Key** → copy it

**Values to save:**
```
QDRANT_HOST=xxxx.us-east4-0.gcp.cloud.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-api-key
```

**✅ Done when:** Cluster is Running and you have the API key.

---

## Task E — Supabase PostgreSQL

**Objective:** Create a free PostgreSQL database for sessions and audit trails.

**Steps:**
1. Go to **https://supabase.com** → **Start your project** → GitHub login
2. Click **New Project** → set:
   - Name: `ventro`
   - Database Password: **generate a strong one — save it**
   - Region: closest to you
3. Wait ~2 minutes for provisioning
4. Go to **Project Settings** → **Database** → scroll to **Connection string**
5. Select **Transaction** pool mode (important for serverless)
6. Copy the URI — it looks like:
   ```
   postgresql://postgres.abcdef:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres
   ```
7. Prepend `asyncpg+` to the scheme:
   ```
   postgresql+asyncpg://postgres.abcdef:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres
   ```

**✅ Done when:** You have the `postgresql+asyncpg://...` connection string.

---

## Task F — MongoDB Atlas

**Objective:** Create a free MongoDB cluster for parsed documents and workpapers.

**Steps:**
1. Go to **https://cloud.mongodb.com** → **Try Free** → GitHub login
2. Select **Free Shared** tier (M0) → any region
3. **Security → Database Access** → Add database user:
   - Username: `ventro_user`, Password: strong one
   - Role: `Atlas admin`
4. **Security → Network Access** → Add IP address → **0.0.0.0/0** (allow all — needed for cloud)
5. **Databases → Connect** → **Drivers** → copy the connection string.
   Atlas formats it as:
   ```
   scheme://username:your-db-password@cluster-host/
   ```
   Where:
   - `scheme` = `mongodb+srv`
   - `username` = `ventro_user`
   - `your-db-password` = the password you set in step 3
   - `cluster-host` = something like `cluster0.xxxxx.mongodb.net`

6. Append the database name and options to the end of the URL:
   ```
   /ventro_docs?retryWrites=true&w=majority
   ```
   > **Important:** Never paste real credentials into documentation or commit them to git.
   > Store this URL only in your Render.com environment variables (Task B).

**✅ Done when:** You have the `mongodb+srv://...` connection string.

---

## Task G — Upstash Redis

**Objective:** Create a free Redis instance for WebSocket pub/sub.

**Steps:**
1. Go to **https://console.upstash.com** → **Sign Up** → GitHub login
2. Click **Create Database** → select:
   - Name: `ventro-redis`
   - Type: **Regional**
   - Region: closest to you
   - **TLS enabled** ✓
3. After creation, go to **Details** → scroll to **.env** section
4. Copy the `UPSTASH_REDIS_REST_URL` — but you need the raw Redis URL format:
   ```
   rediss://default:PASSWORD@REGION.upstash.io:6379
   ```
   (Found under **Connect** → **Redis Client**)

**✅ Done when:** You have the `rediss://...` URL.

---

## Task B — Render Backend

**Objective:** Deploy the FastAPI backend to Render's free web service.

**Pre-requisites:** Tasks C, D, E, F, G must be complete (you need all connection strings).

**Steps:**
1. Go to **https://render.com** → **Get Started for Free** → GitHub login
2. Click **New +** → **Web Service**
3. Connect the **NeoOne601/Ventro** GitHub repository
4. Configure:
   ```
   Name:           ventro-api
   Root Directory: mas-vgfr/backend
   Runtime:        Docker   ← select Docker (uses Dockerfile)
   Branch:         main
   Region:         Oregon (US West) or closest
   Instance Type:  Free
   ```
5. Scroll to **Environment Variables** → Add each of these:

   | Key | Value |
   |-----|-------|
   | `APP_ENV` | `production` |
   | `APP_SECRET_KEY` | *run `openssl rand -hex 32` locally to generate* |
   | `GROQ_API_KEY` | *from Task C* |
   | `GROQ_MODEL` | `llama-3.3-70b-versatile` |
   | `DATABASE_URL` | *from Task E* |
   | `MONGO_URL` | *from Task F* |
   | `MONGO_DB` | `ventro_docs` |
   | `REDIS_URL` | *from Task G* |
   | `QDRANT_HOST` | *from Task D (without https://)* |
   | `QDRANT_PORT` | `6333` |
   | `QDRANT_API_KEY` | *from Task D* |
   | `QDRANT_COLLECTION_NAME` | `ventro_docs` |
   | `ALLOWED_ORIGINS` | `["https://ventro.vercel.app"]` *(update after Task A)* |
   | `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |
   | `EMBEDDING_DIMENSION` | `384` |
   | `SAMR_ENABLED` | `true` |
   | `SAMR_DIVERGENCE_THRESHOLD` | `0.85` |
   | `TEMP_UPLOAD_DIR` | `/tmp/ventro_uploads` |

6. Click **Create Web Service** → wait for build to complete (~5–10 min first time)
7. Your backend URL: `https://ventro-api.onrender.com`
8. Test: `curl https://ventro-api.onrender.com/health`

**✅ Done when:** `/health` returns `{"status":"healthy",...}`

> **Note:** Render free tier sleeps after 15 min inactivity. First request after sleep takes ~30s. For demos, send a warm-up request first.

---

## Task A — Vercel Frontend

**Objective:** Deploy the React frontend to Vercel (global CDN, auto HTTPS).

**Pre-requisite:** Task B must be complete (you need the Render backend URL).

**Steps:**
1. Go to **https://vercel.com** → **Start Deploying** → GitHub login
2. Click **Add New Project** → Import **NeoOne601/Ventro**
3. Configure:
   ```
   Root Directory:    mas-vgfr/frontend
   Framework Preset:  Vite   (auto-detected)
   Build Command:     npm run build
   Output Directory:  dist
   Install Command:   npm install
   ```
4. Add Environment Variables:

   | Key | Value |
   |-----|-------|
   | `VITE_API_BASE_URL` | `https://ventro-api.onrender.com` |

5. Click **Deploy** → wait ~2 minutes
6. Your frontend URL: `https://ventro.vercel.app` (or custom subdomain Vercel assigns)
7. **Go back to Render** → Update `ALLOWED_ORIGINS` env var with your actual Vercel URL
8. In Render dashboard click **Manual Deploy** to pick up the CORS change

**✅ Done when:** `https://ventro.vercel.app` loads the dashboard.

---

## Task H — End-to-End Smoke Test

Run after all services are deployed:

**Test 1: Health check**
```bash
curl https://ventro-api.onrender.com/health
# Expected: {"status":"healthy","service":"MAS-VGFR","version":"1.0.0"}
```

**Test 2: Upload a document**
```bash
curl -X POST https://ventro-api.onrender.com/api/v1/documents/upload \
  -F "file=@any_invoice.pdf"
# Expected: {"document_id":"...","document_type":"invoice","classification_confidence":0.XX}
```

**Test 3: Full UI flow**
1. Open `https://ventro.vercel.app`
2. Upload PO + GRN + Invoice
3. Click **Start AI Reconciliation**
4. Verify the agent pipeline streams in real time
5. View the interactive Audit Workpaper

**✅ Done when:** Full reconciliation completes without errors.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Render build fails | Missing dependency | Check build logs → `pip install` error |
| CORS error in browser | Wrong `ALLOWED_ORIGINS` | Update env var + redeploy backend |
| Qdrant connection refused | Wrong host format | Remove `https://` from `QDRANT_HOST` |
| Groq 429 rate limit | Too many requests | Wait 60s; free tier: 30 req/min |
| Render cold start | Service was sleeping | First request takes 30s — normal |
| MongoDB auth failed | Password has special chars | URL-encode `@` as `%40`, `#` as `%23` |
| Supabase SSL error | Missing `?sslmode=require` | Add `?ssl=true` to connection string |

---

## Deployment Status Tracker

| Task | Service | Status | URL |
|------|---------|--------|-----|
| C | Groq | ⬜ Pending | https://console.groq.com |
| D | Qdrant Cloud | ⬜ Pending | https://cloud.qdrant.io |
| E | Supabase | ⬜ Pending | https://supabase.com |
| F | MongoDB Atlas | ⬜ Pending | https://cloud.mongodb.com |
| G | Upstash Redis | ⬜ Pending | https://console.upstash.com |
| B | Render Backend | ⬜ Pending | https://render.com |
| A | Vercel Frontend | ⬜ Pending | https://vercel.com |
| H | Smoke Test | ⬜ Pending | — |
