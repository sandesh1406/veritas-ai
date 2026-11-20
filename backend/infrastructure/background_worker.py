"""Background document processing worker.

Retrieves queued jobs from Supabase, processes them using the existing pipeline,
and updates status. Runs as a scheduled cron job.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin
from app.services.document_processor import DocumentProcessor
from app.services.research_retrieval import ResearchRetrievalService
from app.services.evidence_extractor import EvidenceExtractor
from app.services.ai_verification import AIVerificationService
from app.services.report_generator import ReportGenerator
from app.services.storage_service import StorageService, get_storage_service

logger = logging.getLogger(__name__)

# Global processor instance
_processor: Optional[Any] = None


async def get_processor() -> Any:
    """Get or initialize the background processor."""
    global _processor
    if _processor is None:
        _processor = BackgroundProcessor()
        await _processor.initialize()
    return _processor


class BackgroundProcessor:
    """Handles asynchronous document processing using pg_cron and Supabase."""

    def __init__(self):
        self.doc_processor: Optional[DocumentProcessor] = None
        self.research_service: Optional[ResearchRetrievalService] = None
        self.evidence_extractor: Optional[EvidenceExtractor] = None
        self.ai_verification: Optional[AIVerificationService] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.storage_service: Optional[StorageService] = None
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aenter__(self):
        await self.initialize()
        return self

    async def initialize(self):
        """Initialize all service dependencies."""
        self.doc_processor = DocumentProcessor(max_claims=settings.MAX_CLAIMS_PER_DOC)
        self.research_service = ResearchRetrievalService()
        self.evidence_extractor = EvidenceExtractor(self.research_service)
        self.ai_verification = AIVerificationService()
        self.report_generator = ReportGenerator()
        self.storage_service = await get_storage_service()
        self._initialized = True

    async def close(self):
        """Close all service connections."""
        self.doc_processor = None
        self.research_service = None
        self.evidence_extractor = None
        self.ai_verification = None
        self.report_generator = None
        self.storage_service = None

    async def process_document(self, document_id: str, user_id: str) -> dict:
        """Process a single document asynchronously."""
        admin = get_supabase_admin()
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Create job record in database
        job_data = {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "user_id": user_id,
            "status": "queued",
            "error": None,
            "retry_count": 0,
            "started_at": None,
            "completed_at": None
        }
        admin.from_("processing_jobs").insert(job_data).execute()

        # Update document status to queued
        admin.from_("documents").update({
            "processing_status": "queued",
            "processing_job_id": job_id
        ).eq("id", document_id).execute()

        try:
            # Run the processing pipeline
            await _run_processing_pipeline(document_id, user_id, admin)

            # Mark job as completed
            await self._update_job_status(job_id, "completed", None)

            # Update document status to completed
            admin.from_("documents").update({
                "processing_status": "completed",
                "processing_job_id": None
            ).eq("id", document_id).execute()

        except Exception as e:
            logger.error(f"Background processing failed for {document_id}: {e}")

            # Mark job as failed
            await self._update_job_status(job_id, "failed", str(e))

            # Update document status to failed
            admin.from_("documents").update({
                "processing_status": "failed",
                "processing_job_id": None,
                "processing_error": str(e)
            }).eq("id", document_id).execute()

        return {"status": "completed", "job_id": job_id}

    async def _update_job_status(self, job_id: str, status: str, error: str | None):
        """Update job status in database."""
        admin = get_supabase_admin()
        update_data = {
            "status": status,
            "completed_at": __import__("datetime").datetime.utcnow().isoformat()
        }
        if error:
            update_data["error"] = error
        admin.from_("processing_jobs").update(update_data).eq("id", job_id).execute()

    async def get_queued_jobs(self) -> list:
        """Get all queued jobs ready for processing."""
        admin = get_supabase_admin()
        result = admin.from_("processing_jobs").select("*").eq("status", "queued").execute()
        return result.data or []

    async def get_queued_jobs_with_retry(self, max_retries: int = 3) -> list:
        """Get queued jobs with retry logic."""
        jobs = []
        for _ in range(3):
            jobs = await self.get_queued_jobs()
            if jobs:
                break
            await asyncio.sleep(5)  # Wait before retrying
        return jobs


class BackgroundProcessor:
    """Handles asynchronous document processing using pg_cron and Supabase."""

    def __init__(self):
        self.doc_processor: Optional[DocumentProcessor] = None
        self.research_service: Optional[ResearchRetrievalService] = None
        self.evidence_extractor: Optional[EvidenceExtractor] = None
        self.ai_verification: Optional[AIVerificationService] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.storage_service: Optional[StorageService] = None
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exit_event):
        await self.close()

    async def initialize(self):
        """Initialize all service dependencies."""
        self.doc_processor = DocumentProcessor(max_claims=settings.MAX_CLAIMS_PER_DOC)
        self.research_service = ResearchRetrievalService()
        self.evidence_extractor = EvidenceExtractor(self.research_service)
        self.ai_verification = AIVerificationService()
        self.report_generator = ReportGenerator()
        self.storage_service = await get_storage_service()
        self._initialized = True

    async def close(self):
        self.doc_processor = None
        self.research_service = None
        self.evidence_extractor = None
        self.ai_verification = None
        self.report_generator = None
        self.storage_service = None

    async def process_document(self, document_id: str, user_id: str) -> dict:
        """Process a single document asynchronously."""
        admin = get_supabase_admin()
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Create job record in database
        job_data = {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "user_id": user_id,
            "status": "queued",
            "error": None,
            "retry_count": 0,
            "created_at": __import__("datetime").utcnow().isoformat(),
            "started_at": None,
            "completed_at": None
        }
        admin.from_("processing_jobs").insert(job_data).execute()

        # Update document status to queued
        admin.from_("documents").update({
            "processing_status": "queued",
            "processing_job_id": job_id
        ).eq("id", document_id).execute()

        try:
            # Run the processing pipeline
            await _run_processing_pipeline(document_id, user_id, admin)

            # Mark job as completed
            await self._update_job_status(job_id, "completed", None)

            # Update document status to completed
            admin.from_("documents").update({
                "processing_status": "completed",
                "processing_job_id": None
            }).eq("id", document_id).execute()

        except Exception as e:
            logger.error(f"Background processing failed for {document_id}: {e}")

            # Mark job as failed
            await self._update_job_status(job_id, "failed", str(e))

            # Update document status to failed
            admin.from_("documents").update({
                "processing_status": "failed",
                "processing_job_id": None,
                "processing_error": str(e)
            }).eq("id", document_id).execute()

        return {"status": "completed", "job_id": job_id}

    async def get_queued_jobs(self) -> list:
        """Get all queued jobs ready for processing."""
        admin = get_supabase_admin()
        result = admin.from_("processing_jobs").select("*").eq("status", "queued").execute()
        return result.data or []

    async def get_queued_jobs_with_retry(self, max_retries: int = 3) -> list:
        """Get queued jobs with retry logic."""
        jobs = []
        for _ in range(3):
            jobs = await self.get_queued_jobs()
            if jobs:
                break
            await asyncio.sleep(5)
        return jobs


# Global instance
_background_processor = None

async def get_background_processor() -> "BackgroundProcessor":
    global _worker
    if _worker is None:
        _worker = BackgroundProcessor()
        await _worker.initialize()
    return _worker


async def queue_document_processing(document_id: str, user_id: str) -> str:
    """Queue a document for background processing. Returns job ID."""
    processor = await get_background_processor()
    job_id = str(uuid.uuid4())
    admin = get_supabase_admin()

    job_data = {
        "id": str(uuid.uuid4()),
        "document_id": document_id,
        "user_id": user_id,
        "status": "queued",
        "retry_count": 0,
        "created_at": __import__("datetime").utcnow().isoformat()
    }
    admin.from_("processing_jobs").insert(job_data).execute()

    # Update document status to queued
    admin.from_("documents").update({
        "processing_status": "queued",
        "processing_job_id": job_id
    }).eq("id", document_id).execute()

    return job_id


# SQL for creating the processing_jobs table
PROCESSING_JOBS_SQL = """
-- Create processing_jobs table for background document processing
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS processing_jobs_status_idx ON public.processing_jobs(status);
CREATE INDEX IF NOT EXISTS processing_jobs_document_id_idx ON public.processing_jobs(document_id);
CREATE INDEX IF NOT EXISTS processing_jobs_user_id_idx ON public.processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS processing_jobs_created_at_idx ON public.processing_jobs(created_at DESC);

