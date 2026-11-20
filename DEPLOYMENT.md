# VERITAS AI - Deployment Guide

## Overview

This guide covers deploying the VERITAS AI application:
- **Frontend**: React + Vite + TypeScript → Vercel
- **Backend**: FastAPI + Python → Render (or similar)
- **Database/Storage**: Supabase (PostgreSQL + Auth + Storage)
- **AI**: Google Gemini API

---

## Prerequisites

- GitHub account
- Vercel account
- Render account (or Railway, Fly.io, Railway)
- Supabase account
- Google Cloud / Google AI Studio account (for Gemini API)
- Domain name (optional but recommended)

---

## 1. Supabase Production Setup

### 1.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Note down:
   - Project URL: `https://your-project-ref.supabase.co`
   - Anon (public) key
   - Service Role key (keep secret!)

### 1.2 Run Database Migrations

In Supabase Dashboard → SQL Editor, run these files in order:

1. `backend/supabase_schema.sql` - Creates all tables, indexes, RLS policies
2. `backend/supabase_functions.sql` - Creates helper RPC functions
3. `backend/app/services/background_processor.py` - Contains SQL for `processing_jobs` table and pg_cron setup (copy SQL sections)

### 1.3 Configure Storage Buckets

In Supabase Dashboard → Storage:

1. Create bucket: `research-documents` (private)
2. Create bucket: `verification-reports` (private)
3. Add storage policies (see `supabase_schema.sql` for policies)

### 1.4 Configure Authentication

In Supabase Dashboard → Authentication → Providers:
1. Enable Email/Password
2. (Optional) Enable OAuth providers (Google, GitHub, etc.)
3. Set Site URL: `https://your-frontend-domain.vercel.app`
4. Add Redirect URLs:
   - `https://your-frontend-domain.vercel.app/auth/callback`
   - `https://your-frontend-domain.vercel.app/reset-password`

---

## 2. Backend Deployment (Render)

### 2.1 Create Render Web Service

1. Connect GitHub repo to Render
2. Create **Web Service**:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Region: Choose closest to your users
   - Instance Type: Starter (or higher for production)

### 2.2 Environment Variables (Render Dashboard)

| Variable | Value | Notes |
|----------|-------|-------|
| `SUPABASE_URL` | `https://your-project.supabase.co` | From Supabase |
| `SUPABASE_ANON_KEY` | `your-anon-key` | From Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | `your-service-role-key` | **Keep secret!** |
| `GEMINI_API_KEY` | `your-gemini-key` | From Google AI Studio |
| `AI_PROVIDER` | `gemini` | |
| `GEMINI_MODEL` | `gemini-3.8-flash` | |
| `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` | **Production frontend URL** |
| `API_HOST` | `0.0.0.0` | |
| `API_PORT` | `10000` | Render uses `$PORT` |
| `AI_TIMEOUT_SECONDS` | `120` | For large PDFs |
| `AI_MAX_RETRIES` | `3` | |
| `AI_RETRY_BACKOFF_BASE` | `2.0` | |

### 2.3 Render Configuration

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Auto-Deploy**: Enabled on push to main
- **Health Check Path**: `/health`

### 2.4 Persistent Storage (Optional)

For background job queue, consider adding Redis or using Supabase pg_cron (already configured in `background_processor.py`).

---

## 3. Frontend Deployment (Vercel)

### 3.1 Vercel Project Setup

1. Import GitHub repository in Vercel
2. Framework Preset: **Vite**
3. Root Directory: `project`
4. Build Command: `npm run build`
5. Output Directory: `dist`

### 3.2 Environment Variables (Vercel Dashboard)

| Variable | Value |
|----------|-------|
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | `your-anon-key` |
| `VITE_API_BASE_URL` | `https://your-backend.onrender.com` |

### 3.3 Vercel Configuration

**Build Settings:**
- Build Command: `npm run build`
- Output Directory: `dist`
- Install Command: `npm install`

**Framework Preset**: Vite

**Node.js Version**: 20.x (or 18.x)

---

## 4. Gemini API Configuration

### 4.1 Get API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API Key
3. Add to backend environment variables as `GEMINI_API_KEY`

### 4.2 Model Configuration

Current model: `gemini-3.8-flash` (configured in `backend/.env` as `GEMINI_MODEL`)

**Model Options:**
- `gemini-1.5-flash` - Fast, cost-effective
- `gemini-1.5-pro` - Higher quality, more expensive
- `gemini-3.8-flash` - Latest fast model

Update `GEMINI_MODEL` in backend `.env` if changing models.

---

## 5. Production Environment Variables Summary

### Backend (`.env`)

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# API
API_HOST=0.0.0.0
API_PORT=10000  # Render uses $PORT

# AI Provider
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-3.8-flash
ANTHROPIC_API_KEY=  # Optional fallback
CLAUDE_MODEL=claude-3-5-sonnet-20241022

# External APIs
CROSSREF_BASE_URL=https://api.crossref.org
OPENALEX_BASE_URL=https://api.openalex.org
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
SEMANTIC_SCHOLAR_API_KEY=  # Optional

