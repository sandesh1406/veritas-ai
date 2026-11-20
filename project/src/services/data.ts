import type { AnalysisRecord, DashboardData, ReportRecord, WorkspaceData, DocumentResultsResponse, VerificationVerdict } from '@/types';
import { supabase } from '@/lib/supabase';
import { api } from '@/services/api';

const breakdownColors = { supported: '#4ade97', partial: '#f4c35b', unsupported: '#fa656c' } as const;

type DocumentRow = {
  id: string;
  filename: string;
  storage_path: string;
  file_type: string;
  file_size: number;
  processing_status: string;
  created_at: string;
};

type ClaimRow = {
  id: string;
  document_id: string;
  claim_text: string;
  created_at: string;
};

type VerificationRow = {
  id: string;
  claim_id: string;
  verdict: string;
  confidence_score: number | null;
  explanation: string | null;
  evidence_status: string | null;
  created_at: string;
};

function classifyVerdict(verdict: string): 'supported' | 'partial' | 'unsupported' {
  const normalized = verdict.toLowerCase().replace(/[-_]/g, ' ');
  if (normalized.includes('partial') || normalized.includes('mixed')) return 'partial';
  if (normalized.includes('support')) return 'supported';
  return 'unsupported';
}

function statusLabel(status: string): AnalysisRecord['status'] {
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Needs review';
  return 'Processing';
}

async function getDashboardDataFromApi(): Promise<DashboardData> {
  try {
    const [documents, statusRes, verifications] = await Promise.all([
      api.listDocuments(),
      api.healthCheck(),
      api.request('/verifications').then(r => r.json()).catch(() => []),
    ]);

    // Build maps from API data
    const claimByDocument = new Map<string, ClaimRow[]>();

    // Get claims from each document
    for (const doc of documents) {
      try {
        const results = await api.getDocumentResults(doc.id);
        const docClaims: ClaimRow[] = results.claims.map((c) => ({
          id: c.id,
          document_id: doc.id,
          claim_text: c.claim_text,
          created_at: new Date().toISOString(),
        }));
        claimByDocument.set(doc.id, docClaims);
      } catch {
        claimByDocument.set(doc.id, []);
      }
    }

    const latestVerificationByClaim = new Map<string, VerificationRow>();
    verifications.forEach((verification: any) => {
      const previous = latestVerificationByClaim.get(verification.claim_id);
      if (!previous || new Date(verification.created_at).getTime() > new Date(previous.created_at).getTime()) {
        latestVerificationByClaim.set(verification.claim_id, verification);
      }
    });

    const records: AnalysisRecord[] = documents.map((document) => {
      const documentClaims = claimByDocument.get(document.id) ?? [];
      const counts = { supported: 0, partial: 0, unsupported: 0 };
      documentClaims.forEach((claim) => {
        const verification = latestVerificationByClaim.get(claim.id);
        if (verification) counts[classifyVerdict(verification.verdict)] += 1;
      });
      return {
        id: document.id,
        document: document.filename,
        analyzedAt: new Date(document.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }),
        claims: documentClaims.length,
        supported: counts.supported,
        partial: counts.partial,
        unsupported: counts.unsupported,
        status: statusLabel(document.processing_status),
      };
    });

    const totals = { supported: 0, partial: 0, unsupported: 0 };
    latestVerificationByClaim.forEach((verification) => { totals[classifyVerdict(verification.verdict)] += 1; });
    const totalVerified = totals.supported + totals.partial + totals.unsupported;

    return {
      documentsAnalyzed: documents.length,
      claimsVerified: totalVerified,
      supportRate: totalVerified ? (totals.supported / totalVerified) * 100 : 0,
      flaggedClaims: totals.unsupported,
      records,
      verificationBreakdown: [
        { name: 'Supported', value: totalVerified ? (totals.supported / totalVerified) * 100 : 0, count: totals.supported, color: breakdownColors.supported },
        { name: 'Partially Supported', value: totalVerified ? (totals.partial / totalVerified) * 100 : 0, count: totals.partial, color: breakdownColors.partial },
        { name: 'Unsupported', value: totalVerified ? (totals.unsupported / totalVerified) * 100 : 0, count: totals.unsupported, color: breakdownColors.unsupported },
      ],
    };
  } catch (error) {
    throw new Error('Unable to load dashboard data from API');
  }
}

async function getDashboardDataFromSupabase(): Promise<DashboardData> {
  const [documentsResult, claimsResult, verificationsResult] = await Promise.all([
    supabase.from('documents').select('id, filename, storage_path, file_type, file_size, processing_status, created_at').order('created_at', { ascending: false }),
    supabase.from('claims').select('id, document_id, claim_text, created_at'),
    supabase.from('verifications').select('id, claim_id, verdict, confidence_score, explanation, evidence_status, created_at'),
  ]);

  if (documentsResult.error || claimsResult.error || verificationsResult.error) {
    throw new Error('Unable to load workspace data.');
  }

  const documents = (documentsResult.data ?? []) as DocumentRow[];
  const claims = (claimsResult.data ?? []) as ClaimRow[];
  const verifications = (verificationsResult.data ?? []) as VerificationRow[];

  return transformData(documents, claims, verifications);
}