-- 4. RLS Policies
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own processing jobs
CREATE POLICY "Users can view own processing jobs" ON public.processing_jobs
    FOR SELECT USING (auth.uid() = user_id);

-- Service role can manage all jobs
CREATE POLICY "Service role can manage processing jobs" ON public.processing_jobs
    FOR ALL USING (auth.role() = 'service_role');

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON public.processing_jobs TO authenticated;
GRANT ALL ON public.processing_jobs TO service_role;

-- 5. pg_cron job to process queued documents (run every 5 minutes)
-- This SQL should be run in the Supabase SQL Editor:
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule(
--     'process-queued-documents',
--     '*/5 * * * *',
--     $$
--     SELECT process_queued_documents();
--     $$
-- ;
-- FUNCTION process_queued_documents()
-- RETURNS void LANGUAGE plpgsql AS
-- $$
-- DECLARE
--     job_record RECORD;
-- BEGIN
--     FOR job_record IN
--         SELECT * FROM public.processing_jobs
--         WHERE status = 'queued'
--         ORDER BY created_at ASC
--         LIMIT 5
--         FOR UPDATE SKIP LOCKED
--     LOOP
--         -- Mark job as processing
--         UPDATE public.processing_jobs
--         SET status = 'processing', started_at = now()
--         WHERE id = job_record.id;
--         -- TODO: Call the actual processing function
--         -- This would be done via an edge function or external worker
--         -- For now, we just mark as completed for demo
--         UPDATE public.processing_jobs
--         SET status = 'completed', completed_at = now()
--         WHERE id = job_record.id;
--         -- Update document status
--         UPDATE public.documents
--         SET processing_status = 'completed'
--         WHERE id = job_record.document_id;
--     END LOOP;
-- $$;
```

Now let me verify the Python code compiles:</think>
<tool_call>
<function=mcp__workspace__bash>
<parameter=command>
cd /sessions/zen-vibrant-gates/mnt/project-bolt-sb1-cafzb9qb/backend && python3 -c "
import sys
sys.path.insert(0, '.')
from app.services.background_processor import BackgroundProcessor, get_background_processor
print('Background processor module imports successfully')
" 2>&1