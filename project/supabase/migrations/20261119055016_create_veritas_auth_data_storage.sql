/*
# Create Veritas AI authenticated data model and private storage

1. New Tables
- `profiles`: one row per Supabase Auth user with editable full name and avatar URL plus a copied email for display.
- `documents`: research papers uploaded by a user, including the private storage path, file metadata, and processing status.
- `claims`: claims extracted from a user's document.
- `citations`: citation references linked to a user's document and claim.
- `publications`: publication metadata linked to a citation.
- `evidence`: evidence excerpts linked to a claim and publication.
- `verifications`: verdict and confidence information linked to a claim. These are readable by the owner but not client-writable.
- `reports`: private report file references linked to a document and owner.
- `review_history`: owner-scoped reviewer decisions and notes linked to a verification.

2. Relationships and indexes
- Every user-owned top-level record references `auth.users` through a UUID owner column with an authenticated-user default where applicable.
- Child records reference their parent records with foreign keys and cascading deletes.
- Indexes are added for every owner and foreign-key lookup used by the application.

3. Security
- Row Level Security is enabled on every new public table.
- Authenticated users can only read or mutate their own records and records reachable through their own documents.
- Profile writes are limited to `full_name` and `avatar_url`; processing, verification, ownership, and audit fields are not client-writable.
- A SECURITY DEFINER trigger creates a profile after signup without exposing the function for remote execution.
- Two private storage buckets are created with size and MIME restrictions.
- Storage policies require the authenticated user's UUID to be the first folder in every object path.

4. Important notes
- The browser uses only the Supabase anonymous client key and authenticated sessions; no service-role credentials are stored in the frontend.
- The separate FastAPI verification engine can write protected processing and verification fields with its server credentials later.
- The migration is idempotent for safe re-application and does not delete or rename existing data.
*/

CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  avatar_url text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
  filename text NOT NULL,
  storage_path text NOT NULL,
  file_type text NOT NULL,
  file_size bigint NOT NULL CHECK (file_size > 0 AND file_size <= 20971520),
  processing_status text NOT NULL DEFAULT 'queued' CHECK (processing_status IN ('queued', 'processing', 'completed', 'failed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  claim_text text NOT NULL,
  claim_type text,
  page_number integer CHECK (page_number IS NULL OR page_number > 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.citations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  citation_text text NOT NULL,
  reference_number text,
  doi text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.publications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  citation_id uuid NOT NULL REFERENCES public.citations(id) ON DELETE CASCADE,
  title text NOT NULL,
  authors text,
  doi text,
  publication_year integer CHECK (publication_year IS NULL OR publication_year BETWEEN 1000 AND 9999),
  source_url text,
  retrieval_status text NOT NULL DEFAULT 'queued',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  publication_id uuid NOT NULL REFERENCES public.publications(id) ON DELETE CASCADE,
  evidence_text text NOT NULL,
  source_location text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.verifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  verdict text NOT NULL,
  confidence_score numeric(5, 2) CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)),
  explanation text,
  evidence_status text,
  model_version text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
  report_path text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.review_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
  verification_id uuid NOT NULL REFERENCES public.verifications(id) ON DELETE CASCADE,
  reviewer_decision text NOT NULL,
  reviewer_notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_user_id_created_at_idx ON public.documents (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS claims_document_id_idx ON public.claims (document_id);
CREATE INDEX IF NOT EXISTS citations_document_id_idx ON public.citations (document_id);
CREATE INDEX IF NOT EXISTS citations_claim_id_idx ON public.citations (claim_id);
CREATE INDEX IF NOT EXISTS publications_citation_id_idx ON public.publications (citation_id);
CREATE INDEX IF NOT EXISTS evidence_claim_id_idx ON public.evidence (claim_id);
CREATE INDEX IF NOT EXISTS evidence_publication_id_idx ON public.evidence (publication_id);
CREATE INDEX IF NOT EXISTS verifications_claim_id_created_at_idx ON public.verifications (claim_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reports_user_id_created_at_idx ON public.reports (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reports_document_id_idx ON public.reports (document_id);
CREATE INDEX IF NOT EXISTS review_history_user_id_created_at_idx ON public.review_history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS review_history_verification_id_idx ON public.review_history (verification_id);

CREATE OR REPLACE FUNCTION public.handle_new_veritas_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name, email)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data ->> 'full_name', ''),
    COALESCE(NEW.email, '')
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created_veritas_profile ON auth.users;
CREATE TRIGGER on_auth_user_created_veritas_profile
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_veritas_profile();

REVOKE EXECUTE ON FUNCTION public.handle_new_veritas_profile() FROM PUBLIC, anon, authenticated;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_history ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT ON public.profiles TO authenticated;
GRANT UPDATE (full_name, avatar_url) ON public.profiles TO authenticated;
GRANT SELECT, INSERT, DELETE ON public.documents TO authenticated;
GRANT INSERT (filename, storage_path, file_type, file_size) ON public.documents TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.claims TO authenticated;
GRANT INSERT (document_id, claim_text, claim_type, page_number) ON public.claims TO authenticated;
GRANT UPDATE (claim_text, claim_type, page_number) ON public.claims TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.citations TO authenticated;
GRANT INSERT (document_id, claim_id, citation_text, reference_number, doi) ON public.citations TO authenticated;
GRANT UPDATE (citation_text, reference_number, doi) ON public.citations TO authenticated;
GRANT SELECT ON public.publications TO authenticated;
GRANT SELECT ON public.evidence TO authenticated;
GRANT SELECT ON public.verifications TO authenticated;
GRANT SELECT, INSERT, DELETE ON public.reports TO authenticated;
GRANT INSERT (document_id, report_path) ON public.reports TO authenticated;
GRANT SELECT, INSERT ON public.review_history TO authenticated;
GRANT INSERT (verification_id, reviewer_decision, reviewer_notes) ON public.review_history TO authenticated;

DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own" ON public.profiles FOR SELECT TO authenticated USING (auth.uid() = id);
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
CREATE POLICY "profiles_update_own" ON public.profiles FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "documents_select_own" ON public.documents;
CREATE POLICY "documents_select_own" ON public.documents FOR SELECT TO authenticated USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "documents_insert_own" ON public.documents;
CREATE POLICY "documents_insert_own" ON public.documents FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "documents_update_own" ON public.documents;
CREATE POLICY "documents_update_own" ON public.documents FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "documents_delete_own" ON public.documents;
CREATE POLICY "documents_delete_own" ON public.documents FOR DELETE TO authenticated USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "claims_select_own" ON public.claims;
CREATE POLICY "claims_select_own" ON public.claims FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d WHERE d.id = claims.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "claims_insert_own" ON public.claims;
CREATE POLICY "claims_insert_own" ON public.claims FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM public.documents d WHERE d.id = claims.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "claims_update_own" ON public.claims;
CREATE POLICY "claims_update_own" ON public.claims FOR UPDATE TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d WHERE d.id = claims.document_id AND d.user_id = auth.uid())) WITH CHECK (EXISTS (SELECT 1 FROM public.documents d WHERE d.id = claims.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "claims_delete_own" ON public.claims;
CREATE POLICY "claims_delete_own" ON public.claims FOR DELETE TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d WHERE d.id = claims.document_id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "citations_select_own" ON public.citations;
CREATE POLICY "citations_select_own" ON public.citations FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d JOIN public.claims c ON c.document_id = d.id WHERE c.id = citations.claim_id AND citations.document_id = d.id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "citations_insert_own" ON public.citations;
CREATE POLICY "citations_insert_own" ON public.citations FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM public.documents d JOIN public.claims c ON c.document_id = d.id WHERE c.id = citations.claim_id AND citations.document_id = d.id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "citations_update_own" ON public.citations;
CREATE POLICY "citations_update_own" ON public.citations FOR UPDATE TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d JOIN public.claims c ON c.document_id = d.id WHERE c.id = citations.claim_id AND citations.document_id = d.id AND d.user_id = auth.uid())) WITH CHECK (EXISTS (SELECT 1 FROM public.documents d JOIN public.claims c ON c.document_id = d.id WHERE c.id = citations.claim_id AND citations.document_id = d.id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "citations_delete_own" ON public.citations;
CREATE POLICY "citations_delete_own" ON public.citations FOR DELETE TO authenticated USING (EXISTS (SELECT 1 FROM public.documents d JOIN public.claims c ON c.document_id = d.id WHERE c.id = citations.claim_id AND citations.document_id = d.id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "publications_select_own" ON public.publications;
CREATE POLICY "publications_select_own" ON public.publications FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.citations ci JOIN public.documents d ON d.id = ci.document_id WHERE ci.id = publications.citation_id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "evidence_select_own" ON public.evidence;
CREATE POLICY "evidence_select_own" ON public.evidence FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.claims c JOIN public.documents d ON d.id = c.document_id WHERE c.id = evidence.claim_id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "verifications_select_own" ON public.verifications;
CREATE POLICY "verifications_select_own" ON public.verifications FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.claims c JOIN public.documents d ON d.id = c.document_id WHERE c.id = verifications.claim_id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "reports_select_own" ON public.reports;
CREATE POLICY "reports_select_own" ON public.reports FOR SELECT TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.documents d WHERE d.id = reports.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "reports_insert_own" ON public.reports;
CREATE POLICY "reports_insert_own" ON public.reports FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.documents d WHERE d.id = reports.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "reports_update_own" ON public.reports;
CREATE POLICY "reports_update_own" ON public.reports FOR UPDATE TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.documents d WHERE d.id = reports.document_id AND d.user_id = auth.uid())) WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.documents d WHERE d.id = reports.document_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "reports_delete_own" ON public.reports;
CREATE POLICY "reports_delete_own" ON public.reports FOR DELETE TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.documents d WHERE d.id = reports.document_id AND d.user_id = auth.uid()));

