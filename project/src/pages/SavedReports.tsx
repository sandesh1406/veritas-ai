import { Download, FileBarChart, MoreHorizontal, Plus, Search, Menu, X } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';
import { PageIntro } from '@/components/PageIntro';
import { api } from '@/services/api';
import type { ReportRecord } from '@/types';

// Helper to add timeout to a promise
function withTimeout<T>(promise: Promise<T>, ms: number, timeoutError: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(timeoutError)), ms)
    )
  ]);
}

export function SavedReports() {
  const [query, setQuery] = useState('');
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    let cancelled = false;

    const loadReports = async () => {
      try {
        // Add 30 second timeout to prevent infinite loading
        const data = await withTimeout(
          api.listReports(),
          30000,
          'Request timed out - unable to load reports'
        );
        if (!mounted) return;
        const transformed = data.map((report) => ({
          id: report.id,
          document_id: report.document_id,
          title: `${report.documents?.filename ?? 'Research document'} · Evidence Report`,
          date: `Created ${new Date(report.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`,
          claims: 'Verification report',
          format: report.report_path?.split('.').pop()?.toUpperCase() ?? 'FILE',
          reportPath: report.report_path,
        }));
        if (!mounted) return;
        setReports(transformed);
      } catch (error) {
        if (!mounted) return;
        console.error('Failed to load reports:', error);
        setMessage(error instanceof Error ? error.message : 'Unable to load saved reports right now.');
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    loadReports();

    return () => { mounted = false; };
  }, []);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const visibleReports = reports.filter((report) =>
    report.title.toLowerCase().includes(query.toLowerCase())
  );

  const downloadReport = async (report: ReportRecord, event: React.MouseEvent) => {
    event.stopPropagation();
    setOpenMenuId(null);
    try {
      const blob = await api.downloadReport(report.document_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report.title.replace(/[^a-z0-9.]/gi, '_').toLowerCase()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Delay revocation to ensure download has started (browser async behavior)
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      console.error('Download failed:', error);
      setMessage('Failed to download report. Please try again.');
    }
  };

  const toggleMenu = (reportId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setOpenMenuId(openMenuId === reportId ? null : reportId);
  };

  const handleMenuAction = (action: string, report: ReportRecord) => {
    setOpenMenuId(null);
    if (action === 'download') {
      downloadReport(report, { stopPropagation: () => {} } as React.MouseEvent);
    }
  };

  const renderReportRow = (report: ReportRecord) => (
    <div className="report-row" key={report.id}>
      <div className="report-icon">
        <FileBarChart size={20} />
      </div>
      <div className="report-copy">
        <strong>{report.title}</strong>
        <span>
          {report.date} · {report.claims}
        </span>
      </div>
      <span className="report-format">{report.format}</span>
      <button
        className="icon-button"
        onClick={(e) => downloadReport(report, e)}
        aria-label={`Download ${report.title}`}
      >
        <Download size={17} />
      </button>
      <div className="dropdown" ref={menuRef}>
        <button
          className="icon-button"
          onClick={(e) => toggleMenu(report.id, e)}
          aria-label="More options"
          aria-expanded={openMenuId === report.id}
        >
          <MoreHorizontal size={18} />
        </button>
        {openMenuId === report.id && (
          <div className="dropdown-menu" role="menu">
            <button
              className="dropdown-item"
              role="menuitem"
              onClick={() => handleMenuAction('download', report)}
            >
              <Download size={14} /> Download
            </button>
          </div>
        )}
      </div>
    </div>
  );

  const renderEmptyState = () => (
    <div className="empty-state panel">
      <FileBarChart size={27} />
      <h2>No saved reports yet</h2>
      <p>Reports generated from completed analyses will appear here.</p>
    </div>
  );

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="Workspace / Deliverables"
        title="Saved Reports"
        description="Find polished evidence summaries ready to share with your research team."
        action={
          <button className="primary-button" disabled>
            <Plus size={17} /> New report
          </button>
        }
      />
      <div className="reports-toolbar">
        <div className="search-field">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search reports"
          />
        </div>
        <span className="filter-count">
          {isLoading ? 'Loading...' : `${visibleReports.length} reports`}
        </span>
      </div>
      {message && <div className="form-message error-message">{message}</div>}
      <section className="panel reports-panel">
        {visibleReports.map(renderReportRow)}
        {!isLoading && !visibleReports.length && renderEmptyState()}
      </section>
    </div>
  );
}