# Processing
MAX_FILE_SIZE_MB=20
CHUNK_SIZE=4000
MAX_CLAIMS_PER_DOC=50

# AI Request
AI_TIMEOUT_SECONDS=120
AI_MAX_RETRIES=3
AI_RETRY_BACKOFF_BASE=2.0

# CORS - Production frontend URL
ALLOWED_ORIGINS=https://your-app.vercel.app
```

### Frontend (`.env.production`)

```bash
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_BASE_URL=https://your-backend.onrender.com
```

---

## 6. Domain & DNS Configuration

### 6.1 Custom Domain (Optional)

1. **Frontend (Vercel)**:
   - Vercel Dashboard → Domains → Add `app.yourdomain.com`
   - Add CNAME: `app` → `cname.vercel-dns.com`

2. **Backend (Render)**:
   - Render Dashboard → Settings → Custom Domains
   - Add `api.yourdomain.com`
   - Add CNAME: `api` → `your-app.onrender.com`

3. **Update Environment Variables**:
   - `ALLOWED_ORIGINS=https://app.yourdomain.com`
   - `VITE_API_BASE_URL=https://api.yourdomain.com`

---

## 7. Supabase Production Checklist

- [ ] RLS policies enabled on all tables
- [ ] Storage buckets created with correct policies
- [ ] Auth providers configured
- [ ] Site URL and redirect URLs updated
- [ ] Storage buckets: `research-documents`, `verification-reports`
- [ ] pg_cron extension enabled (for background jobs)
- [ ] `processing_jobs` table created (from `background_processor.py`)

---

## 7. Pre-Deployment Checklist

- [ ] All `.env` files use production values
- [ ] No hardcoded `localhost` URLs in code
- [ ] `ALLOWED_ORIGINS` set to production frontend URL
- [ ] `VITE_API_BASE_URL` points to production backend
- [ ] Supabase Service Role Key only in backend
- [ ] No secrets in frontend code
- [ ] Error handling doesn't expose stack traces in production
- [ ] PDF upload size limit enforced (20MB)
- [ ] API timeouts configured (120s for AI)

---

## 8. Post-Deployment Verification

1. **Health Checks**:
   - `GET https://your-backend.onrender.com/health` → `{"status":"healthy"}`
   - `GET https://your-backend.onrender.com/health/supabase` → All connected

2. **Frontend Loads**:
   - `https://your-app.vercel.app` loads without console errors
   - Supabase auth works (signup/login)

3. **Full Pipeline Test**:
   - Upload PDF → Process → Check Analysis Workspace
   - Verify claims, citations, evidence, verdicts display
   - Generate report → Download PDF

4. **Background Jobs**:
   - Upload large PDF → Check status → `queued` → `processing` → `completed`

---

## 9. Monitoring & Maintenance

### Logging

- Render: View logs in Dashboard → Logs
- Supabase: Dashboard → Logs → API/Database/Auth
- Vercel: Dashboard → Functions → Logs

### Monitoring

- Render: Metrics → CPU/Memory/Response Time
- Supabase: Dashboard → Reports → API Usage
- Vercel: Analytics → Web Vitals

### Backup

- Supabase: Daily automatic backups (Pro plan)
- Manual: `pg_dump` for PostgreSQL
- Export Supabase data: Dashboard → Database → Backup

---

## 10. Rollback Plan

1. **Frontend**: Vercel → Deployments → Promote previous
2. **Backend**: Render → Deploys → Rollback
3. **Database**: Supabase → Point-in-time recovery (Pro) or manual restore

---

## 11. Cost Estimation (Monthly)

| Service | Plan | Estimated Cost |
|---------|------|----------------|
| Supabase | Pro | $25/mo |
| Render (Backend) | Starter | $7/mo |
| Vercel (Frontend) | Pro | $20/mo |
| Google Gemini API | Pay-as-you-go | ~$5-50/mo |
| **Total** | | **~$57-102/mo** |

---

## Appendix: Useful Commands

```bash
# Backend local development
cd backend
cp .env.example .env
# Edit .env with local values
uvicorn app.main:app --reload --port 8000

# Frontend local development
cd project
cp .env.example .env
npm install
npm run dev

# Database migrations (Supabase CLI)
supabase db push

# View backend logs (Render)
render logs -s your-service-name

# View frontend logs (Vercel)
vercel logs your-deployment-url
```

---

## Support & Troubleshooting

| Issue | Solution |
|-------|----------|
| CORS errors | Check `ALLOWED_ORIGINS` matches frontend URL exactly |
| 401 Unauthorized | Check Supabase keys, JWT validation |
| PDF timeout | Increase `AI_TIMEOUT_SECONDS`, use background jobs |
| Build fails | Check Node.js version (20.x), clear `node_modules` |
| Supabase RLS errors | Check policies, ensure user owns document |

---

## Support

- Supabase Docs: https://supabase.com/docs
- Render Docs: https://render.com/docs
- Vercel Docs: https://vercel.com/docs
- Google Gemini API: https://ai.google.dev/docs
- Rollup/Vite: https://vitejs.dev/guide/

---

*Last Updated: 2024*
*VERITAS AI - Research Integrity Platform*