-- VERITAS AI: Background Processing Infrastructure
-- Safe migration for Supabase PostgreSQL

-- 1. Create processing_jobs table
CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL
        REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL
        REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS processing_jobs_status_idx
ON public.processing_jobs(status);

CREATE INDEX IF NOT EXISTS processing_jobs_document_id_idx
ON public.processing_jobs(document_id);

CREATE INDEX IF NOT EXISTS processing_jobs_user_id_idx
ON public.processing_jobs(user_id);

CREATE INDEX IF NOT EXISTS processing_jobs_created_at_idx
ON public.processing_jobs(created_at DESC);

-- 3. Enable RLS
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

-- 4. Create policies without duplicate-policy errors
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
        AND tablename = 'processing_jobs'
        AND policyname = 'Users can view own processing jobs'
    ) THEN
        CREATE POLICY "Users can view own processing jobs"
        ON public.processing_jobs
        FOR SELECT
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
        AND tablename = 'processing_jobs'
        AND policyname = 'Service role can manage processing jobs'
    ) THEN
        CREATE POLICY "Service role can manage processing jobs"
        ON public.processing_jobs
        FOR ALL
        TO service_role
        USING (true)
        WITH CHECK (true);
    END IF;
END
$$;

-- 5. Permissions
GRANT SELECT ON public.processing_jobs TO authenticated;

GRANT ALL PRIVILEGES ON public.processing_jobs TO service_role;

-- 6. Atomically claim the oldest queued job
CREATE OR REPLACE FUNCTION public.claim_next_job()
RETURNS SETOF public.processing_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    job_record public.processing_jobs%ROWTYPE;
BEGIN
    SELECT *
    INTO job_record
    FROM public.processing_jobs
    WHERE status = 'queued'
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE public.processing_jobs
    SET
        status = 'processing',
        started_at = now(),
        error = NULL
    WHERE id = job_record.id
    RETURNING * INTO job_record;

    RETURN NEXT job_record;
END;
$$;

-- 7. Restrict function execution to backend worker role
REVOKE ALL ON FUNCTION public.claim_next_job() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.claim_next_job() TO service_role;

-- 8. Add processing fields to documents
ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS processing_job_id UUID,
ADD COLUMN IF NOT EXISTS processing_error TEXT;

-- 9. Index
CREATE INDEX IF NOT EXISTS documents_processing_job_id_idx
ON public.documents(processing_job_id);