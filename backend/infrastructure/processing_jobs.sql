-- processing_jobs table for background document processing
-- This table tracks document processing jobs and their status

-- 1. Create the processing_jobs table
CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    error text,
    retry_count integer DEFAULT 0,
    created_at timestamptz DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

-- 2. Create indexes for performance
CREATE INDEX IF NOT EXISTS processing_jobs_status_idx ON public.processing_jobs(status);
CREATE INDEX IF NOT EXISTS processing_jobs_document_id_idx ON public.processing_jobs(document_id);
CREATE INDEX IF NOT EXISTS processing_jobs_user_id_idx ON public.processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS processing_jobs_created_at_idx ON public.processing_jobs(created_at DESC);

-- 3. Enable RLS and set up policies
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own processing jobs
CREATE POLICY "Users can view own processing jobs" ON public.processing_jobs
    FOR SELECT USING (auth.uid() = user_id);

-- Service role can manage all jobs
CREATE POLICY "Service role can manage processing jobs" ON public.processing_jobs
    FOR ALL USING (auth.role() = 'service_role');

-- 4. Grant permissions
GRANT SELECT, INSERT, UPDATE ON public.processing_jobs TO authenticated;
GRANT ALL ON public.processing_jobs TO service_role;