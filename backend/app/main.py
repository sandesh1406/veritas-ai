from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, status, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import logging
import io
import uuid
from supabase import create_client

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin, validate_access_token, get_user_client, verify_user_owns_document
from app.models.schemas import (
    DocumentProcessRequest,
    DocumentStatusResponse,
    DocumentResultsResponse,
    HealthResponse,
    ProcessingStatus,
    DocumentUploadResponse,
    ReportGenerateRequest,
    ReportResponse,
    SupabaseHealthResponse,
    AIProviderInfo,
)
from app.services.document_processor import DocumentProcessor
from app.services.research_retrieval import ResearchRetrievalService
from app.services.evidence_extractor import EvidenceExtractor
from app.services.ai_verification import AIVerificationService
from app.services.report_generator import ReportGenerator
from app.services.storage_service import StorageService, get_storage_service
from app.services.background_worker import queue_document_processing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global service instances
doc_processor: Optional[DocumentProcessor] = None
research_service: Optional[ResearchRetrievalService] = None
evidence_extractor: Optional[EvidenceExtractor] = None
ai_verification: Optional[AIVerificationService] = None
report_generator: Optional[ReportGenerator] = None
storage_service: Optional[StorageService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global doc_processor, research_service, evidence_extractor, ai_verification, report_generator, storage_service
    logger.info("Starting VERITAS AI Backend...")
    doc_processor = DocumentProcessor(max_claims=settings.MAX_CLAIMS_PER_DOC)
    research_service = ResearchRetrievalService()
    evidence_extractor = EvidenceExtractor(research_service)
    ai_verification = AIVerificationService()
    report_generator = ReportGenerator()
    storage_service = await get_storage_service()
    yield
    logger.info("Shutting down...")
    if research_service:
        await research_service.close()
    if ai_verification:
        await ai_verification.close()


app = FastAPI(
    title="VERITAS AI Verification API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - use environment variable in production
cors_origins = settings.ALLOWED_ORIGINS.split(",") if hasattr(settings, 'ALLOWED_ORIGINS') else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_user_token(authorization: str = Header(...)) -> dict:
    """Extract and validate user access token against Supabase Auth."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth header")
    access_token = authorization[7:]
    return await validate_access_token(access_token)


async def get_document_owner(document_id: str, user_data: dict) -> str:
    """Verify document exists and return owner user_id."""
    return await verify_user_owns_document(document_id, user_data["access_token"])


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy")


@app.get("/health/supabase", response_model=SupabaseHealthResponse)
async def supabase_health_check():
    """Check Supabase connectivity."""
    admin = get_supabase_admin()
    result = {"status": "healthy", "database_connected": False, "auth_connected": False, "storage_connected": False, "error": None}

    try:
        # Check database connectivity
        admin.from_("documents").select("id").limit(1).execute()
        result["database_connected"] = True
    except Exception as e:
        result["status"] = "degraded"
        result["error"] = f"Database: {str(e)}"

    try:
        # Check auth connectivity
        auth_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        auth_client.auth.get_session()
        result["auth_connected"] = True
    except Exception as e:
        result["status"] = "degraded"
        result["error"] = (result["error"] or "") + f" Auth: {str(e)}"

    try:
        # Check storage connectivity
        buckets = admin.storage.list_buckets()
        result["storage_connected"] = True
    except Exception as e:
        result["status"] = "degraded"
        result["error"] = (result["error"] or "") + f" Storage: {str(e)}"

    return result


@app.get("/ai/provider", response_model=AIProviderInfo)
async def ai_provider_info():
    """Get information about the configured AI provider."""
    return AIProviderInfo(
        provider=settings.AI_PROVIDER,
        model=settings.GEMINI_MODEL if settings.AI_PROVIDER == "gemini" else settings.CLAUDE_MODEL,
        available=True
    )


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_data: dict = Depends(verify_user_token),
):
    """Upload a research document to Supabase storage."""
    user_id = user_data["id"]
    admin = get_supabase_admin()

    # Validate file type
    allowed_types = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/msword": "doc",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}"
        )

    # Read file content
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Validate file size
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {file_size} bytes (max {max_size} bytes)"
        )

    # Upload to storage
    storage_path = await storage_service.upload_document(user_id, file_bytes, file.filename, file.content_type)

    # Register document in database
    document_id = str(uuid.uuid4())
    result = admin.from_("documents").insert({
        "id": document_id,
        "user_id": user_id,
        "filename": file.filename,
        "storage_path": storage_path,
        "file_type": file.content_type,
        "file_size": file_size,
        "processing_status": "queued",
    }).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register document"
        )

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        storage_path=storage_path,
        file_type=file.content_type,
        file_size=file_size,
        processing_status=ProcessingStatus.QUEUED,
    )


@app.post("/documents/{document_id}/process", response_model=DocumentStatusResponse)
async def process_document(
    document_id: str,
    user_data: dict = Depends(verify_user_token),
):
    """Start document processing pipeline (queued for background processing)."""
    # Verify ownership
    user_id = await get_document_owner(document_id, user_data)

    admin = get_supabase_admin()

    # Update status to queued
    admin.from_("documents").update({"processing_status": "queued"}).eq("id", document_id).execute()

    # Queue for background processing
    job_id = await queue_document_processing(document_id, user_id)

    logger.info(f"Document {document_id} queued for background processing (job: {job_id})")

    # Return immediate queued status
    doc_result = admin.from_("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data

    return DocumentStatusResponse(
        document_id=document_id,
        processing_status=ProcessingStatus.QUEUED,
        claims_extracted=0,
        citations_found=0,
        publications_retrieved=0,
        verifications_completed=0,
        error=None,
        updated_at=doc["created_at"],
    )


@app.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    user_data: dict = Depends(verify_user_token),
):
    """Get current processing status."""
    await get_document_owner(document_id, user_data)  # Verify access

    admin = get_supabase_admin()

    # Get document
    doc_result = admin.from_("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data

    # Count related records using RPC functions for proper joins
    claims_count = admin.from_("claims").select("id", count="exact").eq("document_id", document_id).execute()
    citations_count = admin.from_("citations").select("id", count="exact").eq("document_id", document_id).execute()

    # Use RPC functions for counts that require joins
    pubs_result = admin.rpc("count_publications_for_document", {"doc_id": document_id}).execute()
    pubs_retrieved = pubs_result.data if pubs_result.data else 0

    verifs_result = admin.rpc("count_verifications_for_document", {"doc_id": document_id}).execute()
    verifications_completed = verifs_result.data if verifs_result.data else 0

    return DocumentStatusResponse(
        document_id=document_id,
        processing_status=ProcessingStatus(doc["processing_status"]),
        claims_extracted=claims_count.count or 0,
        citations_found=citations_count.count or 0,
        publications_retrieved=pubs_retrieved,
        verifications_completed=verifications_completed,
        error=None,
        updated_at=doc["created_at"],
    )


@app.get("/documents/{document_id}/results", response_model=DocumentResultsResponse)
async def get_document_results(
    document_id: str,
    user_data: dict = Depends(verify_user_token),
):
    """Get full verification results."""
    await get_document_owner(document_id, user_data)

    admin = get_supabase_admin()

    # Get document
    doc_result = admin.from_("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data

    # Get claims
    claims_result = admin.from_("claims").select("*").eq("document_id", document_id).execute()
    claims = [
        {
            "id": c["id"],
            "claim_text": c["claim_text"],
            "claim_type": c.get("claim_type"),
            "page_number": c.get("page_number"),
        }
        for c in (claims_result.data or [])
    ]

    # Get citations
    citations_result = admin.from_("citations").select("*").eq("document_id", document_id).execute()
    citations = [
        {
            "id": c["id"],
            "claim_id": c["claim_id"],
            "citation_text": c["citation_text"],
            "reference_number": c.get("reference_number"),
            "doi": c.get("doi"),
        }
        for c in (citations_result.data or [])
    ]

    # Get publications
    # Need to join through citations
    pubs_result = admin.from_("publications").select("*").in_("citation_id", [c["id"] for c in citations]).execute()
    publications = [
        {
            "id": p["id"],
            "citation_id": p["citation_id"],
            "title": p["title"],
            "authors": p.get("authors"),
            "doi": p.get("doi"),
            "publication_year": p.get("publication_year"),
            "source_url": p.get("source_url"),
            "retrieval_status": p["retrieval_status"],
        }
        for p in (pubs_result.data or [])
    ]

    # Get evidence
    evidence_result = admin.from_("evidence").select("*").in_("claim_id", [c["id"] for c in claims]).execute()
    evidence = [
        {
            "id": e["id"],
            "claim_id": e["claim_id"],
            "publication_id": e["publication_id"],
            "evidence_text": e["evidence_text"],
            "source_location": e.get("source_location"),
        }
        for e in (evidence_result.data or [])
    ]

    # Get verifications
    verifs_result = admin.from_("verifications").select("*").in_("claim_id", [c["id"] for c in claims]).execute()
    verifications = [
        {
            "id": v["id"],
            "claim_id": v["claim_id"],
            "verdict": v["verdict"],
            "confidence_score": v.get("confidence_score"),
            "explanation": v.get("explanation"),
            "evidence_status": v.get("evidence_status"),
            "model_version": v["model_version"],
        }
        for v in (verifs_result.data or [])
    ]

    return DocumentResultsResponse(
        document_id=document_id,
        filename=doc["filename"],
        claims=claims,
        citations=citations,
        publications=publications,
        evidence=evidence,
        verifications=verifications,
    )


async def _run_processing_pipeline(document_id: str, user_id: str, admin):
    """Run the full processing pipeline."""
    # 1. Get document from storage
    doc_result = admin.from_("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data

    # Download file from storage using storage service
    file_bytes = await storage_service.download_document(doc["storage_path"])
    if not file_bytes:
        raise Exception("Failed to download document from storage")

    file_type = doc["file_type"]
    logger.info(f"Processing document {document_id}: {len(file_bytes)} bytes, type {file_type}")

    # 2. Extract text, claims, citations
    chunks = doc_processor.extract_text(file_bytes, file_type)
    logger.info(f"Document {document_id}: extracted {len(chunks)} text chunks from PDF")

    claims = doc_processor.extract_claims(chunks)
    logger.info(f"Document {document_id}: extracted {len(claims)} claims")

    citations = doc_processor.extract_citations(chunks)
    citations = doc_processor.map_claims_to_citations(claims, citations, chunks)
    logger.info(f"Document {document_id}: extracted {len(citations)} citations")

    # 5. Retrieve publications for each citation
    publication_records = []
    for cite in citation_records:
        pub_meta = await research_service.retrieve_publication(cite["citation_text"], cite["doi"])
        if pub_meta:
            result = admin.from_("publications").insert({
                "citation_id": cite["id"],
                "title": pub_meta.title,
                "authors": pub_meta.authors,
                "doi": pub_meta.doi,
                "publication_year": pub_meta.publication_year,
                "source_url": pub_meta.source_url,
                "retrieval_status": "completed" if (pub_meta.abstract or pub_meta.full_text_url) else "partial",
            }).execute()
            if result.data:
                publication_records.append({
                    "id": result.data[0]["id"],
                    "citation_id": cite["id"],
                    "title": pub_meta.title,
                    "abstract": pub_meta.abstract,
                    "full_text_url": pub_meta.full_text_url,
                })
    logger.info(f"Document {document_id}: retrieved {len(publication_records)} publications (expected: {len(citation_records)})")

    # 6. Extract evidence passages using evidence extractor
    evidence_records = []
    for claim in claim_records:
        # Find publications for this claim's citations - only use citations mapped to this claim
        claim_citations = [c for c in citation_records if c.get("claim_id") == claim["id"]]
        if not claim_citations:
            logger.warning(f"Claim {claim['id']}: no citations mapped, skipping evidence extraction")
            continue

        claim_pubs = [p for p in publication_records if p["citation_id"] in [c["id"] for c in claim_citations]]

        if not claim_pubs:
            logger.warning(f"Claim {claim['id']}: no publications found for its citations, skipping evidence extraction")
            continue

        # Convert to PublicationMetadata objects
        from app.services.research_retrieval import PublicationMetadata
        pub_objects = [
            PublicationMetadata(
                title=p["title"],
                authors=p.get("authors"),
                doi=p.get("doi"),
                publication_year=p.get("publication_year"),
                source_url=p.get("source_url"),
                abstract=p.get("abstract"),
                full_text_url=p.get("full_text_url"),
            )
            for p in claim_pubs
        ]

        passages = await evidence_extractor.extract_evidence_for_claim(
            claim["claim_text"], pub_objects
        )
        logger.info(f"Claim {claim['id']}: extracted {len(passages)} evidence passages from {len(pub_objects)} publications")

        for passage in passages:
            # Find the publication ID
            pub_id = next((p["id"] for p in claim_pubs if p["title"] == passage.publication_id), None)
            if pub_id:
                result = admin.from_("evidence").insert({
                    "claim_id": claim["id"],
                    "publication_id": pub_id,
                    "evidence_text": passage.text[:5000],
                    "source_location": passage.source_location,
                }).execute()
                if result.data:
                    evidence_records.append(result.data[0])
    logger.info(f"Document {document_id}: extracted {len(evidence_records)} evidence passages total")

    # 7. AI Verification
    # Build claim->evidence mapping
    evidence_by_claim = {}
    for ev in evidence_records:
        if ev["claim_id"] not in evidence_by_claim:
            evidence_by_claim[ev["claim_id"]] = []
        evidence_by_claim[ev["claim_id"]].append(ev["evidence_text"])

    # Map citations to claims using the claim_id stored in citation_records
    citation_by_claim = {}
    for cite in citation_records:
        if cite.get("claim_id"):
            citation_by_claim[cite["claim_id"]] = cite

    pub_by_citation = {p["citation_id"]: p for p in publication_records}

    claims_to_verify = []
    for claim in claim_records:
        cite = citation_by_claim.get(claim["id"])
        pub = pub_by_citation.get(cite["id"]) if cite else None

        claims_to_verify.append({
            "claim_id": claim["id"],
            "claim_text": claim["claim_text"],
            "citation_text": cite["citation_text"] if cite else "",
            "evidence_passages": evidence_by_claim.get(claim["id"], []),
            "publication_title": pub["title"] if pub else "Unknown",
        })

    # Verify
    from app.services.ai_verification import ClaimWithEvidence
    claim_objects = [
        ClaimWithEvidence(
            claim_id=c["claim_id"],
            claim_text=c["claim_text"],
            citation_text=c["citation_text"],
            evidence_passages=c["evidence_passages"],
            publication_title=c["publication_title"],
        )
        for c in claims_to_verify
    ]

    logger.info(f"Document {document_id}: {len(claim_objects)} claim objects prepared for verification")
    if not claim_objects:
        logger.warning(f"Document {document_id}: no claims to verify (claim_records={len(claim_records)}, evidence_records={len(evidence_records)})")
    else:
        logger.info(f"Document {document_id}: verifying {len(claim_objects)} claims")
        batch_result = await ai_verification.verify_batch(claim_objects)
        verifications = batch_result.verifications

    # Log batch errors if any
    if batch_result.errors:
        logger.warning(f"Document {document_id}: batch verification completed with {len(batch_result.errors)} errors: {batch_result.errors}")

    # Save verifications
    for claim_obj, verification in zip(claim_objects, verifications):
        admin.from_("verifications").insert({
            "claim_id": claim_obj.claim_id,
            "verdict": verification.verdict.value,
            "confidence_score": verification.confidence_score,
            "explanation": verification.explanation,
            "evidence_status": verification.evidence_status,
            "model_version": settings.GEMINI_MODEL if settings.AI_PROVIDER == "gemini" else settings.CLAUDE_MODEL,
        }).execute()
    logger.info(f"Document {document_id}: saved {len(verifications)} verifications")

    # 8. Generate report
    # (Report generation happens on-demand via frontend)

    # 9. Mark completed ONLY if processing succeeded
    if not claims:
        logger.warning(f"Document {document_id}: no claims extracted, marking as failed")
        admin.from_("documents").update({"processing_status": "failed"}).eq("id", document_id).execute()
        raise Exception("No claims extracted from document")

    # Check for partial failures but don't fail the whole document
    if not citations:
        logger.warning(f"Document {document_id}: no citations extracted")
    if not publication_records:
        logger.warning(f"Document {document_id}: no publications retrieved")
    if not evidence_records and claim_objects:
        logger.warning(f"Document {document_id}: no evidence extracted for claims")
    if not verifications and claim_objects:
        logger.warning(f"Document {document_id}: no verifications completed")

    admin.from_("documents").update({"processing_status": "completed"}).eq("id", document_id).execute()
    logger.info(f"Document {document_id}: processing completed successfully")


@app.post("/documents/{document_id}/report", response_model=ReportResponse)
async def generate_report(
    document_id: str,
    user_data: dict = Depends(verify_user_token),
):
    """Generate a PDF verification report for a document."""
    user_id = user_data["id"]
    admin = get_supabase_admin()

    # Verify ownership
    await get_document_owner(document_id, user_data)

    # Get all results
    results_response = await get_document_results(document_id, user_data)

    # Generate PDF report
    pdf_bytes = report_generator.generate_report(
        filename=results_response.filename,
        claims=results_response.claims,
        citations=results_response.citations,
        publications=results_response.publications,
        evidence=results_response.evidence,
        verifications=results_response.verifications,
    )

    # Upload report to storage
    report_filename = f"{document_id}_verification_report.pdf"
    report_path = await storage_service.upload_report(user_id, pdf_bytes, report_filename)

    # Register report in database
    report_id = str(uuid.uuid4())
    result = admin.from_("reports").insert({
        "id": report_id,
        "document_id": document_id,
        "user_id": user_id,
        "report_path": report_path,
    }).execute()

    # Get signed download URL
    download_url = await storage_service.get_report_url(report_path)

    return ReportResponse(
        report_id=report_id,
        document_id=document_id,
        storage_path=report_path,
        download_url=download_url,
        file_size=len(pdf_bytes),
    )


@app.get("/documents", response_model=list)
async def list_documents(user_data: dict = Depends(verify_user_token)):
    """List all documents for the authenticated user."""
    user_id = user_data["id"]
    admin = get_supabase_admin()

    result = admin.from_("documents").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data or []


@app.get("/reports", response_model=list)
async def list_reports(user_data: dict = Depends(verify_user_token)):
    """List all reports for the authenticated user."""
    user_id = user_data["id"]
    admin = get_supabase_admin()

    result = admin.from_("reports").select("*, documents(filename)").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data or []


@app.get("/documents/{document_id}/report/download")
async def download_report(
    document_id: str,
    user_data: dict = Depends(verify_user_token),
):
    """Download a PDF verification report."""
    await get_document_owner(document_id, user_data)

    admin = get_supabase_admin()

    # Find report for document
    result = admin.from_("reports").select("*").eq("document_id", document_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Report not found")

    # Download report from storage
    report_bytes = await storage_service.download_report(result.data["report_path"])

    return Response(
        content=report_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={document_id}_verification_report.pdf"
        }
    )