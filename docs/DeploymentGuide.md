# Ventro — Deployment Guide
### Internal Ops Document · Local Demo · Production Go-Live · Free Web Showcase

*Version 1.0 · February 2026 · Confidential*

---

## Table of Contents

1. [Prerequisites Checklist](#1-prerequisites-checklist)
2. [Local Demo (Fastest Path)](#2-local-demo-fastest-path)
3. [Sharing Locally Over the Web (Ngrok)](#3-sharing-locally-over-the-web-ngrok)
4. [Free Cloud Deployment (Zero-Cost Public Demo)](#4-free-cloud-deployment-zero-cost-public-demo)
5. [Production Go-Live (Self-Hosted)](#5-production-go-live-self-hosted)
6. [Environment Variable Reference](#6-environment-variable-reference)
7. [Health Check & Smoke Test](#7-health-check--smoke-test)
8. [Rollback Procedure](#8-rollback-procedure)

---

## 1. Prerequisites Checklist

### For Local Demo
- [ ] macOS / Ubuntu 22.04+
- [ ] Docker Desktop ≥ 4.28 (running)
- [ ] Ollama installed — https://ollama.com/download
- [ ] Node.js 20+ (`node -v`)
- [ ] Python 3.11+ (`python3 --version`)
- [ ] 16 GB RAM minimum (Mistral-7B uses ~6 GB)
- [ ] 20 GB free disk (models + Docker volumes)

### For Production
- [ ] Linux server (Ubuntu 22.04 LTS recommended)
- [ ] 32 GB RAM, 8+ CPU cores, NVIDIA GPU (RTX 3090+) preferred
- [ ] Docker + Docker Compose v2 installed
- [ ] Domain name with DNS A record pointing to server
- [ ] SSL certificate (Certbot / Let's Encrypt)
- [ ] Firewall: ports 80, 443 open; 8000/5173 internal only

---

## 2. Local Demo (Fastest Path)

> Estimated setup time: **15–20 minutes** on first run (model download). Subsequent runs: < 2 minutes.

### Step 1 — Clone & configure
```bash
git clone https://github.com/NeoOne601/Ventro.git
cd Ventro/mas-vgfr
cp backend/.env.example backend/.env
```

> The default `.env` is pre-configured for Docker Compose — no changes needed for local demo.

---

### Step 2 — Pull the LLM model
```bash
ollama pull mistral:7b-instruct
```
This downloads ~4 GB. Run once — model is cached permanently.

**Lighter alternative (faster, less RAM):**
```bash
ollama pull phi3:mini          # 2.3 GB, uses ~2 GB RAM — adequate for demos
```
Then update `backend/.env`:
```
OLLAMA_MODEL_NAME=phi3:mini
```

---

### Step 3 — Start all backend services
```bash
cd mas-vgfr/infra
docker compose up -d
```

Services started:
| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Audit session storage |
| MongoDB | 27017 | Parsed documents + workpapers |
| Qdrant | 6333 | Vector similarity search |
| Redis | 6379 | WebSocket pub/sub |
| Backend API | 8000 | FastAPI application |

Wait ~15 seconds for databases to initialize, then verify:
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","service":"MAS-VGFR",...}
```

---

### Step 4 — Start the frontend
```bash
cd mas-vgfr/frontend
npm install        # first time only
npm run dev
```

Open **http://localhost:5173** in your browser.

---

### Step 5 — Demo walkthrough

1. **Upload Documents** → Navigate to the Upload page
2. Drop 3 sample PDFs (PO, GRN, Invoice) — use any financial PDFs or generate samples:
   ```bash
   # Generate synthetic test documents (if synthetic data pipeline is built)
   # For now, use any PO/GRN/Invoice PDFs from your files
   ```
3. Click **Start AI Reconciliation**
4. Watch the **live agent pipeline** stream across the screen
5. View the **Interactive Audit Workpaper** — click any highlighted value to jump to the source PDF location
6. Check **Analytics** dashboard for session metrics

---

### Optional: API Docs (great for demos to developers)
Open **http://localhost:8000/api/docs** — full interactive Swagger UI.

---

## 3. Sharing Locally Over the Web (Ngrok)

> Share your local demo with anyone over the internet instantly — **no deployment needed**.  
> Best for: quick investor/client demos, remote team walkthroughs.

### Setup (one time)
```bash
# Install ngrok
brew install ngrok/ngrok/ngrok      # macOS
# or: https://ngrok.com/download

# Create a free account at https://ngrok.com (no credit card)
# Copy your authtoken from the dashboard:
ngrok config add-authtoken <your_token>
```

### Start the tunnel
```bash
# Terminal 1: make sure docker compose and npm run dev are running (Steps 3 & 4 above)

# Terminal 2: expose the backend
ngrok http 8000
# → Forwarding: https://abc123.ngrok-free.app → localhost:8000

# Terminal 3: expose the frontend
ngrok http 5173
# → Forwarding: https://xyz456.ngrok-free.app → localhost:5173
```

Share `https://xyz456.ngrok-free.app` — anyone in the world can access the full Ventro demo from their browser. No installation required on their end.

**Free ngrok limits:** 1 tunnel concurrent on free plan. Upgrade to ngrok Basic ($8/mo) for multiple simultaneous tunnels, or use localtunnel as an alternative:
```bash
npx localtunnel --port 5173   # completely free, no account needed
```

---

## 4. Free Cloud Deployment (Zero-Cost Public Demo)

> Deploy a fully functional Ventro instance publicly with **no credit card and no subscriptions**.

### Architecture for Free Tier

```
Browser
  │
  ▼
Vercel (frontend)  ──────────────────────────────► FREE
  │ API calls
  ▼
Render.com (FastAPI backend)  ────────────────────► FREE (750 hrs/month)
  │
  ├── Qdrant Cloud (vector DB)  ────────────────── FREE (1 GB cluster)
  ├── Supabase (PostgreSQL) ──────────────────────► FREE (500 MB)
  ├── MongoDB Atlas (document store)  ────────────► FREE (512 MB)
  ├── Upstash Redis (pub/sub)  ────────────────────► FREE (10k cmd/day)
  └── Groq API (LLM inference, replaces Ollama) ──► FREE (30 req/min, 6k tok/s)
```

**Total monthly cost: $0.00**

> **Why Groq instead of Ollama?** Cloud environments can't run Ollama's local LLM server (no GPU, insufficient RAM on free tiers). Groq provides blazing-fast Mistral/Llama inference for free and requires only an API key — no subscription needed.

---

### Step-by-Step Free Cloud Setup

#### A. Create free accounts (all no credit card)

| Service | Sign up | Purpose |
|---------|---------|---------|
| [Vercel](https://vercel.com) | GitHub login | Frontend hosting |
| [Render.com](https://render.com) | GitHub login | Backend API hosting |
| [Qdrant Cloud](https://cloud.qdrant.io) | GitHub login | Vector database |
| [Supabase](https://supabase.com) | GitHub login | PostgreSQL |
| [MongoDB Atlas](https://mongodb.com/atlas) | GitHub login | Document store |
| [Upstash](https://upstash.com) | GitHub login | Redis |
| [Groq](https://console.groq.com) | GitHub login | LLM API (free) |

---

#### B. Collect your credentials

After signing up, collect:

```bash
GROQ_API_KEY=gsk_xxxx                              # from console.groq.com
DATABASE_URL=postgresql://user:pass@host:5432/db   # from Supabase dashboard
MONGO_URL=mongodb+srv://user:pass@cluster/db       # from Atlas dashboard
REDIS_URL=rediss://default:pass@host:6379          # from Upstash dashboard
QDRANT_URL=https://xxx.us-east4-0.gcp.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-api-key
```

---

#### C. Add Groq support to the backend

Create `backend/src/infrastructure/llm/groq_client.py`:

```python
"""Groq API client — drop-in replacement for OllamaClient."""
import httpx
from ..domain.interfaces import ILLMClient

class GroqClient(ILLMClient):
    def __init__(self, api_key: str, model: str = "mixtral-8x7b-32768"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"

    async def complete(self, prompt: str, temperature=0.0, max_tokens=2048) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        # Use embedding endpoint or fallback to hash-based vector
        import hashlib, struct
        h = hashlib.sha256(prompt.encode()).digest()
        return [struct.unpack('f', h[i:i+4])[0] for i in range(0, 64, 4)]
```

Update `backend/src/presentation/dependencies.py` to select client based on env:
```python
def get_llm() -> ILLMClient:
    settings = get_settings()
    if settings.groq_api_key:
        from ..infrastructure.llm.groq_client import GroqClient
        return GroqClient(api_key=settings.groq_api_key)
    return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model_name)
```

---

#### D. Deploy backend to Render.com

1. Go to [render.com/dashboard](https://dashboard.render.com) → **New Web Service**
2. Connect your **NeoOne601/Ventro** GitHub repo
3. Settings:
   ```
   Root Directory:    mas-vgfr/backend
   Build Command:     pip install -e "."
   Start Command:     uvicorn src.presentation.main:app --host 0.0.0.0 --port $PORT
   Instance Type:     Free
   ```
4. Add all environment variables from Step B above
5. Click **Create Web Service** → wait ~5 minutes
6. Your backend is live at: `https://ventro-api.onrender.com`

> **Note:** Render free tier spins down after 15 minutes of inactivity (cold start ~30s). This is fine for demos.

---

#### E. Deploy frontend to Vercel

1. Go to [vercel.com/new](https://vercel.com/new) → Import **NeoOne601/Ventro**
2. Settings:
   ```
   Root Directory:    mas-vgfr/frontend
   Framework Preset:  Vite
   Build Command:     npm run build
   Output Directory:  dist
   ```
3. Add environment variable:
   ```
   VITE_API_BASE_URL=https://ventro-api.onrender.com
   ```
4. Update `frontend/vite.config.ts` proxy to use env variable for production:
   ```typescript
   server: {
     proxy: {
       '/api': { target: process.env.VITE_API_BASE_URL || 'http://localhost:8000' }
     }
   }
   ```
5. Click **Deploy** → frontend live at: `https://ventro.vercel.app`

---

#### F. Share the URL

Send anyone: **`https://ventro.vercel.app`**

They can use the full Ventro demo from any browser on any device.  
No install. No subscription. No credit card. **Permanently free.**

---

## 5. Production Go-Live (Self-Hosted)

> For organisations deploying on-premise with full data sovereignty.

### Infrastructure Spec

```
Recommended minimum production server:
  CPU:    16 cores (AMD EPYC or Intel Xeon)
  RAM:    64 GB
  GPU:    NVIDIA RTX 4090 or A100 (for Ollama GPU inference)
  Disk:   500 GB NVMe SSD
  OS:     Ubuntu 22.04 LTS
  Network: 1 Gbps uplink
```

### Step 1 — Server setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin

# Install NVIDIA Container Toolkit (for GPU Ollama)
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-docker2
sudo systemctl restart docker
```

### Step 2 — Clone and configure
```bash
git clone https://github.com/NeoOne601/Ventro.git
cd Ventro/mas-vgfr/backend
cp .env.example .env
vim .env   # set all production values (strong passwords, real domain, etc.)
```

**Key production `.env` changes:**
```bash
APP_ENV=production
APP_SECRET_KEY=<generate: openssl rand -hex 32>
DATABASE_URL=postgresql+asyncpg://ventro:STRONG_PASS@postgres:5432/ventro_prod
ALLOWED_ORIGINS=["https://yourdomain.com"]
```

### Step 3 — Build and deploy
```bash
cd mas-vgfr/infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**Production overrides** (`docker-compose.prod.yml`):
```yaml
services:
  backend:
    restart: always
    environment:
      - APP_ENV=production
    deploy:
      replicas: 2   # Load balanced
  
  frontend:
    restart: always
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/prod.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

### Step 4 — SSL with Let's Encrypt
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
# Auto-renews every 90 days
```

### Step 5 — Pull production LLM
```bash
docker exec mas_vgfr_ollama ollama pull mistral:7b-instruct-q4_K_M
# Q4 quantized: 4.1 GB, near-identical quality, faster on GPU
```

### Step 6 — Verify production health
```bash
curl https://yourdomain.com/health
# {"status":"healthy","service":"MAS-VGFR","version":"1.0.0",...}

curl https://yourdomain.com/api/docs
# Should load Swagger UI
```

---

## 6. Environment Variable Reference

| Variable | Local | Production | Free Cloud |
|----------|-------|-----------|------------|
| `APP_ENV` | `development` | `production` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://mas_vgfr_user:mas_vgfr_password@postgres:5432/mas_vgfr` | Strong password | Supabase URL |
| `MONGO_URL` | `mongodb://mas_vgfr_user:...@mongodb:27017/...` | Strong password | Atlas URL |
| `REDIS_URL` | `redis://redis:6379/0` | `redis://redis:6379/0` | Upstash URL |
| `QDRANT_HOST` | `qdrant` | `qdrant` | Qdrant Cloud URL |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | `http://ollama:11434` | *(not used)* |
| `GROQ_API_KEY` | *(optional)* | *(optional)* | **Required** |
| `ALLOWED_ORIGINS` | `["http://localhost:5173"]` | `["https://yourdomain.com"]` | `["https://ventro.vercel.app"]` |
| `APP_SECRET_KEY` | `dev-secret-key` | **Must be random 32-byte hex** | Random hex |

---

## 7. Health Check & Smoke Test

Run after every deployment:

```bash
# 1. System health
curl https://yourdomain.com/health

# 2. Service health detail
curl https://yourdomain.com/api/v1/analytics/health | python3 -m json.tool

# 3. Upload a test document
curl -X POST https://yourdomain.com/api/v1/documents/upload \
  -F "file=@test_po.pdf" | python3 -m json.tool

# 4. Check Qdrant
curl http://localhost:6333/collections
# Should show "mas_vgfr_docs" collection

# 5. Verify Ollama (local)
curl http://localhost:11434/api/tags
# Should list mistral:7b-instruct
```

---

## 8. Rollback Procedure

```bash
# If a deployment fails, roll back to previous commit:
cd Ventro/mas-vgfr

# Find the last good commit
git log --oneline -10

# Revert
git checkout <last-good-commit-hash>

# Redeploy
cd infra
docker compose up -d --build backend

# For Render/Vercel free cloud: use their dashboard's
# "Rollback to previous deploy" one-click button
```

---

## Summary: Recommended Path Per Use Case

| Use Case | Approach | Time to Live |
|----------|----------|-------------|
| **Quick demo (yourself)** | Local Docker Compose + `npm run dev` | 15 min |
| **Show to remote client/investor** | Local + Ngrok tunnel | 20 min |
| **Public link anyone can try** | Vercel + Render + Groq (free) | 1–2 hours |
| **Production enterprise** | Self-hosted Ubuntu server with GPU | 2–4 hours |
