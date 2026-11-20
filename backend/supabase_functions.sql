-- Supabase helper functions for VERITAS AI backend
-- Run these in Supabase SQL Editor after main migration

-- Function to count publications for a document (via citations)
CREATE OR REPLACE FUNCTION public.count_publications_for_document(doc_id uuid)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COUNT(*)
  FROM public.publications p
  JOIN public.citations c ON c.id = p.citation_id
  WHERE c.document_id = doc_id;
$$;

-- Function to count verifications for a document (via claims)
CREATE OR REPLACE FUNCTION public.count_verifications_for_document(doc_id uuid)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COUNT(*)
  FROM public.verifications v
  JOIN public.claims c ON c.id = v.claim_id
  WHERE c.document_id = doc_id;
$$;

-- Grant execute to authenticated users (for frontend) and service role
GRANT EXECUTE ON FUNCTION public.count_publications_for_document(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.count_verifications_for_document(uuid) TO authenticated;

-- Verify verdict check constraint (add to verifications table)
ALTER TABLE public.verifications
DROP CONSTRAINT IF EXISTS verifications_verdict_check,
ADD CONSTRAINT verifications_verdict_check
CHECK (verdict IN (
  'SUPPORTED',
  'PARTIALLY_SUPPORTED',
  'UNSUPPORTED',
  'CONTRADICTORY',
  'POTENTIALLY_OUTDATED',
  'NEEDS_REVIEW'
));

-- Index for faster publication lookups
CREATE INDEX IF NOT EXISTS publications_citation_id_retrieval_idx
ON public.publications (citation_id, retrieval_status);

-- Index for evidence lookups
CREATE INDEX IF NOT EXISTS evidence_claim_publication_idx
ON public.evidence (claim_id, publication_id);

-- Function to get document processing stats
CREATE OR REPLACE FUNCTION public.get_document_processing_stats(doc_id uuid)
RETURNS json
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT json_build_object(
    'claims_extracted', (SELECT COUNT(*) FROM public.claims WHERE document_id = doc_id),
    'citations_found', (SELECT COUNT(*) FROM public.citations WHERE document_id = doc_id),
    'publications_retrieved', public.count_publications_for_document(doc_id),
    'verifications_completed', public.count_verifications_for_document(doc_id)
  );
$$;

GRANT EXECUTE ON FUNCTION public.get_document_processing_stats(uuid) TO authenticated;