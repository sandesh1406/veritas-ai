import type { LucideIcon } from 'lucide-react';

type MetricCardProps = {
  label: string;
  value: string;
  delta: string;
  tone: 'blue' | 'violet' | 'green' | 'orange';
  icon: LucideIcon;
  negative?: boolean;
};

export function MetricCard({ label, value, delta, tone, icon: Icon, negative = false }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon size={23} strokeWidth={1.8} /></div>
      <div className="metric-copy">
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
      <span className={`metric-delta ${negative ? 'negative' : ''}`}>{negative ? '↓' : '↑'} {delta}</span>
    </article>
  );
}
