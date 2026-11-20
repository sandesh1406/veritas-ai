# VERITAS AI - FastAPI Backend

## Overview

VERITAS AI is a scientific claim verification system that:
- Extracts claims and citations from research documents (PDF/DOCX)
- Retrieves publication metadata from multiple sources (Crossref, OpenAlex, Semantic Scholar)
- Extracts evidence passages from open-access publications
- Uses AI (Gemini or Claude) to verify claims against evidence
- Generates comprehensive PDF reports with full traceability

## Quick Start

### 1. Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Required configuration:**
- `SUPABASE_URL` - Your Supabase project URL (e.g., `https://abcdefgh.supabase.co`)
- `SUPABASE_ANON_KEY` - Supabase anonymous key (from Project Settings → API)
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key (NEVER expose in frontend)
- `GEMINI_API_KEY` - Google Gemini API key (from Google AI Studio)
- `AI_PROVIDER` - Set to `"gemini"` (default) or `"anthropic"`

**Optional:**
- `ANTHROPIC_API_KEY` - For Claude fallback
- `SEMANTIC_SCHOLAR_API_KEY` - For enhanced Semantic Scholar lookups
- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins (default: `http://localhost:5173,http://localhost:3000`)

### 3. Set Up Supabase Database

**Step 3a: Run the schema migration**

In Supabase Dashboard → SQL Editor, run `supabase_schema.sql`:
```sql
-- Copy and paste the entire contents of backend/supabase_schema.sql
-- This creates all tables, indexes, RLS policies, and triggers
```

**Step 3b: Run the helper functions**

In Supabase Dashboard → SQL Editor, run `supabase_functions.sql`:
```sql
-- Copy and paste the entire contents of backend/supabase_functions.sql
-- This creates RPC functions for counting and the verdict constraint
```

**Step 3c: Create Storage Buckets**

In Supabase Dashboard → Storage:
1. Create bucket `research-documents` (private)
2. Create bucket `verification-reports` (private)

**Step 3d: Configure Storage Policies**

For bucket `research-documents`:
```sql
-- Allow users to upload to their own folder
CREATE POLICY "Users can upload own documents"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'research-documents' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Allow users to read their own documents
CREATE POLICY "Users can read own documents"
ON storage.objects FOR SELECT
USING (bucket_id = 'research-documents' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Allow users to delete their own documents
CREATE POLICY "Users can delete own documents"
ON storage.objects FOR DELETE
USING (bucket_id = 'research-documents' AND auth.uid()::text = (storage.foldername(name))[1]);
```

For bucket `verification-reports`:
```sql
-- Allow users to upload reports
CREATE POLICY "Users can upload own reports"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'verification-reports' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Allow users to read their own reports
CREATE POLICY "Users can read own reports"
ON storage.objects FOR SELECT
USING (bucket_id = 'verification-reports' AND auth.uid()::text = (storage.foldername(name))[1]);
```

### 4. Configure Authentication

In Supabase Dashboard → Authentication → Providers:
1. Enable Email/Password authentication
2. (Optional) Enable OAuth providers (Google, GitHub, etc.)
3. Set Site URL to your frontend URL (e.g., `http://localhost:5173`)
4. Add Redirect URLs for password reset: `http://localhost:5173/reset-password`

### 5. Start Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/health/supabase` | Supabase connectivity check |
| GET | `/ai/provider` | Get AI provider info |
| POST | `/documents/upload` | Upload a research document |
| POST | `/documents/{id}/process` | Start document processing |
| GET | `/documents/{id}/status` | Get processing status |
| GET | `/documents/{id}/results` | Get full verification results |
| POST | `/documents/{id}/report` | Generate PDF verification report |
| GET | `/documents/{id}/report/download` | Download PDF report |
| GET | `/documents` | List user's documents |
| GET | `/reports` | List user's reports |

All endpoints require `Authorization: Bearer <user_access_token>` header.

## Architecture

```
app/
├── core/           # Config, Supabase clients
├── models/         # Pydantic schemas
├── services/       # Business logic
│   ├── document_processor.py  # PDF/DOCX extraction, claim/citation detection
│   ├── research_retrieval.py  # Crossref, OpenAlex, Semantic Scholar
│   ├── evidence_extractor.py  # Evidence passage extraction
│   ├── ai_verification.py     # AI verification service
│   ├── ai_provider.py         # Provider abstraction
│   ├── gemini_provider.py     # Gemini implementation
│   ├── anthropic_provider.py  # Claude implementation
│   └── report_generator.py    # PDF report generation
└── main.py         # FastAPI routes
```

## Processing Pipeline

1. **Document Upload** - File uploaded to Supabase Storage (`research-documents` bucket)
2. **Document Download** - Fetched from storage for processing
3. **Text Extraction** - PyMuPDF (PDF) / python-docx (DOCX) with page numbers
4. **Claim Extraction** - Heuristic patterns for scientific claims
5. **Citation Extraction** - Bibliography parsing with reference numbers
6. **Claim→Citation Mapping** - Match reference numbers in text to bibliography
7. **Publication Retrieval** - Crossref → OpenAlex → Semantic Scholar (by DOI then title)
8. **Evidence Extraction** - Abstracts + full text where open access
9. **AI Verification** - AI compares claims vs evidence → 6 verdicts + confidence
10. **Report Generation** - PDF with full traceability (stored in `verification-reports` bucket)

