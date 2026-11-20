const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

type RequestOptions = RequestInit & {
  params?: Record<string, string>;
};

async function fetchWithAuth(
  path: string,
  options: RequestOptions = {}
): Promise<Response> {
  if (!API_BASE_URL) {
    throw new Error('The verification service is not connected yet.');
  }

  // Get Supabase session for auth token
  const { supabase } = await import('@/lib/supabase');
  const { data: { session } } = await supabase.auth.getSession();

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (session?.access_token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${session.access_token}`;
  }

  const url = new URL(`${API_BASE_URL}${path}`);
  if (options.params) {
    Object.entries(options.params).forEach(([key, value]) => {
      url.searchParams.append(key, value);
    });
  }

  const response = await fetch(url.toString(), {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    throw new Error(errorText || `Request failed with status ${response.status}`);
  }

  return response;
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  storage_path: string;
  file_type: string;
  file_size: number;
  processing_status: string;
}

export interface DocumentStatusResponse {
  document_id: string;
  processing_status: string;
  claims_extracted: number;
  citations_found: number;
  publications_retrieved: number;
  verifications_completed: number;
  error: string | null;
  updated_at: string;
}

export interface DocumentResultsResponse {
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
}

export interface ReportResponse {
  report_id: string;
  document_id: string;
  storage_path: string;
  download_url: string;
  file_size: number;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface AIProviderInfo {
  provider: string;
  model: string;
  available: boolean;
}

export const api = {
  baseUrl: API_BASE_URL,

  async request(path: string, init?: RequestInit): Promise<Response> {
    return fetchWithAuth(path, init);
  },

  // Document Upload
  async uploadDocument(file: File): Promise<DocumentUploadResponse> {
    const { supabase } = await import('@/lib/supabase');
    const { data: { session } } = await supabase.auth.getSession();

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/documents/upload`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${session?.access_token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      throw new Error(errorText || `Upload failed with status ${response.status}`);
    }

    return response.json();
  },

  // Document Processing
  async processDocument(documentId: string): Promise<DocumentStatusResponse> {
    const response = await fetchWithAuth(`/documents/${documentId}/process`, {
      method: 'POST',
    });
    return response.json();
  },

  async getDocumentStatus(documentId: string): Promise<DocumentStatusResponse> {
    const response = await fetchWithAuth(`/documents/${documentId}/status`);
    return response.json();
  },

  async getDocumentResults(documentId: string): Promise<DocumentResultsResponse> {
    const response = await fetchWithAuth(`/documents/${documentId}/results`);
    return response.json();
  },

  async listDocuments(): Promise<Array<{
    id: string;
    filename: string;
    storage_path: string;
    file_type: string;
    file_size: number;
    processing_status: string;
    created_at: string;
  }>> {
    const response = await fetchWithAuth('/documents');
    return response.json();
  },

  // Reports
  async generateReport(documentId: string): Promise<ReportResponse> {
    const response = await fetchWithAuth(`/documents/${documentId}/report`, {
      method: 'POST',
    });
    return response.json();
  },

  async downloadReport(documentId: string): Promise<Blob> {
    const response = await fetchWithAuth(`/documents/${documentId}/report/download`);
    return response.blob();
  },

  async listReports(): Promise<Array<{
    id: string;
    document_id: string;
    user_id: string;
    report_path: string;
    created_at: string;
    documents: { filename: string };
  }>> {
    const response = await fetchWithAuth('/reports');
    return response.json();
  },

  async getReports(): Promise<Array<{
    id: string;
    document_id: string;
    user_id: string;
    report_path: string;
    created_at: string;
    documents: { filename: string };
  }>> {
    return this.listReports();
  },

  // Health & Config
  async healthCheck(): Promise<HealthResponse> {
    const response = await fetchWithAuth('/health');
    return response.json();
  },

  async supabaseHealthCheck(): Promise<{
    status: string;
    database_connected: boolean;
    auth_connected: boolean;
    storage_connected: boolean;
    error: string | null;
  }> {
    const response = await fetchWithAuth('/health/supabase');
    return response.json();
  },

  async getAIProviderInfo(): Promise<AIProviderInfo> {
    const response = await fetchWithAuth('/ai/provider');
    return response.json();
  },
};