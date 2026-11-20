"""Research retrieval service for VERITAS AI.

Integrates Crossref, OpenAlex, and Semantic Scholar with
deduplication, citation matching, and source metadata preservation.
"""

import re
import httpx
import asyncio
import logging
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from app.core.config import settings
from difflib import SequenceMatcher
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class PublicationMetadata:
    """Standardized publication metadata from all sources."""
    title: str
    authors: Optional[str]
    doi: Optional[str]
    publication_year: Optional[int]
    source_url: Optional[str]
    abstract: Optional[str] = None
    full_text_url: Optional[str] = None
    source: str = "unknown"  # crossref, openalex, semantic_scholar
    retrieval_status: str = "unknown"
    matched_source: Optional[str] = None  # Which source found this first
    confidence: float = 1.0  # Confidence in the match


class DeduplicationEngine:
    """Handles deduplication of publications across sources."""

    @staticmethod
    def _normalize_doi(doi: Optional[str]) -> Optional[str]:
        """Normalize DOI to lowercase, no prefix."""
        if not doi:
            return None
        doi = doi.strip()
        # Remove https://doi.org/ prefix
        doi = doi.replace("https://doi.org/", "").replace("doi.org/", "")
        # Remove any trailing punctuation
        doi = doi.rstrip(".,;)")
        return doi.lower()

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for comparison."""
        if not title:
            return ""
        # Remove punctuation, lowercase, normalize whitespace
        title = re.sub(r"[^\w\s]", " ", title.lower())
        title = re.sub(r"\s+", " ", title).strip()
        return title

    @staticmethod
    def _compute_similarity(str1: str, str2: str) -> float:
        """Compute similarity between two strings."""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower().strip(), str2.lower().strip()).ratio()

    @staticmethod
    def _authors_match(authors1: Optional[str], authors2: Optional[str], threshold: float = 0.7) -> bool:
        """Check if two author strings match."""
        if not authors1 and not authors2:
            return True
        if not authors1 or not authors2:
            return False

        # Extract last names for comparison
        def extract_last_names(author_str: str) -> Set[str]:
            names = re.split(r"[;,]", author_str)
            last_names = set()
            for name in names:
                name = name.strip()
                if "et al" in name.lower():
                    continue
                parts = name.split()
                if parts:
                    last_names.add(parts[-1].lower())
            return last_names

        names1 = extract_last_names(authors1)
        names2 = extract_last_names(authors2)

        if not names1 and not names2:
            return True
        if not names1 or not names2:
            return False

        intersection = names1 & names2
        union = names1 | names2
        return len(intersection) / len(union) >= threshold if union else False

    @staticmethod
    def _year_match(year1: Optional[int], year2: Optional[int], tolerance: int = 1) -> bool:
        """Check if two publication years match within tolerance."""
        if not year1 and not year2:
            return True
        if not year1 or not year2:
            return False
        return abs(year1 - year2) <= tolerance

    @classmethod
    def is_duplicate(
        cls,
        existing: PublicationMetadata,
        candidate: PublicationMetadata,
    ) -> bool:
        """Determine if candidate is a duplicate of existing publication.

        Two publications are considered duplicates if:
        - They have the same normalized DOI (primary), OR
        - They have similar titles AND matching authors AND matching years
        """
        # Primary: DOI match
        existing_doi = cls._normalize_doi(existing.doi)
        candidate_doi = cls._normalize_doi(candidate.doi)

        if existing_doi and candidate_doi and existing_doi == candidate_doi:
            return True

        # Secondary: title + authors + year match
        existing_norm_title = cls._normalize_title(existing.title)
        candidate_norm_title = cls._normalize_title(candidate.title)

        title_similarity = cls._compute_similarity(existing_norm_title, candidate_norm_title)
        if title_similarity < 0.75:  # Higher threshold for title similarity
            return False

        authors_match = cls._authors_match(existing.authors, candidate.authors)
        years_match = cls._year_match(existing.publication_year, candidate.publication_year)

        return authors_match and years_match

    @classmethod
    def merge_publications(
        cls,
        primary: PublicationMetadata,
        secondary: PublicationMetadata
    ) -> PublicationMetadata:
        """Merge two publication records, preferring data from primary but filling gaps from secondary."""
        return PublicationMetadata(
            title=primary.title,
            authors=primary.authors or secondary.authors,
            doi=primary.doi or secondary.doi,
            publication_year=primary.publication_year or secondary.publication_year,
            source_url=primary.source_url or secondary.source_url,
            abstract=primary.abstract or secondary.abstract,
            full_text_url=primary.full_text_url or secondary.full_text_url,
            source=primary.source,
            retrieval_status=primary.retrieval_status,
            matched_source=primary.matched_source or secondary.matched_source,
            confidence=max(primary.confidence, secondary.confidence),
        )


class CrossrefClient:
    def __init__(self):
        self.base_url = settings.CROSSREF_BASE_URL
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def search_by_doi(self, doi: str) -> Optional[PublicationMetadata]:
        try:
            # Normalize DOI
            normalized_doi = DeduplicationEngine._normalize_doi(doi)
            if not normalized_doi:
                return None

            resp = await self.client.get(f"{self.base_url}/works/{normalized_doi}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()["message"]
            return self._parse_work(data)
        except Exception as e:
            logger.warning(f"Crossref DOI lookup failed for {doi}: {e}")
            return None

    async def search_by_title(self, title: str, limit: int = 5) -> List[PublicationMetadata]:
        try:
            params = {"query.title": title, "rows": limit, "select": "DOI,title,author,published-print,published-online,issued,URL,abstract"}
            resp = await self.client.get(f"{self.base_url}/works", params=params)
            resp.raise_for_status()
            items = resp.json()["message"]["items"]
            results = []
            for item in items:
                parsed = self._parse_work(item)
                if parsed:
                    results.append(parsed)
            return results
        except Exception as e:
            logger.warning(f"Crossref title search failed for '{title}': {e}")
            return []

    def _parse_work(self, data: Dict) -> Optional[PublicationMetadata]:
        try:
            title = data.get("title", [""])[0] if data.get("title") else ""
            if not title:
                return None

            authors_list = []
            for author in data.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if given or family:
                    authors_list.append(f"{given} {family}".strip())
            authors = "; ".join(authors_list) if authors_list else None

            doi = data.get("DOI")

            year = None
            for date_field in ["published-print", "published-online", "issued"]:
                if date_field in data and "date-parts" in data[date_field]:
                    parts = data[date_field]["date-parts"][0]
                    if parts:
                        year = parts[0]
                        break

            url = data.get("URL")

            # Crossref sometimes has abstract in the response
            abstract = None
            if "abstract" in data:
                abstract = data["abstract"]
                # Clean up HTML tags if present
                abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            return PublicationMetadata(
                title=title,
                authors=authors,
                doi=doi,
                publication_year=year,
                source_url=url,
                abstract=abstract,
                source="crossref"
            )
        except Exception as e:
            logger.warning(f"Crossref parse failed: {e}")
            return None

    async def close(self):
        await self.client.aclose()


class OpenAlexClient:
    def __init__(self):
        self.base_url = settings.OPENALEX_BASE_URL
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def search_by_doi(self, doi: str) -> Optional[PublicationMetadata]:
        try:
            normalized_doi = DeduplicationEngine._normalize_doi(doi)
            if not normalized_doi:
                return None

            resp = await self.client.get(f"{self.base_url}/works/https://doi.org/{normalized_doi}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._parse_work(resp.json())
        except Exception as e:
            logger.warning(f"OpenAlex DOI lookup failed for {doi}: {e}")
            return None

    async def search_by_title(self, title: str, limit: int = 5) -> List[PublicationMetadata]:
        try:
            params = {"filter": f"title.search:{quote(title)}", "per-page": limit}
            resp = await self.client.get(f"{self.base_url}/works", params=params)
            resp.raise_for_status()
            results = resp.json()["results"]
            parsed_results = []
            for r in results:
                parsed = self._parse_work(r)
                if parsed:
                    parsed_results.append(parsed)
            return parsed_results
        except Exception as e:
            logger.warning(f"OpenAlex title search failed for '{title}': {e}")
            return []

    def _parse_work(self, data: Dict) -> Optional[PublicationMetadata]:
        try:
            title = data.get("display_name", "")
            if not title:
                return None

            authors_list = []
            for authorship in data.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name")
                if name:
                    authors_list.append(name)
            authors = "; ".join(authors_list) if authors_list else None

            doi = data.get("doi")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi.replace("https://doi.org/", "")

            year = data.get("publication_year")

            url = data.get("doi") or data.get("id")

            # Check for open access full text
            full_text_url = None
            for location in data.get("locations", []):
                if location.get("is_oa") and location.get("pdf_url"):
                    full_text_url = location["pdf_url"]
                    break

            # Get abstract if available (OpenAlex has abstract_inverted_index)
            abstract = None
            if data.get("abstract_inverted_index"):
                # Reconstruct abstract from inverted index
                inverted = data["abstract_inverted_index"]
                word_positions = []
                for word, positions in inverted.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(word for _, word in word_positions)

            return PublicationMetadata(
                title=title,
                authors=authors,
                doi=doi,
                publication_year=year,
                source_url=url,
                abstract=abstract,
                full_text_url=full_text_url,
                source="openalex"
            )
        except Exception as e:
            logger.warning(f"OpenAlex parse failed: {e}")
            return None

    async def close(self):
        await self.client.aclose()


class SemanticScholarClient:
    def __init__(self):
        self.base_url = settings.SEMANTIC_SCHOLAR_BASE_URL
        headers = {}
        if settings.SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True)

    async def search_by_doi(self, doi: str) -> Optional[PublicationMetadata]:
        try:
            normalized_doi = DeduplicationEngine._normalize_doi(doi)
            if not normalized_doi:
                return None

            resp = await self.client.get(f"{self.base_url}/paper/DOI:{normalized_doi}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._parse_paper(resp.json())
        except Exception as e:
            logger.warning(f"Semantic Scholar DOI lookup failed for {doi}: {e}")
            return None

    async def search_by_title(self, title: str, limit: int = 5) -> List[PublicationMetadata]:
        try:
            params = {"query": title, "limit": limit, "fields": "title,authors,year,doi,url,abstract,openAccessPdf,publicationTypes"}
            resp = await self.client.get(f"{self.base_url}/paper/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for p in data.get("data", []):
                parsed = self._parse_paper(p)
                if parsed:
                    results.append(parsed)
            return results
        except Exception as e:
            logger.warning(f"Semantic Scholar title search failed for '{title}': {e}")
            return []

    def _parse_paper(self, data: Dict) -> Optional[PublicationMetadata]:
        try:
            title = data.get("title", "")
            if not title:
                return None

            authors_list = [a.get("name", "") for a in data.get("authors", []) if a.get("name")]
            authors = "; ".join(authors_list) if authors_list else None

            doi = data.get("doi")
            year = data.get("year")
            url = data.get("url")
            abstract = data.get("abstract")

            full_text_url = None
            if data.get("openAccessPdf") and data["openAccessPdf"].get("url"):
                full_text_url = data["openAccessPdf"]["url"]

            return PublicationMetadata(
                title=title,
                authors=authors,
                doi=doi,
                publication_year=year,
                source_url=url,
                abstract=abstract,
                full_text_url=full_text_url,
                source="semantic_scholar"
            )
        except Exception as e:
            logger.warning(f"Semantic Scholar parse failed: {e}")
            return None

    async def close(self):
        await self.client.aclose()


class ResearchRetrievalService:
    """Orchestrates retrieval from multiple sources with deduplication."""

    def __init__(self):
        self.crossref = CrossrefClient()
        self.openalex = OpenAlexClient()
        self.semantic_scholar = SemanticScholarClient()
        self._cache: Dict[str, PublicationMetadata] = {}

    def _cache_key(self, citation_text: str, doi: Optional[str]) -> str:
        """Generate cache key for a citation."""
        parts = []
        if doi:
            parts.append(f"doi:{DeduplicationEngine._normalize_doi(doi)}")
        parts.append(f"text:{hash(citation_text)}")
        return "|".join(parts)

    async def retrieve_publication(
        self,
        citation_text: str,
        doi: Optional[str] = None
    ) -> Optional[PublicationMetadata]:
        """Try to retrieve publication metadata with deduplication.

        Strategy:
        1. Check cache first
        2. Try DOI first across all sources, preferring results with abstract/full text
        3. Extract title from citation and search across sources
        4. Use deduplication to avoid returning duplicates from different sources
        5. Merge results from multiple sources
        6. Return best result with metadata and accessible content
        """

        # Check cache
        cache_key = self._cache_key(citation_text, doi)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Track candidates with their sources
        candidates: List[Tuple[PublicationMetadata, str]] = []  # (metadata, source)

        # Normalize DOI if provided
        normalized_doi = None
        if doi:
            normalized_doi = DeduplicationEngine._normalize_doi(doi)

        # 1. Try DOI first across all sources
        if normalized_doi:
            for client in [self.crossref, self.openalex, self.semantic_scholar]:
                result = await client.search_by_doi(normalized_doi)
                if result:
                    # Check for duplicates
                    is_dup = any(
                        DeduplicationEngine.is_duplicate(result, existing_md)
                        for existing_md, _ in candidates
                    )
                    if not is_dup:
                        candidates.append((result, client.__class__.__name__))
                        if result.abstract or result.full_text_url:
                            # Return first result with abstract/full text, but cache it
                            self._cache[cache_key] = result
                            return result

        # 2. Extract title from citation text for title search
        title = self._extract_title_from_citation(citation_text)
        if not title:
            # Return first DOI result if no title could be extracted
            if candidates:
                # Merge all candidates
                merged = self._merge_candidates(candidates)
                self._cache[cache_key] = merged
                return merged
            return None

        # 3. Try title search across sources
        for client in [self.crossref, self.openalex, self.semantic_scholar]:
            try:
                results = await client.search_by_title(title, limit=5)
                for result in results:
                    # Check for duplicates with existing candidates
                    is_dup = any(
                        DeduplicationEngine.is_duplicate(result, existing_md)
                        for existing_md, _ in candidates
                    )
                    if not is_dup:
                        candidates.append((result, client.__class__.__name__))
                        # If this result has abstract or full text, return it
                        if result.abstract or result.full_text_url:
                            result.retrieval_status = "completed"
                            # Merge with any DOI results
                            merged = self._merge_candidates(candidates)
                            self._cache[cache_key] = merged
                            return merged
            except Exception as e:
                logger.warning(f"Title search failed for '{title}' from {client.__class__.__name__}: {e}")

        # 4. Return best effort result (might not have abstract/full text)
        if candidates:
            # Mark the best candidate
            best_result, best_source = candidates[0]
            best_result.retrieval_status = "partial"
            best_result.matched_source = best_source

            # Merge all candidates for completeness
            merged = self._merge_candidates(candidates)
            self._cache[cache_key] = merged
            return merged

        return None

    def _merge_candidates(self, candidates: List[Tuple[PublicationMetadata, str]]) -> PublicationMetadata:
        """Merge multiple candidates into the best publication record."""
        if not candidates:
            return None

        # Sort by quality: has abstract > has full_text > has DOI > source priority
        source_priority = {"crossref": 3, "openalex": 2, "semantic_scholar": 1}

        def quality_score(item: Tuple[PublicationMetadata, str]) -> Tuple:
            md, source = item
            return (
                1 if md.abstract else 0,
                1 if md.full_text_url else 0,
                1 if md.doi else 0,
                source_priority.get(source, 0),
            )

        candidates.sort(key=quality_score, reverse=True)
        primary, primary_source = candidates[0]
        primary.matched_source = primary_source

        # Merge additional info from other sources
        merged = primary
        for candidate, source in candidates[1:]:
            merged = DeduplicationEngine.merge_publications(merged, candidate)
            if not merged.matched_source:
                merged.matched_source = source

        return merged

    def _extract_title_from_citation(self, citation: str) -> Optional[str]:
        """Extract likely title from citation text."""
        # Remove reference numbers
        text = re.sub(r"^[\[\]()']?\d+[\]()]?\s*", "", citation)
        text = text.strip()

        # Handle common citation formats
        # Format: "Title. Journal, Year." or "Title. In: Book/Conf, Year."
        # Title usually ends with a period before journal markers

        # Try patterns that end with period before journal/conf markers
        patterns = [
            r"^(.+?)\.\s+(?:In\s*:|Proc\.|Conf\.|Proceedings|Journal|IEEE|ACM|Nature|Science|Cell|[A-Z][a-z]+\s+(?:Journal|Review|Letters))\b",
            r"^(.+?)\.\s+[A-Z][a-z]+\s+\d{4}",  # Journal Name Year
            r"^(.+?)\.\s+\d{4}",  # Title. Year
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                title = match.group(1).strip()
                if 10 <= len(title) <= 300:
                    return title

        # Fallback: first sentence up to reasonable length
        first_period = text.find(". ")
        if first_period > 10 and first_period < 250:
            return text[:first_period].strip()

        # Last resort: first 200 chars
        return text[:200].strip() if len(text) > 10 else None

    async def fetch_full_text(self, publication: PublicationMetadata) -> Optional[str]:
        """Attempt to fetch full text from open access URL."""
        if not publication.full_text_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(publication.full_text_url)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "pdf" in content_type or publication.full_text_url.endswith(".pdf"):
                        return f"[PDF_CONTENT:{publication.full_text_url}]"
                    return resp.text[:100000]  # Limit size
        except Exception as e:
            logger.warning(f"Full text fetch failed for {publication.full_text_url}: {e}")
        return None

    async def retrieve_batch(
        self,
        citations: List[Tuple[str, Optional[str]]]
    ) -> List[Optional[PublicationMetadata]]:
        """Retrieve multiple publications in parallel with rate limiting."""
        semaphore = asyncio.Semaphore(3)  # Limit concurrent requests

        async def retrieve_one(citation_text: str, doi: Optional[str]) -> Optional[PublicationMetadata]:
            async with semaphore:
                return await self.retrieve_publication(citation_text, doi)

        tasks = [retrieve_one(cite_text, doi) for cite_text, doi in citations]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def close(self):
        await self.crossref.close()
        await self.openalex.close()
        await self.semantic_scholar.close()