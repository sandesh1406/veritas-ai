import { BookOpenCheck } from 'lucide-react';

export function BrandLogo() {
  return (
    <div className="brand-lockup">
      <div className="brand-mark" aria-hidden="true">
        <BookOpenCheck size={25} strokeWidth={1.8} />
      </div>
      <div>
        <div className="brand-name">Veritas AI</div>
        <div className="brand-tagline">Scientific Claim &amp; Citation Verifier</div>
      </div>
    </div>
  );
}
