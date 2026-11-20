from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTORY = "CONTRADICTORY"
    POTENTIALLY_OUTDATED = "POTENTIALLY_OUTDATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DocumentProcessRequest(BaseModel):
    document_id: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    processing_status: ProcessingStatus
    claims_extracted: int = 0
    citations_found: int = 0
    publications_retrieved: int = 0
    verifications_completed: int = 0
    error: Optional[str] = None
    updated_at: datetime


class ClaimExtracted(BaseModel):
    id: str
    claim_text: str
    claim_type: Optional[str] = None
    page_number: Optional[int] = None


class CitationExtracted(BaseModel):
    id: str
    claim_id: str
    citation_text: str
    reference_number: Optional[str] = None
    doi: Optional[str] = None


class PublicationRetrieved(BaseModel):
    id: str
    citation_id: str
    title: str
    authors: Optional[str] = None
    doi: Optional[str] = None
    publication_year: Optional[int] = None
    source_url: Optional[str] = None
    retrieval_status: str
    abstract: Optional[str] = None
    full_text_url: Optional[str] = None


class EvidenceExtracted(BaseModel):
    id: str
    claim_id: str
    publication_id: str
    evidence_text: str
    source_location: Optional[str] = None


class VerificationResult(BaseModel):
    id: str
    claim_id: str
    verdict: VerificationVerdict
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    explanation: Optional[str] = None
    evidence_status: Optional[str] = None
    model_version: str


class DocumentResultsResponse(BaseModel):
    document_id: str
    filename: str
    claims: List[ClaimExtracted]
    citations: List[CitationExtracted]
    publications: List[PublicationRetrieved]
    evidence: List[EvidenceExtracted]
    verifications: List[VerificationResult]


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"


class DocumentUploadResponse(BaseModel):
    """Response for document upload."""
    document_id: str
    filename: str
    storage_path: str
    file_type: str
    file_size: int
    processing_status: ProcessingStatus


class ReportGenerateRequest(BaseModel):
    """Request to generate a verification report."""
    document_id: str


class ReportResponse(BaseModel):
    """Response for report generation."""
    report_id: str
    document_id: str
    storage_path: str
    download_url: str
    file_size: int


class SupabaseHealthResponse(BaseModel):
    """Response for Supabase health check."""
    status: str
    database_connected: bool
    auth_connected: bool
    storage_connected: bool
    error: Optional[str] = None


class AIProviderInfo(BaseModel):
    """Response for AI provider info."""
    provider: str
    model: str
    available: bool