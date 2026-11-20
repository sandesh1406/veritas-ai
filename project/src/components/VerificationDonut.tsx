import { BarChart3 } from 'lucide-react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { VerificationBreakdown } from '@/types';

type VerificationDonutProps = { data: VerificationBreakdown[] };

export function VerificationDonut({ data }: VerificationDonutProps) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  const supportRate = data.find((item) => item.name === 'Supported')?.value ?? 0;
  return <section className="panel donut-panel">
    <div className="panel-heading"><div><span className="eyebrow">Claim outcomes</span><h2>Claim Verification Overview</h2></div><span className="panel-icon"><BarChart3 size={16} /></span></div>
    <div className="donut-content">
      <div className="donut-chart">{total ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={59} outerRadius={79} paddingAngle={1} startAngle={90} endAngle={-270} stroke="none">{data.map((entry) => <Cell key={entry.name} fill={entry.color} />)}</Pie><Tooltip contentStyle={{ background: '#171b37', border: '1px solid #353b62', borderRadius: 10, color: '#fff' }} formatter={(value: number) => [`${value.toFixed(1)}%`, 'Share']} /></PieChart></ResponsiveContainer> : <div className="donut-empty">No claims yet</div>}<div className="donut-label"><strong>{supportRate.toFixed(1)}%</strong><span>Supported</span></div></div>
      <div className="legend-list">{data.map((item) => <div className="legend-row" key={item.name}><span className="legend-label"><i style={{ background: item.color }} />{item.name}</span><b>{item.count} ({item.value.toFixed(1)}%)</b></div>)}</div>
    </div>
  </section>;
}