async function getDashboardData(): Promise<DashboardData> {
  // Try API first, fall back to Supabase
  try {
    return await getDashboardDataFromApi();
  } catch (apiError) {
    console.warn('API dashboard load failed, falling back to Supabase:', apiError);
    return await getDashboardDataFromSupabase();
  }
}

export async function getWorkspaceData(documentId?: string): Promise<WorkspaceData | null> {
  try {
    const results = documentId
      ? await api.getDocumentResults(documentId)
      : await api.getDocumentResults((await api.listDocuments())[0]?.id || '');

    if (!results) return null;

    // Build lookup maps
    const evidenceByClaim = new Map<string, string[]>();
    results.evidence.forEach((ev) => {
      if (!evidenceByClaim.has(ev.claim_id)) evidenceByClaim.set(ev.claim_id, []);
      evidenceByClaim.get(ev.claim_id)!.push(ev.evidence_text);
    });

    const publicationsByCitation = new Map<string, typeof results.publications[0][]>();
    results.publications.forEach((pub) => {
      if (!publicationsByCitation.has(pub.citation_id)) publicationsByCitation.set(pub.citation_id, []);
      publicationsByCitation.get(pub.citation_id)!.push(pub);
    });

    const verificationsByClaim = new Map<string, typeof results.verifications[0]>();
    results.verifications.forEach((v) => verificationsByClaim.set(v.claim_id, v));

    const citationsByClaim = new Map<string, typeof results.citations[0][]>();
    results.citations.forEach((cite) => {
      if (!citationsByClaim.has(cite.claim_id)) citationsByClaim.set(cite.claim_id, []);
      citationsByClaim.get(cite.claim_id)!.push(cite);
    });

    return {
      id: results.document_id,
      filename: results.filename,
      processingStatus: 'completed',
      createdAt: new Date().toISOString(),
      claims: results.claims.map((claim) => {
        const verification = verificationsByClaim.get(claim.id);
        const citations = citationsByClaim.get(claim.id) ?? [];
        const evidence = evidenceByClaim.get(claim.id) ?? [];
        const pubs = citations.flatMap((c) => publicationsByCitation.get(c.id) ?? []);

        // Build source string
        let source = 'Evidence retrieval pending';
        if (pubs.length > 0) {
          source = pubs.map((p) => p.title).slice(0, 2).join('; ');
          if (pubs.length > 2) source += ` +${pubs.length - 2} more`;
        } else if (citations.length > 0) {
          source = citations.map((c) => c.reference_number ? `[${c.reference_number}]` : 'Citation').join(', ');
        }

        return {
          id: claim.id,
          text: claim.claim_text,
          status: (verification?.verdict as VerificationVerdict) ?? 'Awaiting verification',
          source,
          confidence: verification?.confidence_score == null ? '—' : `${verification.confidence_score}%`,
        };
      }),
    };
  } catch (error) {
    console.error('Failed to load workspace data:', error);
    return null;
  }
}

function transformData(
  documents: DocumentRow[],
  claims: ClaimRow[],
  verifications: VerificationRow[]
): DashboardData {
  const claimByDocument = new Map<string, ClaimRow[]>();
  claims.forEach((claim) => {
    const docClaims = claimByDocument.get(claim.document_id) ?? [];
    claimByDocument.set(claim.document_id, [...docClaims, claim]);
  });

  const latestVerificationByClaim = new Map<string, VerificationRow>();
  verifications.forEach((verification) => {
    const previous = latestVerificationByClaim.get(verification.claim_id);
    if (!previous || new Date(verification.created_at).getTime() > new Date(previous.created_at).getTime()) {
      latestVerificationByClaim.set(verification.claim_id, verification);
    }
  });

  const records: AnalysisRecord[] = documents.map((document) => {
    const documentClaims = claimByDocument.get(document.id) ?? [];
    const counts = { supported: 0, partial: 0, unsupported: 0 };
    documentClaims.forEach((claim) => {
      const verification = latestVerificationByClaim.get(claim.id);
      if (verification) counts[classifyVerdict(verification.verdict)] += 1;
    });
    return {
      id: document.id,
      document: document.filename,
      analyzedAt: new Date(document.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }),
      claims: documentClaims.length,
      supported: counts.supported,
      partial: counts.partial,
      unsupported: counts.unsupported,
      status: statusLabel(document.processing_status),
    };
  });

  const totals = { supported: 0, partial: 0, unsupported: 0 };
  latestVerificationByClaim.forEach((verification) => {
    totals[classifyVerdict(verification.verdict)] += 1;
  });
  const totalVerified = totals.supported + totals.partial + totals.unsupported;

  return {
    documentsAnalyzed: documents.length,
    claimsVerified: totalVerified,
    supportRate: totalVerified ? (totals.supported / totalVerified) * 100 : 0,
    flaggedClaims: totals.unsupported,
    records,
    verificationBreakdown: [
      { name: 'Supported', value: totalVerified ? (totals.supported / totalVerified) * 100 : 0, count: totals.supported, color: breakdownColors.supported },
      { name: 'Partially Supported', value: totalVerified ? (totals.partial / totalVerified) * 100 : 0, count: totals.partial, color: breakdownColors.partial },
      { name: 'Unsupported', value: totalVerified ? (totals.unsupported / totalVerified) * 100 : 0, count: totals.unsupported, color: breakdownColors.unsupported },
    ],
  };
}

