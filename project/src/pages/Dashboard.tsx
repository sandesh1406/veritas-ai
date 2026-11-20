import { ArrowRight, CheckCircle2, FileCheck2, FileText, Flag, Layers3, Play, UploadCloud, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnalysisTable } from '@/components/AnalysisTable';
import { HowItWorks } from '@/components/HowItWorks';
import { MetricCard } from '@/components/MetricCard';
import { VerificationDonut } from '@/components/VerificationDonut';
import { api, HealthResponse } from '@/services/api';
import type { DashboardData } from '@/types';

const emptyData: DashboardData = {
  documentsAnalyzed: 0,
  claimsVerified: 0,
  supportRate: 0,
  flaggedClaims: 0,
  records: [],
  verificationBreakdown: [
    { name: 'Supported', value: 0, count: 0, color: '#4ade97' },
    { name: 'Partially Supported', value: 0, count: 0, color: '#f4c35b' },
    { name: 'Unsupported', value: 0, count: 0, color: '#fa656c' },
  ],
};

function classifyVerdict(verdict: string): 'supported' | 'partial' | 'unsupported' {
  const normalized = verdict.toLowerCase().replace(/[-_]/g, ' ');
  if (normalized.includes('partial') || normalized.includes('mixed')) return 'partial';
  if (normalized.includes('support')) return 'supported';
  return 'unsupported';
}

function statusLabel(status: string): 'Completed' | 'Processing' | 'Needs review' {
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Needs review';
  return 'Processing';
}

function transformApiData(documents: any[], claims: any[], verifications: any[]): DashboardData {
  const claimByDocument = new Map<string, typeof claims>();
  claims.forEach((claim) => {
    const docClaims = claimByDocument.get(claim.document_id) ?? [];
    claimByDocument.set(claim.document_id, [...docClaims, claim]);
  });

  const latestVerificationByClaim = new Map<string, typeof verifications[0]>();
  verifications.forEach((verification) => {
    const previous = latestVerificationByClaim.get(verification.claim_id);
    if (!previous || new Date(verification.created_at).getTime() > new Date(previous.created_at).getTime()) {
      latestVerificationByClaim.set(verification.claim_id, verification);
    }
  });

  const records = documents.map((document) => {
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
      { name: 'Supported', value: totalVerified ? (totals.supported / totalVerified) * 100 : 0, count: totals.supported, color: '#4ade97' },
      { name: 'Partially Supported', value: totalVerified ? (totals.partial / totalVerified) * 100 : 0, count: totals.partial, color: '#f4c35b' },
      { name: 'Unsupported', value: totalVerified ? (totals.unsupported / totalVerified) * 100 : 0, count: totals.unsupported, color: '#fa656c' },
    ],
  };
}

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData>(emptyData);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    let mounted = true;

    // Check API health first
    api.healthCheck()
      .then(() => {
        if (!mounted) return;
        setIsConnected(true);
        // Load dashboard data from API
        return Promise.all([
          api.listDocuments(),
          api.request('/claims').then(r => r.json()).catch(() => []),
          api.request('/verifications').then(r => r.json()).catch(() => []),
        ]);
      })
      .then((results) => {
        if (!mounted || !results) return;
        const documents = results[0] || [];
        const claims = results[1] || [];
        const verifications = results[2] || [];
        const transformed = transformApiData(documents, claims, verifications);
        setData(transformed);
      })
      .catch((error) => {
        if (!mounted) return;
        setIsConnected(false);
        setLoadError('Unable to connect to verification service. Check your connection.');
        console.error('Dashboard load error:', error);
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });

    return () => { mounted = false; };
  }, []);

  return (
    <div className="dashboard-page">
      <section className="hero-section">
        <div className="hero-copy">
          <span className="hero-kicker">
            <CheckCircle2 size={14} /> VERITAS AI • Research Integrity
          </span>
          <h1>Verify Research Claims with <span>Trusted Evidence</span></h1>
          <p>Extract claims, analyze citations, retrieve original sources, and verify whether the evidence truly supports each claim — all in one intelligent platform.</p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => navigate('/verify')}>
              Verify a Document <ArrowRight size={17} />
            </button>
            <button className="secondary-button" onClick={() => navigate('/workspace')}>
              <Play size={16} /> View Workspace
            </button>
          </div>
        </div>
        <div className="hero-visual" aria-label="Evidence verification illustration">
          <div className="wave wave-one" />
          <div className="wave wave-two" />
          <div className="document-visual">
            <div className="doc-lines"><i /><i /><i /><i /><i /><i /><i /></div>
            <div className="doc-stamp"><CheckCircle2 size={33} /></div>
            <div className="doc-glass" />
          </div>
          <div className="signal-card signal-top"><CheckCircle2 size={16} /><span><b>Claim mapping</b><small>Structured review</small></span></div>
          <div className="signal-card signal-mid"><CheckCircle2 size={16} /><span><b>Citation links</b><small>Source matching</small></span></div>
          <div className="signal-card signal-right"><CheckCircle2 size={16} /><span><b>Evidence trace</b><small>Source comparison</small></span></div>
          <div className="signal-card signal-bottom"><FileCheck2 size={16} /><span><b>Research report</b><small>Clear explanations</small></span></div>
        </div>
      </section>
      <div className={`sample-banner ${loadError ? 'data-warning' : ''}`}>
        <span>
          <UploadCloud size={15} />
          {isLoading ? 'Loading live workspace' : isConnected ? 'Connected to verification service' : 'Verification service unavailable'}
        </span>
        <p>
          {loadError || (data.documentsAnalyzed ? 'Your private research activity is shown below.' : 'No documents yet. Upload a research paper to begin.')}
        </p>
        {!isConnected && !isLoading && (
          <button className="secondary-button" style={{marginTop: '8px'}} onClick={() => window.location.reload()}>
            <RotateCcw size={14} /> Retry Connection
          </button>
        )}
      </div>
      <section className="metric-grid">
        <MetricCard label="Documents Analyzed" value={String(data.documentsAnalyzed)} delta="Live" tone="blue" icon={FileText} />
        <MetricCard label="Claims Verified" value={String(data.claimsVerified)} delta="Live" tone="violet" icon={Layers3} />
        <MetricCard label="Overall Support Rate" value={`${data.supportRate.toFixed(1)}%`} delta="Live" tone="green" icon={CheckCircle2} />
        <MetricCard label="Flagged / Misleading Claims" value={String(data.flaggedClaims)} delta="Live" tone="orange" icon={Flag} negative />
      </section>
      <section className="dashboard-grid">
        <AnalysisTable records={isLoading ? [] : data.records} onViewAll={() => navigate('/history')} />
        <VerificationDonut data={data.verificationBreakdown} />
      </section>
      <HowItWorks />
    </div>
  );
}