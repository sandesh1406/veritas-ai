import { ArrowRight, CheckCircle2, FileText } from 'lucide-react';
import type { AnalysisRecord } from '@/types';

function percentage(value: number, total: number) {
  return total ? Math.round(value / total * 100) : 0;
}

type AnalysisTableProps = {
  records: AnalysisRecord[];
  compact?: boolean;
  onViewAll?: () => void;
};

const statusClass: Record<AnalysisRecord['status'], string> = {
  Completed: 'status-complete',
  Processing: 'status-processing',
  'Needs review': 'status-review',
};

export function AnalysisTable({ records, compact = false, onViewAll }: AnalysisTableProps) {
  return (
    <section className={`panel analysis-panel ${compact ? 'compact' : ''}`}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Evidence queue</span>
          <h2>Recent Analysis</h2>
        </div>
        {onViewAll && <button className="text-button" onClick={onViewAll}>View All <ArrowRight size={15} /></button>}
      </div>
      <div className="table-wrap">
        <table className="analysis-table">
          <thead>
            <tr><th>Document</th><th>Claims</th><th>Supported</th><th>Partially</th><th>Unsupported</th><th>Status</th></tr>
          </thead>
          <tbody>
            {records.length ? records.map((record) => (
              <tr key={`${record.document}-${record.analyzedAt}`}>
                <td><div className="document-cell"><span className="pdf-icon"><FileText size={15} /></span><span><b>{record.document}</b><small>{record.analyzedAt}</small></span></div></td>
                <td>{record.claims}</td>
                <td className="success-text">{record.supported} ({percentage(record.supported, record.claims)}%)</td>
                <td className="warning-text">{record.partial} ({percentage(record.partial, record.claims)}%)</td>
                <td className="danger-text">{record.unsupported} ({percentage(record.unsupported, record.claims)}%)</td>
                <td><span className={`status-pill ${statusClass[record.status]}`}>{record.status === 'Completed' && <CheckCircle2 size={13} />}{record.status}</span></td>
              </tr>
            )) : <tr><td colSpan={6} className="empty-cell">No analysis matches your search.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
