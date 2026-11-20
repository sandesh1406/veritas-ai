import { ArrowLeft, ArrowRight, ExternalLink, FileSearch, Flag, Link2, Search, ShieldCheck, RotateCcw, AlertCircle, Download } from 'lucide-react';
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageIntro } from '@/components/PageIntro';
import { api, DocumentResultsResponse } from '@/services/api';
import type { WorkspaceData, WorkspaceClaim } from '@/types';

function statusClass(status: string) {
  const normalized = status.toLowerCase().replace(/\s+/g, '_');
  if (normalized === 'supported') return 'status-complete';
  if (normalized === 'partially_supported') return 'status-processing';
  if (normalized === 'contradictory' || normalized === 'potentially_outdated') return 'status-review danger';
  if (normalized === 'unsupported') return 'status-review danger';
  if (normalized === 'needs_review') return 'status-review';
  return 'status-processing';
}

function verdictColor(verdict: string) {
  const v = verdict.toLowerCase().replace(/\s+/g, '_');
  if (v === 'supported') return 'success-text';
  if (v === 'partially_supported') return 'warning-text';
  if (v === 'unsupported') return 'danger-text';
  if (v === 'contradictory') return 'danger-text';
  if (v === 'potentially_outdated') return 'warning-text';
  if (v === 'needs_review') return '';
  return '';
}

function transformApiToWorkspace(apiResults: DocumentResultsResponse): WorkspaceData {
  // Build lookup maps
  const evidenceByClaim = new Map<string, string[]>();
  apiResults.evidence.forEach((ev) => {
    if (!evidenceByClaim.has(ev.claim_id)) evidenceByClaim.set(ev.claim_id, []);
    evidenceByClaim.get(ev.claim_id)!.push(ev.evidence_text);
  });

  const publicationsByCitation = new Map<string, typeof apiResults.publications[0][]>();
  apiResults.publications.forEach((pub) => {
    if (!publicationsByCitation.has(pub.citation_id)) publicationsByCitation.set(pub.citation_id, []);
    publicationsByCitation.get(pub.citation_id)!.push(pub);
  });

  const verificationsByClaim = new Map<string, typeof apiResults.verifications[0]>();
  apiResults.verifications.forEach((v) => verificationsByClaim.set(v.claim_id, v));

  const citationsByClaim = new Map<string, typeof apiResults.citations[0][]>();
  apiResults.citations.forEach((cite) => {
    if (!citationsByClaim.has(cite.claim_id)) citationsByClaim.set(cite.claim_id, []);
    citationsByClaim.get(cite.claim_id)!.push(cite);
  });

  return {
    id: apiResults.document_id,
    filename: apiResults.filename,
    processingStatus: 'completed',
    createdAt: new Date().toISOString(),
    claims: apiResults.claims.map((claim) => {
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
        status: (verification?.verdict as WorkspaceClaim['status']) ?? 'Awaiting verification',
        source,
        confidence: verification?.confidence_score == null ? '—' : `${verification.confidence_score}%`,
      };
    }),
  };
}

