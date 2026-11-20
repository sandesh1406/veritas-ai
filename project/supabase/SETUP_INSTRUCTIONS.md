# VERITAS AI - Supabase Setup Instructions

## Prerequisites
- Supabase project named `veritas-ai` already created
- Access to Supabase Dashboard SQL Editor

## Step 1: Get Project Credentials
1. Go to Supabase Dashboard → Project Settings → API
2. Copy **Project URL** and **anon public** key
3. Create `.env` in `project/` folder:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

## Step 2: Run Migration
1. Go to Supabase Dashboard → SQL Editor
2. Click "New query"
3. Copy entire contents of `supabase/migrations/20261119055016_create_veritas_auth_data_storage.sql`
4. Paste and click **Run**
5. Verify no errors

## Step 3: Verify Tables Created
Run this verification query in SQL Editor:

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN (
  'profiles', 'documents', 'claims', 'citations', 
  'publications', 'evidence', 'verifications', 
  'reports', 'review_history'
)
ORDER BY table_name;
```

Expected: 9 rows

## Step 4: Verify RLS Enabled
```sql
SELECT schemaname, tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN (
  'profiles', 'documents', 'claims', 'citations', 
  'publications', 'evidence', 'verifications', 
  'reports', 'review_history'
)
ORDER BY tablename;
```

Expected: `rowsecurity = true` for all 9 tables

## Step 5: Verify Storage Buckets
```sql
SELECT id, name, public, file_size_limit, allowed_mime_types 
FROM storage.buckets 
WHERE id IN ('research-documents', 'verification-reports');
```

Expected: 2 rows, both `public = false`, 20MB limit, PDF/DOCX MIME types

## Step 6: Test Auth & Upload (Frontend)
1. `cd project && npm install && npm run dev`
2. Sign up new account
3. Go to `/verify` and upload a PDF/DOCX (<20MB)
4. Should redirect to `/workspace` with document listed

## Troubleshooting
- **Migration fails**: Check for existing tables - migration uses `IF NOT EXISTS` and `ON CONFLICT`
- **RLS blocks upload**: Ensure you're signed in; bucket policies require `auth.uid()` as first folder
- **Auth errors**: Verify `.env` values match Supabase dashboard exactly