export async function getReports(): Promise<ReportRecord[]> {
  // Try API first
  try {
    const results = await api.listReports();
    return results.map((report: any) => ({
      id: report.id,
      document_id: report.document_id,
      title: `${report.documents?.filename ?? 'Research document'} · Evidence Report`,
      date: `Created ${new Date(report.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`,
      claims: 'Verification report',
      format: report.report_path?.split('.').pop()?.toUpperCase() ?? 'FILE',
      reportPath: report.report_path,
    }));
  } catch (error) {
    console.warn('API reports load failed, falling back to Supabase:', error);

    // Fall back to Supabase
    const { data: reports, error: supabaseError } = await supabase.from('reports').select('id, document_id, report_path, created_at');
    if (supabaseError) throw new Error('Unable to load saved reports.');

    const reportRows = (reports ?? []) as Array<{
      id: string;
      document_id: string;
      report_path: string;
      created_at: string;
    }>;

    if (!reportRows.length) return [];

    const { data: documents, error: documentError } = await supabase.from('documents').select('id, filename').in('id', reportRows.map((report) => report.document_id));
    if (documentError) throw new Error('Unable to load report documents.');

    const filenames = new Map((documents ?? []).map((document) => [String(document.id), String(document.filename)]));

    return reportRows.map((report) => ({
      id: report.id,
      document_id: report.document_id,
      title: `${filenames.get(report.document_id) ?? 'Research document'} · Evidence Report`,
      date: `Created ${new Date(report.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`,
      claims: 'Verification report',
      format: report.report_path.split('.').pop()?.toUpperCase() ?? 'FILE',
      reportPath: report.report_path,
    }));
  }
}

export async function updateProfile(userId: string, fullName: string, avatarUrl: string | null) {
  const { error } = await supabase.from('profiles').update({ full_name: fullName.trim(), avatar_url: avatarUrl?.trim() || null }).eq('id', userId);
  if (error) {
    console.error('profile update failed', error);
    throw new Error('We could not save your profile. Please try again.');
  }
}

export async function getLibrarySources() {
  const { data, error } = await supabase.from('publications').select('id, title, authors, doi, publication_year, source_url, retrieval_status, created_at').order('created_at', { ascending: false });
  if (error) throw new Error('Unable to load the research library.');
  return (data ?? []).map((source) => ({
    id: String(source.id),
    title: String(source.title),
    authors: String(source.authors ?? 'Authors not listed'),
    type: 'Publication',
    year: source.publication_year ? String(source.publication_year) : 'Year not listed',
    doi: String(source.doi ?? ''),
    sourceUrl: String(source.source_url ?? ''),
    retrievalStatus: String(source.retrieval_status ?? 'queued'),
  }));
}

export async function createPrivateDownloadUrl(bucket: string, path: string) {
  const { data, error } = await supabase.storage.from(bucket).createSignedUrl(path, 60);
  if (error || !data?.signedUrl) {
    console.error('private download url failed', error);
    throw new Error('This file is not available right now.');
  }
  return data.signedUrl;
}

export async function uploadResearchDocument(userId: string, file: File): Promise<{ id: string }> {
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
  const storagePath = `${userId}/${crypto.randomUUID()}-${safeName}`;
  const { error: uploadError } = await supabase.storage.from('research-documents').upload(storagePath, file, { contentType: file.type, upsert: false });
  if (uploadError) {
    console.error('document upload failed', uploadError);
    throw new Error('We could not upload this document. Please try again.');
  }
  const { data, error: insertError } = await supabase.from('documents').insert({ filename: file.name, storage_path: storagePath, file_type: file.type, file_size: file.size }).select('id').maybeSingle();
  if (insertError || !data) {
    await supabase.storage.from('research-documents').remove([storagePath]);
    console.error('document record creation failed', insertError);
    throw new Error('We could not save this document. Please try again.');
  }
  return { id: String(data.id) };
}