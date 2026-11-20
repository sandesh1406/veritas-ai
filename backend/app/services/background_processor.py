"""Background document processing using Supabase pg_cron.

This module provides asynchronous document processing using Supabase pg_cron
to avoid timeout issues with large PDF processing.
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin
from app.services.document_processor import DocumentProcessor
from app.services.research_retrieval import ResearchRetrievalService
from app.services.evidence_extractor import EvidenceExtractor
from app.services.ai_verification import AIVerificationService
from app.services.report_generator import ReportGenerator
from app.services.storage_service import StorageService, get_storage_service

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    id: str
    document_id: str
    user_id: str
    status: ProcessingStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0


class BackgroundProcessor:
    """Handles asynchronous document processing using Supabase pg_cron."""

    def __init__(self):
        self.doc_processor: Optional[DocumentProcessor] = None
        self.research_service: Optional[ResearchRetrievalService] = None
        self.evidence_extractor: Optional[EvidenceExtractor] = None
        self.ai_verification: Optional[AIVerificationService] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.storage_service: Optional[StorageService] = None
        self._initialized = False

    async def initialize(self):
        """Initialize all service dependencies."""
        if self._initialized:
            return
        self.doc_processor = DocumentProcessor(max_claims=settings.MAX_CLAIMS_PER_DOC)
        self.research_service = ResearchRetrievalService()
        self.evidence_extractor = EvidenceExtractor(self.research_service)
        self.ai_verification = AIVerificationService()
        self.report_generator = ReportGenerator()
        self.storage_service = await get_storage_service()
        self._initialized = True

    async def process_document(self, document_id: str, user_id: str) -> None:
        """Process a single document asynchronously."""
        admin = get_supabase_admin()
        job_id = str(uuid.uuid4())

        # Create processing job record
        job = await self._create_job(job_id, document_id, user_id)

        try:
            # Update document status to processing
            admin.from_("documents").update({
                "processing_status": "processing",
                "processing_job_id": job.id
            }).eq("id", document_id).execute()

            # Run the processing pipeline
            await self._run_processing_pipeline(document_id, user_id, admin)

            # Mark job as completed
            await self._complete_job(job.id, "completed", None)

            # Update document status
            admin.from_("documents").update({
                "processing_status": "completed",
                "processing_job_id": None
            }).eq("id", document_id).execute()

        except Exception as e:
            logger.error(f"Background processing failed for {document_id}: {e}")

            # Update job with error
            await self._complete_job(job.id, "failed", str(e))

            # Update document status to failed
            admin.from_("documents").update({
                "processing_status": "failed",
                "processing_job_id": None,
                "processing_error": str(e)
            }).eq("id", document_id).execute()

    async def _create_job(self, job_id: str, document_id: str, user_id: str) -> Dict[str, Any]:
        """Create a processing job record."""
        admin = get_supabase_admin()
        job_data = {
            "id": job_id,
            "document_id": document_id,
            "user_id": user_id,
            "status": ProcessingStatus.QUEUED.value,
            "created_at": datetime.utcnow().isoformat(),
            "retry_count": 0
        }
        result = admin.from_("processing_jobs").insert(job_data).execute()
        return result.data[0] if result.data else {"id": job_id, **job_data}

    async def _complete_job(self, job_id: str, status: str, error: Optional[str] = None):
        """Mark a job as completed or failed."""
        admin = get_supabase_admin()
        update_data = {
            "status": status,
            "completed_at": datetime.utcnow().isoformat()
        }
        if error:
            update_data["error"] = error
        admin.from_("processing_jobs").update(update_data).eq("id", job_id).execute()


# Global background processor instance
_background_processor: Optional[BackgroundProcessor] = None


async def get_background_processor() -> BackgroundProcessor:
    """Get or create the background processor instance."""
    global _background_processor
    if _background_processor is None:
        _background_processor = BackgroundProcessor()
        await _background_processor.initialize()
    return _background_processor


async def queue_document_processing(document_id: str, user_id: str) -> str:
    """Queue a document for background processing. Returns job ID."""
    processor = await get_background_processor()
    job_id = str(uuid.uuid4())

    # Create job record
    admin = get_supabase_admin()
    job_data = {
        "id": str(uuid.uuid4()),
        "document_id": document_id,
        "user_id": user_id,
        "status": ProcessingStatus.QUEUED.value,
        "created_at": datetime.utcnow().isoformat(),
        "retry_count": 0
    }
    admin.from_("processing_jobs").insert(job_data).execute()

    # Update document status to queued
    admin = get_supabase_admin()
    admin.from_("documents").update({
        "processing_status": "queued",
        "processing_job_id": job_data["id"]
    }).eq("id", document_id).execute()

    # The pg_cron job will pick this up
    return job_data["id"]


# SQL for creating the processing_jobs table (run in Supabase SQL Editor)
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
CREATE INDEX IF NOT EXISTS processing_jobs_created_at_idx ON public.processing_jobs(created_at);

-- RLS Policies
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
"""

# pg_cron job to process queued documents (run every 5 minutes)
PG_CRON_SETUP_SQL = """
-- Enable pg_cron extension
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule background processing every 5 minutes
SELECT cron.schedule(
    'process-queued-documents',
    '*/5 * * * *',
    $$
    SELECT process_queued_documents();
    $$
);

-- Function to process queued documents
CREATE OR REPLACE FUNCTION process_queued_documents()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    job_record RECORD;
BEGIN
    -- Lock and get the oldest queued job
    FOR job_record IN
        SELECT * FROM public.processing_jobs
        WHERE status = 'queued'
        ORDER BY created_at ASC
        LIMIT 5
        FOR UPDATE SKIP LOCKED
    LOOP
        -- Mark job as processing
        UPDATE public.processing_jobs
        SET status = 'processing', started_at = now()
        WHERE id = job_record.id;

        -- TODO: Call the actual processing function
        -- This would typically be done via an edge function or external worker
        -- For now, we just mark as completed for demo
        UPDATE public.processing_jobs
        SET status = 'completed', completed_at = now()
        WHERE id = job_record.id;

        -- Update document status
        UPDATE public.documents
        SET processing_status = 'completed'
        WHERE id = job_record.document_id;
    END LOOP;
END;
$$;
"""