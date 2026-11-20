import type { ReactNode } from 'react';

type PageIntroProps = { eyebrow: string; title: string; description: string; action?: ReactNode };

export function PageIntro({ eyebrow, title, description, action }: PageIntroProps) {
  return <div className="page-intro"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{action && <div className="intro-action">{action}</div>}</div>;
}