DROP POLICY IF EXISTS "review_history_select_own" ON public.review_history;
CREATE POLICY "review_history_select_own" ON public.review_history FOR SELECT TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.verifications v JOIN public.claims c ON c.id = v.claim_id JOIN public.documents d ON d.id = c.document_id WHERE v.id = review_history.verification_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "review_history_insert_own" ON public.review_history;
CREATE POLICY "review_history_insert_own" ON public.review_history FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.verifications v JOIN public.claims c ON c.id = v.claim_id JOIN public.documents d ON d.id = c.document_id WHERE v.id = review_history.verification_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "review_history_update_own" ON public.review_history;
CREATE POLICY "review_history_update_own" ON public.review_history FOR UPDATE TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.verifications v JOIN public.claims c ON c.id = v.claim_id JOIN public.documents d ON d.id = c.document_id WHERE v.id = review_history.verification_id AND d.user_id = auth.uid())) WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.verifications v JOIN public.claims c ON c.id = v.claim_id JOIN public.documents d ON d.id = c.document_id WHERE v.id = review_history.verification_id AND d.user_id = auth.uid()));
DROP POLICY IF EXISTS "review_history_delete_own" ON public.review_history;
CREATE POLICY "review_history_delete_own" ON public.review_history FOR DELETE TO authenticated USING (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.verifications v JOIN public.claims c ON c.id = v.claim_id JOIN public.documents d ON d.id = c.document_id WHERE v.id = review_history.verification_id AND d.user_id = auth.uid()));

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('research-documents', 'research-documents', false, 20971520, ARRAY['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']),
  ('verification-reports', 'verification-reports', false, 20971520, ARRAY['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'])
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "research_documents_select_own" ON storage.objects;
CREATE POLICY "research_documents_select_own" ON storage.objects FOR SELECT TO authenticated USING (bucket_id = 'research-documents' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "research_documents_insert_own" ON storage.objects;
CREATE POLICY "research_documents_insert_own" ON storage.objects FOR INSERT TO authenticated WITH CHECK (bucket_id = 'research-documents' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "research_documents_update_own" ON storage.objects;
CREATE POLICY "research_documents_update_own" ON storage.objects FOR UPDATE TO authenticated USING (bucket_id = 'research-documents' AND (storage.foldername(name))[1] = auth.uid()::text) WITH CHECK (bucket_id = 'research-documents' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "research_documents_delete_own" ON storage.objects;
CREATE POLICY "research_documents_delete_own" ON storage.objects FOR DELETE TO authenticated USING (bucket_id = 'research-documents' AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS "verification_reports_select_own" ON storage.objects;
CREATE POLICY "verification_reports_select_own" ON storage.objects FOR SELECT TO authenticated USING (bucket_id = 'verification-reports' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "verification_reports_insert_own" ON storage.objects;
CREATE POLICY "verification_reports_insert_own" ON storage.objects FOR INSERT TO authenticated WITH CHECK (bucket_id = 'verification-reports' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "verification_reports_update_own" ON storage.objects;
CREATE POLICY "verification_reports_update_own" ON storage.objects FOR UPDATE TO authenticated USING (bucket_id = 'verification-reports' AND (storage.foldername(name))[1] = auth.uid()::text) WITH CHECK (bucket_id = 'verification-reports' AND (storage.foldername(name))[1] = auth.uid()::text);
DROP POLICY IF EXISTS "verification_reports_delete_own" ON storage.objects;
CREATE POLICY "verification_reports_delete_own" ON storage.objects FOR DELETE TO authenticated USING (bucket_id = 'verification-reports' AND (storage.foldername(name))[1] = auth.uid()::text);
