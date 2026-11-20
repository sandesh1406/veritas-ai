import fitz  # PyMuPDF
import httpx
import asyncio
import re
import logging
from typing import List, Optional, Dict, Set, Tuple
from dataclasses import dataclass
from app.services.research_retrieval import ResearchRetrievalService, PublicationMetadata
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class EvidencePassage:
    text: str
    source_location: str  # "abstract", "full_text_page_N", "section:X"
    publication_id: str
    confidence: float = 1.0  # Confidence in relevance


class EvidenceExtractor:
    """Extract relevant evidence passages from publications for claim verification."""

    def __init__(self, research_service: ResearchRetrievalService):
        self.research_service = research_service

    async def extract_evidence_for_claim(
        self,
        claim_text: str,
        publications: List[PublicationMetadata],
        max_passages_per_pub: int = 3
    ) -> List[EvidencePassage]:
        """Extract evidence passages from publications relevant to a claim."""
        all_passages = []

        # Extract key terms from claim for relevance scoring
        claim_keywords = self._extract_keywords(claim_text)
        claim_entities = self._extract_entities(claim_text)

        for pub in publications:
            passages = []

            # 1. Use abstract if available
            if pub.abstract:
                relevant = self._find_relevant_passages(
                    claim_text, claim_keywords, claim_entities,
                    pub.abstract, "abstract", max_passages_per_pub
                )
                for passage in relevant:
                    passage.publication_id = pub.title
                    passages.append(passage)

            # 2. Try to fetch full text if open access (HTML/XML)
            if pub.full_text_url and not pub.full_text_url.startswith("[PDF_CONTENT:"):
                full_text = await self._fetch_full_text(pub.full_text_url)
                if full_text:
                    relevant = self._find_relevant_passages(
                        claim_text, claim_keywords, claim_entities,
                        full_text, "full_text", max_passages_per_pub
                    )
                    for passage in relevant:
                        passage.publication_id = pub.title
                        passages.append(passage)

            # 3. Handle PDF content marker
            if pub.full_text_url and pub.full_text_url.startswith("[PDF_CONTENT:"):
                pdf_url = pub.full_text_url.replace("[PDF_CONTENT:", "").rstrip("]")
                pdf_passages = await self._extract_pdf_passages(
                    claim_text, claim_keywords, claim_entities,
                    pdf_url, max_passages_per_pub
                )
                for passage in pdf_passages:
                    passage.publication_id = pub.title
                    passages.append(passage)

            all_passages.extend(passages[:max_passages_per_pub])

        # Sort all passages by confidence and return top results
        all_passages.sort(key=lambda p: p.confidence, reverse=True)
        return all_passages[:max_passages_per_pub * len(publications)]

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from text (words >= 4 chars, not stopwords)."""
        stopwords = {
            "this", "that", "with", "from", "have", "were", "been", "their", "there",
            "they", "them", "then", "than", "when", "where", "which", "what",
            "will", "would", "could", "should", "about", "after", "before",
            "because", "through", "during", "under", "over", "between",
            "among", "within", "across", "above", "below", "into", "onto",
            "upon", "since", "until", "while", "once", "such", "each",
            "other", "another", "some", "many", "more", "most", "much",
            "very", "also", "even", "only", "just", "still", "yet",
            "already", "often", "always", "never", "sometimes", "usually",
            "generally", "typically", "specifically", "particularly",
            "mainly", "primarily", "largely", "partially", "fully",
            "completely", "totally", "absolutely", "certainly",
            "definitely", "probably", "possibly", "likely", "unlikely",
        }

        words = set(re.findall(r'\b\w{4,}\b', text.lower()))
        return {w for w in words if w not in stopwords and not w.isdigit()}

    def _extract_entities(self, text: str) -> Set[str]:
        """Extract potential entities (capitalized phrases, numbers with units, etc.)."""
        entities = set()

        # Capitalized phrases (potential proper nouns)
        cap_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities.update(cap_phrases)

        # Numbers with units or percentages
        numbers = re.findall(r'\b\d+(?:\.\d+)?\s*(?:%|percent|fold|times?|x)\b', text, re.IGNORECASE)
        entities.update(numbers)

        # Statistical values
        stats = re.findall(r'\b(?:p\s*[<>=]\s*0\.\d+|CI\s*\d+%|OR\s*[\d.]+|RR\s*[\d.]+|HR\s*[\d.]+)\b', text, re.IGNORECASE)
        entities.update(stats)

        return entities

    def _find_relevant_passages(
        self,
        claim_text: str,
        claim_keywords: Set[str],
        claim_entities: Set[str],
        source_text: str,
        source_type: str,
        max_passages: int
    ) -> List[EvidencePassage]:
        """Find passages in source text most relevant to claim using multi-factor scoring."""
        if not source_text or not claim_keywords:
            return []

        # Split into sentences with context
        sentences = self._split_into_sentences_with_context(source_text)
        scored = []

        for i, (sent, context_before, context_after) in enumerate(sentences):
            sent = sent.strip()
            if len(sent) < 30 or len(sent) > 800:
                continue

            # Score based on multiple factors
            score = self._score_relevance(
                sent, claim_text, claim_keywords, claim_entities,
                context_before, context_after
            )

            if score >= 0.3:  # Minimum threshold
                # Determine source location more precisely
                location = self._determine_location(source_text, sent, source_type, i)
                scored.append((score, sent, location))

        # Sort by relevance and return top
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            EvidencePassage(text=sent, source_location=loc, publication_id="", confidence=score)
            for score, sent, loc in scored[:max_passages]
        ]

    def _split_into_sentences_with_context(self, text: str, context_window: int = 1) -> List[Tuple[str, str, str]]:
        """Split text into sentences with surrounding context."""
        # Simple sentence splitting (could be improved with spaCy/nltk if needed)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        results = []
        for i, sent in enumerate(sentences):
            before = " ".join(sentences[max(0, i-context_window):i]) if i > 0 else ""
            after = " ".join(sentences[i+1:min(len(sentences), i+1+context_window)]) if i < len(sentences)-1 else ""
            results.append((sent, before, after))
        return results

    def _score_relevance(
        self,
        sentence: str,
        claim_text: str,
        claim_keywords: Set[str],
        claim_entities: Set[str],
        context_before: str,
        context_after: str
    ) -> float:
        """Score sentence relevance to claim using multiple signals."""
        sent_lower = sentence.lower()
        sent_keywords = set(re.findall(r'\b\w{4,}\b', sent_lower))

        # 1. Keyword overlap (TF-IDF style)
        keyword_overlap = len(claim_keywords & sent_keywords)
        keyword_score = min(keyword_overlap / max(len(claim_keywords), 1) * 2, 1.0)

        # 2. Entity overlap (exact matches of proper nouns, numbers)
        sent_entities = self._extract_entities(sentence)
        entity_overlap = len(claim_entities & sent_entities)
        entity_score = min(entity_overlap / max(len(claim_entities), 1) * 1.5, 1.0) if claim_entities else 0

        # 3. Semantic similarity (sequence matcher on full text)
        semantic_score = SequenceMatcher(None, claim_text.lower(), sent_lower).ratio()

        # 4. Context bonus (keywords in surrounding sentences)
        context_text = f"{context_before} {sentence} {context_after}".lower()
        context_keywords = set(re.findall(r'\b\w{4,}\b', context_text))
        context_overlap = len(claim_keywords & context_keywords)
        context_score = min(context_overlap / max(len(claim_keywords), 1) * 0.5, 0.5)

        # 5. Length penalty (prefer medium-length sentences)
        length_penalty = 1.0
        if len(sentence) < 50:
            length_penalty = 0.8
        elif len(sentence) > 400:
            length_penalty = 0.9

        # Weighted combination
        total_score = (
            0.35 * keyword_score +
            0.25 * entity_score +
            0.20 * semantic_score +
            0.10 * context_score
        ) * length_penalty

        return min(total_score, 1.0)

    def _determine_location(
        self,
        source_text: str,
        sentence: str,
        source_type: str,
        sentence_index: int
    ) -> str:
        """Determine precise location of sentence in source."""
        if source_type == "abstract":
            return "abstract"

        # For full text, estimate page/section
        # Find position of sentence in text
        pos = source_text.find(sentence)
        if pos >= 0:
            # Rough page estimate (assuming ~3000 chars per page)
            page_est = max(1, pos // 3000 + 1)

            # Try to find section header before this position
            before_text = source_text[max(0, pos-500):pos]
            section_match = re.search(r'\n([A-Z][A-Za-z\s]{3,40})\n', before_text[::-1])
            if section_match:
                section = section_match.group(1)[::-1].strip()
                return f"section:{section}, page~{page_est}"

            return f"full_text_page_{page_est}"

        return "full_text"

    async def _fetch_full_text(self, url: str) -> Optional[str]:
        """Fetch full text from HTML/XML source with better extraction."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")

                    if "xml" in content_type or url.endswith(".xml"):
                        return self._extract_xml_text(resp.text)
                    elif "html" in content_type or url.endswith((".html", ".htm")):
                        return self._extract_html_text(resp.text)
                    else:
                        # Plain text or unknown
                        return resp.text[:100000]
        except Exception as e:
            logger.warning(f"Full text fetch failed for {url}: {e}")
        return None

    def _extract_html_text(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove scripts, styles, nav, footer
        html = re.sub(r'<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags but keep text
        text = re.sub(r'<[^>]+>', ' ', html)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()[:100000]

    def _extract_xml_text(self, xml: str) -> str:
        """Extract text from XML (e.g., JATS, NLM)."""
        # Remove XML tags but keep content
        text = re.sub(r'<[^>]+>', ' ', xml)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()[:100000]

    async def _extract_pdf_passages(
        self,
        claim_text: str,
        claim_keywords: Set[str],
        claim_entities: Set[str],
        pdf_url: str,
        max_passages: int
    ) -> List[EvidencePassage]:
        """Download and extract relevant passages from PDF with page tracking."""
        passages = []

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(pdf_url)
                if resp.status_code == 200:
                    doc = fitz.open(stream=resp.content, filetype="pdf")

                    for page_num, page in enumerate(doc, 1):
                        page_text = page.get_text()
                        if not page_text.strip():
                            continue

                        relevant = self._find_relevant_passages(
                            claim_text, claim_keywords, claim_entities,
                            page_text, "pdf", max_passages
                        )

                        # Update location with page number
                        for p in relevant:
                            p.source_location = f"pdf_page_{page_num}"
                            passages.append(p)

                        if len(passages) >= max_passages:
                            break

                    doc.close()
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")

        return passages[:max_passages]

    async def extract_evidence_batch(
        self,
        claims: List[Tuple[str, List[PublicationMetadata]]],
        max_passages_per_pub: int = 3
    ) -> Dict[str, List[EvidencePassage]]:
        """Extract evidence for multiple claims in parallel."""
        semaphore = asyncio.Semaphore(3)

        async def extract_one(claim_text: str, pubs: List[PublicationMetadata]) -> Tuple[str, List[EvidencePassage]]:
            async with semaphore:
                passages = await self.extract_evidence_for_claim(claim_text, pubs, max_passages_per_pub)
                return (claim_text, passages)

        tasks = [extract_one(claim, pubs) for claim, pubs in claims]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return {claim: passages for claim, passages in results}