export function AnalysisWorkspace() {
  const navigate = useNavigate();
  const params = useParams();
  const documentId = params.documentId as string | undefined;

  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<string>('');

  // Load initial workspace data
  useEffect(() => {
    let mounted = true;
    if (documentId) {
      api.getDocumentResults(documentId)
        .then((data) => {
          if (mounted) setWorkspace(transformApiToWorkspace(data));
        })
        .catch(async () => {
          // Fallback to getDocumentStatus
          try {
            const status = await api.getDocumentStatus(documentId);
            setProcessingStatus(status.processing_status);
            if (status.processing_status === 'completed') {
              const results = await api.getDocumentResults(documentId);
              if (mounted) setWorkspace(transformApiToWorkspace(results));
            }
          } catch {
            if (mounted) setError('Unable to load this analysis right now.');
          }
        })
        .finally(() => {
          if (mounted) setIsLoading(false);
        });
    } else {
      // No document ID - try to load the latest document for this user
      api.listDocuments()
        .then((documents) => {
          if (!mounted) return;
          if (documents.length > 0) {
            const latestDoc = documents[0];
            navigate(`/workspace/${latestDoc.id}`, { replace: true });
          } else {
            setIsLoading(false);
          }
        })
        .catch(() => {
          if (mounted) setIsLoading(false);
        });
    }
    return () => { mounted = false; };
  }, [documentId, navigate]);

  // Poll for processing status if document is not completed
  useEffect(() => {
    if (!workspace || !documentId) return;
    if (workspace.processingStatus === 'completed' || workspace.processingStatus === 'failed') return;

    const poll = async () => {
      try {
        const status = await api.getDocumentStatus(documentId);
        setProcessingStatus(status.processing_status);
        if (status.processing_status === 'completed' || status.processing_status === 'failed') {
          // Reload full workspace data
          if (status.processing_status === 'completed') {
            const results = await api.getDocumentResults(documentId);
            setWorkspace(transformApiToWorkspace(results));
          }
        }
      } catch (e) {
        console.error('Status poll failed:', e);
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [workspace, documentId]);

  const startProcessing = useCallback(async () => {
    if (!documentId) return;
    setIsProcessing(true);
    setError('');
    try {
      const result = await api.processDocument(documentId);
      setProcessingStatus(result.processing_status);
      if (result.processing_status === 'completed' || result.processing_status === 'failed') {
        if (result.processing_status === 'completed') {
          const results = await api.getDocumentResults(documentId);
          setWorkspace(transformApiToWorkspace(results));
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start processing');
    } finally {
      setIsProcessing(false);
    }
  }, [documentId]);

  const generateReport = useCallback(async () => {
    if (!documentId) return;
    setIsProcessing(true);
    try {
      await api.generateReport(documentId);
      // In a real app, you'd show a success toast or navigate to reports page
      alert('Report generated! Check the Reports page.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate report');
    } finally {
      setIsProcessing(false);
    }
  }, [documentId]);

  const filteredClaims = useMemo(() =>
    (workspace?.claims ?? []).filter((claim) =>
      claim.text.toLowerCase().includes(query.toLowerCase())
    ),
    [query, workspace]
  );

  const supported = workspace?.claims.filter((claim) =>
    claim.status.toLowerCase() === 'supported'
  ).length ?? 0;
  const partial = workspace?.claims.filter((claim) =>
    claim.status.toLowerCase() === 'partially_supported'
  ).length ?? 0;
  const unsupported = workspace?.claims.filter((claim) =>
  ['unsupported', 'contradictory', 'potentially_outdated']
    .includes(claim.status.toLowerCase())
).length ?? 0;

const needsReview = workspace?.claims.filter((claim) =>
  claim.status.toLowerCase() === 'needs_review'
).length ?? 0;
  const total = supported + partial + unsupported;
  const supportRate = total ? (supported / total) * 100 : 0;

  const isCompleted = workspace?.processingStatus === 'completed';
  const isFailed = workspace?.processingStatus === 'failed';
  const isProcessingStatus = workspace?.processingStatus === 'processing';

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="Analysis workspace / Live data"
        title={workspace?.filename ?? 'Analysis Workspace'}
        description={workspace
          ? 'A claim-by-claim evidence map for your uploaded research paper.'
          : 'Your latest uploaded document and its verification results will appear here.'}
        action={
          <button className="secondary-button" onClick={() => navigate('/history')}>
            <ArrowLeft size={16} /> Back to history
          </button>
        }
      />

      {error && <div className="form-message error-message">{error}</div>}

      {isLoading ? (
        <div className="panel empty-state">
          <div className="loading-orbit small" />
          <h2>Loading analysis</h2>
          <p>Retrieving your private document workspace.</p>
        </div>
      ) : !workspace ? (
        <div className="panel empty-state">
          <FileSearch size={27} />
          <h2>No document has been uploaded yet</h2>
          <p>Upload a research paper to create your first analysis workspace.</p>
          <button className="primary-button" onClick={() => navigate('/verify')}>
            Upload a document <ArrowRight size={16} />
          </button>
        </div>
      ) : (
        <>
          <div className="workspace-toolbar">
            <div className="workspace-file">
              <div className="pdf-icon large"><FileSearch size={18} /></div>
              <div>
                <strong>{workspace.filename}</strong>
                <span>
                  {isProcessingStatus ? 'Processing...' : isCompleted ? 'Analysis complete' : isFailed ? 'Processing failed' : `Processing status: ${workspace.processingStatus}`}
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {!isCompleted && !isProcessingStatus && !isFailed && (
                <button
                  className="primary-button"
                  disabled={isProcessing || !workspace.claims.length}
                  onClick={startProcessing}
                >
                  {isProcessing ? (
                    <>
                      <RotateCcw size={16} className="spin" /> Starting...
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={16} /> Start Verification
                    </>
                  )}
                </button>
              )}
              {isProcessingStatus && (
                <button className="secondary-button" disabled>
                  <RotateCcw size={16} className="spin" /> Processing...
                </button>
              )}
              {isFailed && (
                <button
                  className="primary-button"
                  onClick={startProcessing}
                >
                  <RotateCcw size={16} /> Retry Verification
                </button>
              )}
              {isCompleted && (
                <>
                  <button className="primary-button" onClick={generateReport} disabled={isProcessing}>
                    <Download size={16} /> Export Report
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="workspace-summary">
            <div><span>Claims extracted</span><strong>{workspace.claims.length}</strong></div>
            <div><span>Supported</span><strong className="success-text">{supported}</strong></div>
            <div><span>Partially supported</span><strong className="warning-text">{partial}</strong></div>
            <div><span>Unsupported</span><strong className="danger-text">{unsupported}</strong></div>
            <div className="workspace-progress">
              <div><span>Overall support rate</span><b>{supportRate.toFixed(1)}%</b></div>
              <div className="progress-track"><i style={{ width: `${supportRate}%` }} /></div>
            </div>
          </div>

          <section className="panel claims-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Evidence map</span>
                <h2>Claim Verification</h2>
              </div>
              <div className="claim-search">
                <Search size={15} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search claims"
                />
              </div>
            </div>

            {filteredClaims.length ? (
              <div className="claim-list">
                {filteredClaims.map((claim, index) => (
                  <article className="claim-row" key={claim.id}>
                    <span className="claim-number">{String(index + 1).padStart(2, '0')}</span>
                    <div className="claim-main">
                      <p>{claim.text}</p>
                      <div className="claim-meta">
                        <span className={`status-pill ${statusClass(claim.status)}`}>
                          {claim.status}
                        </span>
                        <span>
                          <Link2 size={14} /> {claim.source}
                        </span>
                        <span className="confidence">
                          {claim.confidence === '—' ? 'Awaiting confidence score' : `${claim.confidence} confidence`}
                        </span>
                        {claim.status !== 'Awaiting verification' && (
                          <span className={`verdict-badge ${verdictColor(claim.status)}`}>
                            {claim.status.replace(/_/g, ' ')}
                          </span>
                        )}
                      </div>
                    </div>
                    <button className="icon-button claim-action" aria-label="View evidence" disabled>
                      <ExternalLink size={16} />
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <Flag size={24} />
                <h2>{workspace.claims.length ? 'No claims match your search' : 'Claims are not available yet'}</h2>
                <p>
                  {workspace.claims.length
                    ? 'Try a different search term.'
                    : isProcessingStatus
                      ? 'Claims are being extracted and verified...'
                      : isFailed
                        ? 'Processing failed. Click "Retry Verification" to try again.'
                        : 'Click "Start Verification" to begin claim extraction and verification.'}
                </p>
              </div>
            )}
          </section>

          <div className="workspace-footer">
            <span>
              <Flag size={15} /> Verification results are provided by the connected analysis service.
            </span>
            <button className="text-button" onClick={() => navigate('/verify')}>
              Analyze another document <ArrowRight size={15} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}