## Verification Verdicts

- **SUPPORTED**: The evidence directly and fully supports the claim
- **PARTIALLY_SUPPORTED**: The evidence supports some aspects but not all
- **UNSUPPORTED**: The evidence does not support the claim
- **CONTRADICTORY**: The evidence directly contradicts the claim
- **POTENTIALLY_OUTDATED**: Claim was supported but newer evidence suggests otherwise
- **NEEDS_REVIEW**: Insufficient evidence or could not be evaluated

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_ai_provider.py -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

Expected: 48 tests passing

## Security

- All endpoints require `Authorization: Bearer <user_access_token>`
- Service role key used ONLY in backend for admin operations
- User ownership verified before any document access
- JWT validation via Supabase JWKS (local validation with fallback)
- RLS policies enforce user isolation at database level
- No credentials ever exposed in frontend code
- CORS configured via environment variable

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | Yes | - | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | - | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | - | Supabase service role key |
| `AI_PROVIDER` | Yes | "gemini" | "gemini" or "anthropic" |
| `GEMINI_API_KEY` | Conditional | - | Gemini API key (required if AI_PROVIDER=gemini) |
| `GEMINI_MODEL` | No | "gemini-3.8-flash" | Gemini model name |
| `ANTHROPIC_API_KEY` | Conditional | - | Claude API key (required if AI_PROVIDER=anthropic) |
| `CLAUDE_MODEL` | No | "claude-3-5-sonnet-20241022" | Claude model name |
| `SEMANTIC_SCHOLAR_API_KEY` | No | - | Semantic Scholar API key |
| `MAX_FILE_SIZE_MB` | No | 20 | Maximum document size |
| `MAX_CLAIMS_PER_DOC` | No | 50 | Maximum claims to extract |
| `AI_TIMEOUT_SECONDS` | No | 30 | AI request timeout |
| `AI_MAX_RETRIES` | No | 3 | AI retry attempts |
| `AI_RETRY_BACKOFF_BASE` | No | 2.0 | Exponential backoff base |
| `ALLOWED_ORIGINS` | No | "http://localhost:5173,http://localhost:3000" | CORS origins |

## Files Created/Modified for Integration Readiness

### New Files Created:
- `backend/supabase_schema.sql` - Complete database schema with RLS policies
- `backend/supabase_functions.sql` - RPC functions and constraints (already existed, verified)

### Modified Files:
- `backend/app/core/config.py` - Set `GEMINI_MODEL` to `gemini-3.8-flash`, added `ALLOWED_ORIGINS`
- `backend/app/main.py` - CORS configuration now environment-driven
- `backend/.env.example` - Updated model name and added CORS variable
- `backend/README.md` - Complete setup instructions with Supabase Dashboard steps

### Existing Files (Verified Complete):
- `backend/app/services/gemini_provider.py` - Uses official `google-genai` SDK with structured JSON responses
- `backend/app/services/ai_provider.py` - All 6 verdicts validated, proper error handling
- `backend/app/core/supabase_client.py` - JWT validation via JWKS with fallback, admin/user clients
- `backend/app/services/storage_service.py` - Document and report storage operations
- `backend/app/services/report_generator.py` - PDF generation with all verdict types
- `backend/app/services/evidence_extractor.py` - Multi-factor relevance scoring
- `backend/app/services/research_retrieval.py` - Deduplication across 3 sources
- `backend/app/services/document_processor.py` - Enhanced claim/citation extraction

## Remaining Manual Setup Steps

1. **Create Supabase Project** at https://supabase.com
2. **Run `supabase_schema.sql`** in Supabase SQL Editor
3. **Run `supabase_functions.sql`** in Supabase SQL Editor
4. **Create storage buckets** `research-documents` and `verification-reports`
5. **Configure storage policies** (see Step 3d above)
6. **Configure Auth** (see Step 4 above)
7. **Get API keys**:
   - Supabase: Project Settings → API
   - Gemini: https://aistudio.google.com/apikey
8. **Create `.env`** from `.env.example` with actual values
9. **Start backend**: `uvicorn app.main:app --reload`
10. **Start frontend**: `npm run dev` (in project root)

## Troubleshooting

### API Key Errors
- Ensure your AI provider API key is valid
- Check quota limits on your Gemini/Claude account

### Supabase Connection Issues
- Verify your Supabase URL and keys
- Check that your service role key has correct permissions
- Ensure storage buckets exist and policies are applied

### JWT Validation Fails
- Ensure `SUPABASE_URL` is correct (JWKS fetched from `https://{project}.supabase.co/auth/v1/.well-known/jwks.json`)
- Check that the access token is from the same Supabase project

### CORS Errors
- Set `ALLOWED_ORIGINS` in `.env` to include your frontend URL
- Example: `ALLOWED_ORIGINS=http://localhost:5173,https://yourdomain.com`

### Processing Timeout
- Large documents may need more time
- Check `AI_TIMEOUT_SECONDS` setting
- Monitor logs for specific errors

## License

MIT License - See LICENSE file for details.