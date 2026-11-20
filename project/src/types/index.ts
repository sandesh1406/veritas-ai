export type AnalysisStatus = 'Completed' | 'Processing' | 'Needs review';

export type AnalysisRecord = {
  id: string;
  document: string;
  analyzedAt: string;
  claims: number;
  supported: number;
  partial: number;
  unsupported: number;
  status: AnalysisStatus;
};

export type VerificationBreakdown = {
  name: string;
  value: number;
  count: number;
  color: string;
};

export type DashboardData = {
  documentsAnalyzed: number;
  claimsVerified: number;
  supportRate: number;
  flaggedClaims: number;
  records: AnalysisRecord[];
  verificationBreakdown: VerificationBreakdown[];
};

export type Profile = {
  id: string;
  full_name: string;
  email: string;
  avatar_url: string | null;
  created_at: string;
};

export type VerificationVerdict =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'UNSUPPORTED'
  | 'CONTRADICTORY'
  | 'POTENTIALLY_OUTDATED'
  | 'NEEDS_REVIEW'
  | 'Awaiting verification';

export type WorkspaceClaim = {
  id: string;
  text: string;
  status: VerificationVerdict;
  source: string;
  confidence: string;
};

export type WorkspaceData = {
  id: string;
  filename: string;
  processingStatus: string;
  createdAt: string;
  claims: WorkspaceClaim[];
};

export type ReportRecord = {
  id: string;
  document_id: string;
  title: string;
  date: string;
  claims: string;
  format: string;
  reportPath: string;
};

export type LibrarySource = {
  id: string;
  title: string;
  authors: string;
  type: string;
  year: string;
  doi: string;
  sourceUrl: string;
  retrievalStatus: string;
};

// API response types
export type DocumentStatusResponse = {
  document_id: string;
  processing_status: string;
  claims_extracted: number;
  citations_found: number;
  publications_retrieved: number;
  verifications_completed: number;
  error: string | null;
  updated_at: string;
};

export type DocumentResultsResponse = {
  document_id: string;
  filename: string;
  claims: Array<{
    id: string;
    claim_text: string;
    claim_type: string | null;
    page_number: number | null;
  }>;
  citations: Array<{
    id: string;
    claim_id: string;
    citation_text: string;
    reference_number: string | null;
    doi: string | null;
  }>;
  publications: Array<{
    id: string;
    citation_id: string;
    title: string;
    authors: string | null;
    doi: string | null;
    publication_year: number | null;
    source_url: string | null;
    retrieval_status: string;
  }>;
  evidence: Array<{
    id: string;
    claim_id: string;
    publication_id: string;
    evidence_text: string;
    source_location: string | null;
  }>;
  verifications: Array<{
    id: string;
    claim_id: string;
    verdict: string;
    confidence_score: number | null;
    explanation: string | null;
    evidence_status: string | null;
    model_version: string;
  }>;
};
