import {
  BookOpen,
  Download,
  LifeBuoy,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useState } from 'react';
import { PageIntro } from '@/components/PageIntro';

export function HelpCenter() {
  const [activeSection, setActiveSection] = useState<string>('getting-started');
  const [searchQuery, setSearchQuery] = useState('');

  const sections = [
    {
      id: 'getting-started',
      title: 'Getting Started',
      icon: Sparkles,
      content: (
        <div className="help-section">
          <h3>How to Upload a PDF</h3>
          <p>Uploading a research paper for verification is simple:</p>
          <ol className="help-list">
            <li>Navigate to the <strong>Verify Document</strong> page from the sidebar.</li>
            <li>Drag and drop a PDF or DOCX file onto the upload zone, or click to browse.</li>
            <li>Ensure the file is under 20 MB and in PDF or DOCX format.</li>
            <li>Click <strong>Start Verification</strong> to queue the document for processing.</li>
          </ol>
          <div className="help-note">
            <strong>Tip:</strong> Documents with clear bibliographies and well-structured claims process faster and yield better results.
          </div>
        </div>
      ),
    },
    {
      id: 'how-it-works',
      title: 'How Document Verification Works',
      icon: ShieldCheck,
      content: (
        <div className="help-section">
          <p>VERITAS AI verifies research claims through a multi-stage pipeline:</p>
          <div className="steps-grid">
            <div className="step-card">
              <span className="step-number">1</span>
              <h4>PDF Upload & Text Extraction</h4>
              <p>Your PDF is securely stored and text is extracted page by page using PyMuPDF.</p>
            </div>
            <div className="step-card">
              <span className="step-number">2</span>
              <h4>Claim Extraction</h4>
              <p>Heuristic patterns identify scientific claims in the text (methods, results, conclusions).</p>
            </div>
            <div className="step-card">
              <span className="step-number">3</span>
              <h4>Citation Extraction</h4>
              <p>Bibliography is parsed to extract citations with DOIs, titles, and authors.</p>
            </div>
            <div className="step-card">
              <span className="step-number">4</span>
              <h4>Publication Retrieval</h4>
              <p>Crossref, OpenAlex, and Semantic Scholar are queried for each citation.</p>
            </div>
            <div className="step-card">
              <span className="step-number">5</span>
              <h4>Evidence Extraction</h4>
              <p>Relevant passages from abstracts and full-text PDFs are matched to each claim.</p>
            </div>
            <div className="step-card">
              <span className="step-number">6</span>
              <h4>AI Verification</h4>
              <p>Gemini compares each claim against retrieved evidence and assigns a verdict.</p>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'verdicts',
      title: 'Understanding the Six Verdicts',
      icon: ShieldCheck,
      content: (
        <div className="help-section">
          <p>Each claim receives one of six verdicts based on the evidence:</p>
          <div className="verdict-grid">
            <div className="verdict-card supported">
              <h4><span className="verdict-badge supported">SUPPORTED</span></h4>
              <p>Evidence directly and fully supports the claim.</p>
            </div>
            <div className="verdict-card partially-supported">
              <h4><span className="verdict-badge partial">PARTIALLY SUPPORTED</span></h4>
              <p>Evidence supports some aspects but not all, or supports a weaker version.</p>
            </div>
            <div className="verdict-card unsupported">
              <h4><span className="verdict-badge unsupported">UNSUPPORTED</span></h4>
              <p>Evidence neither confirms nor contradicts the claim.</p>
            </div>
            <div className="verdict-card contradictory">
              <h4><span className="verdict-badge contradictory">CONTRADICTORY</span></h4>
              <p>Evidence directly contradicts the claim.</p>
            </div>
            <div className="verdict-card potentially-outdated">
              <h4><span className="verdict-badge outdated">POTENTIALLY OUTDATED</span></h4>
              <p>Claim was supported at publication time but newer evidence suggests otherwise.</p>
            </div>
            <div className="verdict-card needs-review">
              <h4><span className="verdict-badge review">NEEDS REVIEW</span></h4>
              <p>Insufficient evidence retrieved, evidence inaccessible, or claim cannot be evaluated.</p>
            </div>
          </div>
          <p className="help-note">
            <strong>Note:</strong> VERITAS AI never fabricates evidence. When evidence is unavailable or ambiguous, the verdict defaults to <strong>NEEDS_REVIEW</strong>.
          </p>
        </div>
      ),
    },
    {
      id: 'reports',
      title: 'Downloading & Sharing Reports',
      icon: Download,
      content: (
        <div className="help-section">
          <h3>Generating a Report</h3>
          <p>
            After processing completes, open the document in the <strong>Analysis Workspace</strong> and click <strong>Export Report</strong>.
          </p>
          <h3>Downloading a Report</h3>
          <ol className="help-list">
            <li>Go to <strong>Saved Reports</strong> from the sidebar.</li>
            <li>Find the report you want and click the <strong>Download</strong> icon.</li>
            <li>The PDF will download with all claims, evidence, and verdicts.</li>
          </ol>
          <h3>Sharing Reports</h3>
          <p>
            Reports are PDFs with full claim evidence, citations, and verdict explanations. Share them via email, Slack, or your reference manager.
          </p>
        </div>
      ),
    },
    {
      id: 'troubleshooting',
      title: 'Troubleshooting',
      icon: LifeBuoy,
      content: (
        <div className="help-section">
          <h3>Common Issues & Solutions</h3>
          <div className="troubleshooting-grid">
            <div className="trouble-card">
              <h4>Upload failed</h4>
              <ul>
                <li>File must be PDF or DOCX, under 20 MB.</li>
                <li>Check your internet connection.</li>
                <li>Try a different browser if the issue persists.</li>
              </ul>
            </div>
            <div className="trouble-card">
              <h4>Processing stuck on "queued"</h4>
              <ul>
                <li>The background worker processes jobs every 30 seconds.</li>
                <li>Large PDFs (&gt;50 pages) may take several minutes.</li>
                <li>Check the <strong>Analysis Workspace</strong> for real-time status.</li>
              </ul>
            </div>
            <div className="trouble-card">
              <h4>Zero claims extracted</h4>
              <ul>
                <li>Scanned/image-only PDFs cannot be processed (OCR not yet supported).</li>
                <li>Ensure the PDF has selectable text.</li>
                <li>Documents without clear claims or bibliography will yield few results.</li>
              </ul>
            </div>
            <div className="trouble-card">
              <h4>Zero citations found</h4>
              <ul>
                <li>Document may lack a formal bibliography section.</li>
                <li>Citations must follow standard formats (e.g., [1], 1., Author et al.).</li>
              </ul>
            </div>
            <div className="trouble-card">
              <h4>All verdicts are NEEDS_REVIEW</h4>
              <ul>
                <li>No full-text evidence was accessible (paywalled sources).</li>
                <li>Citations lacked DOIs or retrievable metadata.</li>
                <li>This is a conservative verdict & not an error.</li>
              </ul>
            </div>
            <div className="trouble-card">
              <h4>Report download fails</h4>
              <ul>
                <li>Ensure processing completed successfully first.</li>
                <li>Check browser pop-up blocker settings.</li>
                <li>Try a different browser.</li>
              </ul>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'contact',
      title: 'Contact & Support',
      icon: LifeBuoy,
      content: (
        <div className="help-section">
          <p>Need more help? We&apos;re here to assist.</p>
          <div className="contact-options">
            <a href="mailto:support@veritas-ai.example.com" className="contact-link">
              <LifeBuoy size={20} /> Email Support
            </a>
            <a
              href="#"
              className="contact-link"
              onClick={(e) => {
                e.preventDefault();
                alert('Documentation coming soon');
              }}
            >
              <BookOpen size={20} /> Documentation
            </a>
            <a
              href="#"
              className="contact-link"
              onClick={(e) => {
                e.preventDefault();
                alert('Changelog coming soon');
              }}
            >
              <Sparkles size={20} /> Changelog
            </a>
          </div>
        </div>
      ),
    },
  ];

  const filteredSections = sections.filter((section) =>
    section.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeContent = sections.find(
    (section) => section.id === activeSection
  )?.content;

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="Support / Help Center"
        title="Help Center"
        description="Find answers, learn how verification works, and troubleshoot issues."
      />

      <div className="help-layout">
        <aside className="help-sidebar">
          <div className="help-search">
            <Search size={16} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search help..."
            />
          </div>

          <nav className="help-nav">
            {filteredSections.map((section) => (
              <button
                key={section.id}
                className={`help-nav-item ${activeSection === section.id ? 'active' : ''}`}
                onClick={() => setActiveSection(section.id)}
              >
                <section.icon size={16} />
                <span>{section.title}</span>
              </button>
            ))}
          </nav>
        </aside>

        <main className="help-content">
          {activeContent || (
            <div className="help-section">
              <h2>Section not found</h2>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}