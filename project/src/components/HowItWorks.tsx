import { ArrowRight, CloudUpload, FileSearch, Layers3, Link2, ScrollText } from 'lucide-react';

const steps = [
  { number: '1', title: 'Upload Paper', detail: 'PDF, DOCX, or Research File', icon: CloudUpload },
  { number: '2', title: 'Extract Claims', detail: 'Identify key scientific claims', icon: ScrollText },
  { number: '3', title: 'Analyze Citations', detail: 'Detect and map references', icon: Link2 },
  { number: '4', title: 'Verify Evidence', detail: 'Retrieve & compare sources', icon: Layers3 },
  { number: '5', title: 'Get Report', detail: 'Support, gaps & explanations', icon: FileSearch },
];

export function HowItWorks() {
  return <section className="panel how-panel"><div className="panel-heading"><div><span className="eyebrow">The Veritas workflow</span><h2>How It Works</h2></div></div><div className="steps-row">{steps.map((step, index) => <div className="step-group" key={step.number}><div className="step-card"><div className="step-icon"><step.icon size={24} /></div><strong>{step.number}. {step.title}</strong><span>{step.detail}</span></div>{index < steps.length - 1 && <ArrowRight className="step-arrow" size={21} />}</div>)}</div></section>;
}
