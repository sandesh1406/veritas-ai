import { BookOpen, ExternalLink, Filter, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { PageIntro } from '@/components/PageIntro';
import { supabase } from '@/lib/supabase';
import type { LibrarySource } from '@/types';

export function ResearchLibrary() {
  const [query, setQuery] = useState('');
  const [sources, setSources] = useState<LibrarySource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    const loadLibrary = async () => {
      try {
        const { data, error } = await supabase
          .from('publications')
          .select('id, title, authors, doi, publication_year, source_url, retrieval_status')
          .order('created_at', { ascending: false });

        if (!mounted) return;

        if (error) {
          console.error('Failed to load library:', error);
          setError('Unable to load your research library right now.');
        } else {
          const transformed = (data ?? []).map((source) => ({
            id: String(source.id),
            title: String(source.title),
            authors: String(source.authors ?? 'Authors not listed'),
            type: 'Publication',
            year: source.publication_year ? String(source.publication_year) : 'Year not listed',
            doi: String(source.doi ?? ''),
            sourceUrl: String(source.source_url ?? ''),
            retrievalStatus: String(source.retrieval_status ?? 'queued'),
          }));
          setSources(transformed);
        }
      } catch (error) {
        if (mounted) {
          console.error('Failed to load library:', error);
          setError('Unable to load your research library right now.');
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    loadLibrary();
    return () => { mounted = false; };
  }, []);

  const visibleSources = useMemo(
    () =>
      sources.filter(
        (source) =>
          `${source.title} ${source.authors} ${source.doi}`.toLowerCase().includes(query.toLowerCase())
      ),
    [query, sources]
  );

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="Workspace / Source collection"
        title="Research Library"
        description="Keep trusted source material close to every claim review."
        action={
          <button className="secondary-button">
            <Filter size={16} /> Browse collections
          </button>
        }
      />
      <div className="library-toolbar">
        <div className="search-field large-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search papers, authors, or DOI"
          />
        </div>
        <span className="filter-count">{isLoading ? 'Loading...' : `${visibleSources.length} sources`}</span>
      </div>
      {error && <div className="form-message error-message">{error}</div>}
      <div className="source-grid">
        {visibleSources.map((source) => (
          <article className="source-card panel" key={source.id}>
            <div className="source-top">
              <div className="source-icon">
                <BookOpen size={20} />
              </div>
              <span className="source-type">{source.retrievalStatus}</span>
            </div>
            <span className="source-type">{source.type} · {source.year}</span>
            <h2>{source.title}</h2>
            <p>{source.authors}</p>
            {source.doi && (
              <div className="tag-list">
                <span>DOI {source.doi}</span>
              </div>
            )}
            <a
              className="source-link"
              href={source.sourceUrl || `https://doi.org/${source.doi}`}
              target="_blank"
              rel="noreferrer"
            >
              Open source <ExternalLink size={14} />
            </a>
          </article>
        ))}
        {!isLoading && !visibleSources.length && (
          <div className="empty-state panel">
            <BookOpen size={27} />
            <h2>Your research library is ready</h2>
            <p>Publications linked to your verified citations will appear here.</p>
          </div>
        )}
      </div>
    </div>
  );
}