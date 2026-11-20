import { CalendarDays, ChevronDown, Filter, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnalysisTable } from '@/components/AnalysisTable';
import { PageIntro } from '@/components/PageIntro';
import { api } from '@/services/api';
import type { AnalysisRecord, DocumentResultsResponse } from '@/types';

export function AnalysisHistory() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All statuses');
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    const loadHistory = async () => {
      try {
        const documents = await api.listDocuments();

        if (!mounted) return;

        // For each completed document, fetch its results to get verification counts
        const enriched: AnalysisRecord[] = [];

        for (const doc of documents) {
          if (!mounted) return;

          let claims = 0, supported = 0, partial = 0, unsupported = 0;

          if (doc.processing_status === 'completed') {
            try {
              const results = await api.getDocumentResults(doc.id);
              claims = results.claims.length;
              for (const v of results.verifications) {
                const vLower = v.verdict.toLowerCase().replace(/_/g, ' ');
                if (vLower === 'supported') supported++;
                else if (vLower === 'partially supported') partial++;
                else unsupported++;
              }
            } catch (e) {
              console.warn(`Failed to load results for ${doc.id}:`, e);
            }
          }

          enriched.push({
            id: doc.id,
            document: doc.filename,
            analyzedAt: new Date(doc.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }),
            claims,
            supported,
            partial,
            unsupported,
            status: statusLabel(doc.processing_status),
          });
        }

        if (mounted) setRecords(enriched);
      } catch (error) {
        if (mounted) setError('Unable to load your analysis history right now.');
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    loadHistory();

    return () => { mounted = false; };
  }, []);

  const filteredRecords = useMemo(() =>
    records.filter((record) =>
      record.document.toLowerCase().includes(query.toLowerCase()) &&
      (status === 'All statuses' || record.status === status)
    ),
    [query, records, status]
  );

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="Workspace / Evidence log"
        title="Analysis History"
        description="Review every document your team has prepared, verified, and flagged."
        action={
          <button className="primary-button">
            <CalendarDays size={16} /> This month <ChevronDown size={15} />
          </button>
        }
      />
      <div className="filter-bar panel">
        <div className="search-field">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search documents"
          />
        </div>
        <label className="select-field">
          <Filter size={15} />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option>All statuses</option>
            <option>Completed</option>
            <option>Processing</option>
            <option>Failed</option>
            <option>Needs review</option>
          </select>
          <ChevronDown size={14} />
        </label>
        <span className="filter-count">
          {isLoading ? 'Loading...' : `${filteredRecords.length} documents`}
        </span>
      </div>
      {error && <div className="form-message error-message">{error}</div>}
      <AnalysisTable records={filteredRecords} />
    </div>
  );
}

function statusLabel(status: string): AnalysisRecord['status'] {
  if (status === 'completed') return 'Completed';
  if (status === 'processing') return 'Processing';
  if (status === 'failed') return 'Needs review';
  return 'Processing';
}