"""Background document processing worker.

Processes queued documents from the processing_jobs table. Claims jobs atomically
via the claim_next_job RPC, runs the processing pipeline, and keeps job/document
statuses synchronized. Run with: python -m app.services.background_worker
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, Any

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin
from app.services.document_processor import DocumentProcessor
from app.services.research_retrieval import ResearchRetrievalService
from app.services.evidence_extractor import EvidenceExtractor
from app.services.ai_verification import AIVerificationService
from app.services.report_generator import ReportGenerator
from app.services.storage_service import get_storage_service
from app.services.processing_pipeline import run_processing_pipeline

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Background worker for processing queued document jobs."""

    def __init__(self):
        self.doc_processor: Optional[DocumentProcessor] = None
        self.research_service: Optional[ResearchRetrievalService] = None
        self.evidence_extractor: Optional[EvidenceExtractor] = None
        self.ai_verification: Optional[AIVerificationService] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.storage_service: Optional[Any] = None
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
        logger.info("Worker services initialized (doc_processor, research, evidence, ai, reports, storage)")

    async def close(self):
        """Close all service connections."""
        if self.research_service:
            await self.research_service.close()
        if self.ai_verification:
            await self.ai_verification.close()
        logger.info("Worker services closed")

    async def process_next_job(self) -> bool:
        """Claim and process the next queued job. Returns True if a job was processed."""
        admin = get_supabase_admin()

        # Claim the oldest queued job atomically via claim_next_job RPC
        try:
            result = admin.rpc("claim_next_job", {}).execute()
        except Exception as e:
            logger.error(f"claim_next_job RPC failed: {e}", exc_info=True)
            return False

        if not result.data:
            return False

        job = result.data[0]
        job_id = job["id"]
        document_id = job["document_id"]
        user_id = job["user_id"]

        logger.info(f"Claimed job {job_id} for document {document_id}")

        # Mark job as processing with timestamp
        admin.from_("processing_jobs").update({
            "status": "processing",
            "started_at": datetime.utcnow().isoformat()
        }).eq("id", job_id).execute()
        # Update document status in sync
        admin.from_("documents").update({
            "processing_status": "processing"
        }).eq("id", document_id).execute()

        try:
            result_data = await run_processing_pipeline(
                document_id=document_id,
                user_id=user_id,
                admin=admin
            )
            claims_count = len(result_data.get("claims", []))
            verifications_count = len(result_data.get("verifications", []))
            logger.info(f"Pipeline complete for {document_id}: {claims_count} claims, {verifications_count} verifications")

            # Mark job completed only after pipeline succeeds
            admin.from_("processing_jobs").update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": None
            }).eq("id", job_id).execute()

            logger.info(f"Job {job_id} completed successfully")
        except Exception as e:
            # Sanitized error message (avoid leaking internals)
            error_msg = str(e)[:500]
            logger.error(f"Processing failed for document {document_id}: {error_msg}", exc_info=True)

            # Mark job as failed with error
            admin.from_("processing_jobs").update({
                "status": "failed",
                "error": error_msg,
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", job_id).execute()

            # Mark document as failed in sync
            admin.from_("documents").update({
                "processing_status": "failed",
                "processing_error": error_msg,
                "processing_job_id": None
            }).eq("id", document_id).execute()

        return True

    async def run_continuous(self, poll_interval: int = 30, max_jobs_per_batch: int = 5):
        """Poll continuously for queued jobs and process them."""
        logger.info(f"Background worker polling started (interval={poll_interval}s, batch={max_jobs_per_batch})")
        while True:
            try:
                jobs_processed = 0
                for _ in range(max_jobs_per_batch):
                    processed = await self.process_next_job()
                    if not processed:
                        break
                    jobs_processed += 1

                if jobs_processed == 0:
                    logger.info("No queued jobs, waiting...")
                    await asyncio.sleep(poll_interval)
                else:
                    logger.info(f"Processed {jobs_processed} job(s) this batch")
                    await asyncio.sleep(2)

            except asyncio.CancelledError:
                logger.info("Worker cancelled, shutting down")
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
                await asyncio.sleep(60)


async def queue_document_processing(document_id: str, user_id: str) -> str:
    """Queue a document for background processing. Returns job ID."""
    job_id = str(uuid.uuid4())
    admin = get_supabase_admin()

    job_data = {
        "id": job_id,
        "document_id": document_id,
        "user_id": user_id,
        "status": "queued",
        "retry_count": 0,
        "created_at": datetime.utcnow().isoformat()
    }

    result = admin.from_("processing_jobs").insert(job_data).execute()
    if not result.data:
        raise Exception(f"Failed to insert processing job for document {document_id}")
    logger.info(f"Job {job_id} inserted for document {document_id}")

    # Update document status only after successful job insertion
    admin.from_("documents").update({
        "processing_status": "queued",
        "processing_job_id": job_id
    }).eq("id", document_id).execute()
    logger.info(f"Document {document_id} marked queued (job: {job_id})")

    return job_id


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    async def main():
        logger.info("=" * 60)
        logger.info("VERITAS AI Background Worker Starting")
        logger.info(f"Supabase URL: {settings.SUPABASE_URL}")
        logger.info(f"Max claims per doc: {settings.MAX_CLAIMS_PER_DOC}")
        logger.info("=" * 60)

        worker = BackgroundWorker()
        await worker.initialize()
        await worker.run_continuous(poll_interval=30, max_jobs_per_batch=5)

    asyncio.run(main())