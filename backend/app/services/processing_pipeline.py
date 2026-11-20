"""Document processing pipeline for VERITAS AI.

This module contains the core document processing pipeline that extracts claims,
citations, retrieves publications, extracts evidence, and runs AI verification.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin
from app.services.document_processor import DocumentProcessor
from app.services.research_retrieval import ResearchRetrievalService
from app.services.evidence_extractor import EvidenceExtractor
from app.services.ai_verification import AIVerificationService, ClaimWithEvidence
from app.services.report_generator import ReportGenerator
from app.services.storage_service import StorageService, get_storage_service

logger = logging.getLogger(__name__)


async def run_processing_pipeline(
    document_id: str,
    user_id: str,
    admin,
    doc_processor: Optional[DocumentProcessor] = None,
    research_service: Optional[Any] = None,
    evidence_extractor: Optional[Any] = None,
    ai_verification: Optional[Any] = None,
    storage_service: Optional[Any] = None,
) -> dict:
    """Run the complete document processing pipeline.

    Args:
        document_id: UUID of the document to process
        user_id: UUID of the user who owns the document
        admin: Supabase admin client
        doc_processor: Optional DocumentProcessor instance
        research_service: Optional ResearchRetrievalService instance
        evidence_extractor: Optional EvidenceExtractor instance
        ai_verification: Optional AIVerificationService instance
        storage_service: Optional StorageService instance

    Returns:
        dict with processing results: claims, citations, publications, evidence, verifications

    Raises:
        Exception: If critical processing steps fail (e.g., no claims extracted)
    """
    # Initialize services if not provided - reuse injected instances
    if doc_processor is None:
        from app.services.document_processor import DocumentProcessor
        doc_processor = DocumentProcessor(max_claims=settings.MAX_CLAIMS_PER_DOC)

    if research_service is None:
        from app.services.research_retrieval import ResearchRetrievalService
        research_service = ResearchRetrievalService()

    if evidence_extractor is None:
        from app.services.evidence_extractor import EvidenceExtractor
        research_service = research_service or ResearchRetrievalService()
        evidence_extractor = EvidenceExtractor(research_service)

    from app.services.ai_verification import AIVerificationService
    ai_verification = ai_verification or AIVerificationService()

    if storage_service is None:
        from app.services.storage_service import get_storage_service
        storage_service = await get_storage_service()

    logger = logging.getLogger(__name__)

    # 1. Get document from storage
    doc_result = admin.from_("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data
    if not doc:
        raise Exception(f"Document {document_id} not found")

    # Download file from storage using storage service
    from app.services.storage_service import get_storage_service
    storage_service = await get_storage_service()
    file_bytes = await storage_service.download_document(doc["storage_path"])
    if not file_bytes:
        raise Exception("Failed to download document from storage")

    file_type = doc["file_type"]
    logger.info(f"Processing document {document_id}: {len(file_bytes)} bytes, type {file_type}")

    # 2. Extract text, claims, citations
    chunks = doc_processor.extract_text(file_bytes, file_type)
    if not chunks:
        raise Exception(f"Document {document_id}: PDF text extraction returned no text chunks")

    total_chars = sum(len(c.text) for c in chunks)
    logger.info(f"Document {document_id}: extracted {len(chunks)} text chunks, {total_chars} characters total")

    claims = doc_processor.extract_claims(chunks)
    logger.info(f"Document {document_id}: extracted {len(claims)} claims")

    if not claims:
        raise Exception(f"Document {document_id}: No claims extracted from document. Document may be scanned, empty, or in an unsupported format.")

    citations = doc_processor.extract_citations(chunks)
    citations = doc_processor.map_claims_to_citations(claims, citations, chunks)
    logger.info(f"Document {document_id}: extracted {len(citations)} citations")

    # 3. Save claims
    claim_records = []
    for claim in claims:
        result = admin.from_("claims").insert({
            "document_id": document_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "page_number": claim.page_number,
        }).execute()
        if result.data:
            claim_records.append({"id": result.data[0]["id"], "claim_text": claim.claim_text, "page_number": claim.page_number, "claim_type": claim.claim_type})
    logger.info(f"Document {document_id}: saved {len(claim_records)} claims to database")

    if not claim_records:
        raise Exception(f"Document {document_id}: No claims persisted to database")

    # 4. Save citations linked to claims - improved mapping
    claim_text_to_id = {c["claim_text"]: c["id"] for c in claim_records}
    citation_records = []

    # Build a more robust citation-to-claim mapping using reference numbers
    claim_ref_map = {}  # Map reference numbers to claim IDs
    for claim in claims:
        # Find reference numbers in claim text
        import re
        ref_matches = re.findall(r'[\[\\(](\d+(?:,\s*\d+)*)[\]\)]', claim.claim_text)
        for match in ref_matches:
            for ref in match.split(','):
                ref = ref.strip()
                if ref.isdigit():
                    claim_ref_map[ref] = claim_records[claims.index(claim)]["id"] if claim in claims else None

    citation_records = []
    for cite in citations:
        claim_id = None

        # Try to map by reference number first
        if cite.reference_number and cite.reference_number in claim_ref_map:
            claim_id = claim_ref_map[cite.reference_number]
        else:
            # Fallback to claim text matching
            claim_id = claim_text_to_id.get(cite.claim_text)

        if not claim_id and claim_records:
            claim_id = claim_records[0]["id"]  # Fallback to first claim

        result = admin.from_("citations").insert({
            "document_id": document_id,
            "claim_id": claim_id,
            "citation_text": cite.citation_text,
            "reference_number": cite.reference_number,
            "doi": cite.doi,
        }).execute()

        if result.data:
            citation_records.append({
                "id": result.data[0]["id"],
                "citation_text": cite.citation_text,
                "doi": cite.doi,
                "reference_number": cite.reference_number,
                "claim_id": claim_id  # Track which claim this citation belongs to
            })
            logger.info(f"Citation '{cite.reference_number}' mapped to claim_id={claim_id}")
        else:
            logger.warning(f"Citation failed to insert")

    logger.info(f"Document {document_id}: saved {len(citation_records)} citations to database")

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
                "abstract": pub_meta.abstract,
                "full_text_url": pub_meta.full_text_url,
                "retrieval_status": "completed" if (pub_meta.abstract or pub_meta.full_text_url) else "partial",
            }).execute()
            if result.data:
                publication_records.append({
                    "id": result.data[0]["id"],
                    "citation_id": cite["id"],
                    "title": pub_meta.title,
                    "authors": pub_meta.authors,
                    "doi": pub_meta.doi,
                    "publication_year": pub_meta.publication_year,
                    "source_url": pub_meta.source_url,
                    "abstract": pub_meta.abstract,
                    "full_text_url": pub_meta.full_text_url,
                })
    logger.info(f"Document {document_id}: retrieved {len(publication_records)} publications (expected: {len(citation_records)})")

    # 6. Extract evidence passages using evidence extractor
    evidence_records = []
    for claim in claim_records:
        # Find publications for this claim's citations
        claim_citations = [c for c in citation_records if c.get("claim_id") == claim["id"]]
        if not claim_citations:
            logger.warning(f"Claim {claim['id']}: no citations mapped, skipping evidence extraction")
            continue

        claim_pubs = [p for p in publication_records if p["citation_id"] in [c["id"] for c in claim_citations]]

        if not claim_pubs:
            logger.warning(f"Claim: no publications found for its citations, skipping evidence extraction")
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
            # Find the publication ID by matching title and ID for reliability
            pub_id = None
            for p in claim_pubs:
                if p["title"] == passage.publication_id and p["id"]:
                    pub_id = p["id"]
                    break

            if pub_id:
                result = admin.from_("evidence").insert({
                    "claim_id": claim["id"],
                    "publication_id": pub_id,
                    "evidence_text": passage.text[:5000],
                    "source_location": passage.source_location,
                }).execute()
                if result.data:
                    evidence_records.append(result.data[0])
            else:
                logger.warning(f"Could not find publication ID for evidence passage")

    logger.info(f"Document: extracted {len(evidence_records)} evidence passages total")

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
    from app.services.ai_verification import ClaimWithEvidence, AIVerificationService
    ai_verification = AIVerificationService()
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

    logger.info(f"Document: {len(claim_objects)} claim objects prepared for verification")
    verifications = []

    if not claim_objects:
        logger.warning(f"Document: no claims to verify")
    else:
        logger.info(f"Document: verifying {len(claim_objects)} claims")
        batch_result = await ai_verification.verify_batch(claim_objects)
        verifications = batch_result.verifications

        # Log batch errors if any
        if batch_result.errors:
            logger.warning(f"Batch verification completed with {len(batch_result.errors)} errors: {batch_result.errors}")

        # Save verifications
        verifications = []
        for claim_obj, verification in zip(claim_objects, batch_result.verifications):
            result = admin.from_("verifications").insert({
                "claim_id": claim_obj.claim_id,
                "verdict": verification.verdict.value,
                "confidence_score": verification.confidence_score,
                "explanation": verification.explanation,
                "evidence_status": verification.evidence_status,
                "model_version": settings.GEMINI_MODEL if settings.AI_PROVIDER == "gemini" else settings.CLAUDE_MODEL,
            }).execute()
            if result.data:
                verifications.append({
                    "id": result.data[0]["id"],
                    "claim_id": claim_obj.claim_id,
                    "verdict": verification.verdict.value,
                    "confidence_score": verification.confidence_score,
                    "explanation": verification.explanation,
                    "evidence_status": verification.evidence_status,
                })
            else:
                logger.warning(f"Failed to save verification for claim {claim_obj.claim_id}")
        logger.info(f"Document: saved {len(verifications)} verifications")

    return {
        "claims": claim_records,
        "citations": citation_records,
        "publications": publication_records,
        "evidence": evidence_records,
        "verifications": verifications
    }