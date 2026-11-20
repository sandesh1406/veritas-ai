import logging

logger = logging.getLogger(__name__)
import fitz  # PyMuPDF
from docx import Document as DocxDocument
import re
import logging
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
import uuid


@dataclass
class TextChunk:
    text: str
    page_number: int


@dataclass
class ExtractedClaim:
    claim_text: str
    claim_type: Optional[str]
    page_number: int
    confidence: float = 1.0


@dataclass
class ExtractedCitation:
    citation_text: str
    reference_number: Optional[str]
    doi: Optional[str]
    claim_text: str = ""
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None


class DocumentProcessor:
    """Extract text, claims, and citations from PDF/DOCX documents."""

    def __init__(self, max_claims: int = 50):
        self.max_claims = max_claims

    def extract_text(self, file_bytes: bytes, file_type: str) -> List[TextChunk]:
        """Extract text with page numbers from PDF or DOCX."""
        if file_type == "application/pdf":
            return self._extract_pdf(file_bytes)
        elif file_type in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"):
            return self._extract_docx(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def _extract_pdf(self, file_bytes: bytes) -> List[TextChunk]:
        chunks = []
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                chunks.append(TextChunk(text=text, page_number=page_num))
        doc.close()
        total_chars = sum(len(c.text) for c in chunks)
        logger.info(f"PDF extraction: {len(chunks)} pages, {total_chars} characters extracted")
        return chunks

    def _extract_docx(self, file_bytes: bytes) -> List[TextChunk]:
        """DOCX doesn't have reliable page numbers; treat as single page."""
        import io
        doc = DocxDocument(io.BytesIO(file_bytes))
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        return [TextChunk(text=full_text, page_number=1)]

    def find_bibliography_start(self, chunks: List[TextChunk]) -> Optional[int]:
        """
        Find the page/chunk where bibliography/references section starts.
        A genuine bibliography section:
        - Has a section header line (short, all caps or title case)
        - Contains multiple numbered/structured references
        - Is NOT just a passing mention of "References" in running text
        """
        bib_keywords = [
            r"\breferences\b", r"\bbibliography\b", r"\bworks\s+cited\b",
            r"\bliterature\s+cited\b", r"\breference\s+list\b"
        ]

        for i, chunk in enumerate(chunks):
            text_lower = chunk.text.lower()

            # Check for section header pattern
            lines = chunk.text.split("\n")
            header_found = False
            header_line_idx = -1

            for line_idx, line in enumerate(lines):
                line_stripped = line.strip()
                if len(line_stripped) > 100 or not line_stripped:
                    continue

                for kw in bib_keywords:
                    if re.search(kw, line.lower()):
                        # Check if this looks like a section header
                        is_header = (
                            line_stripped.isupper() or
                            line_stripped.istitle() or
                            (line_stripped.startswith(kw.replace(r"\b", "").replace(r"\\b", "")) and len(line_stripped) < 50)
                        )
                        if is_header:
                            header_found = True
                            header_line_idx = line_idx
                            break
                if header_found:
                    # Verify this chunk has multiple reference-like entries
                    # Count reference-like lines in this and subsequent chunks
                    ref_count = 0
                    for j in range(i, min(i + 3, len(chunks))):
                        chunk_text = chunks[j].text
                        # Look for numbered references like [1], 1., (1), etc.
                        ref_matches = re.findall(r'(?:^|\n)\s*(?:\[\d+\]|\d+\.|\(\d+\))', chunk_text)
                        ref_count += len(ref_matches)
                        # Also count et al. patterns
                        ref_count += len(re.findall(r'et\s+al\.', chunk_text, re.IGNORECASE))

                    if ref_count >= 2 or header_found:
                        return i

        return None

    def extract_claims(self, chunks: List[TextChunk]) -> List[ExtractedClaim]:
        """Extract evidence-checkable scientific claims from document text."""
    
        bib_idx = self.find_bibliography_start(chunks)
        main_chunks = chunks[:bib_idx] if bib_idx is not None else chunks
    
        logger.info(
            f"Claim extraction: searching {len(main_chunks)} chunks"
        )
    
        strong_patterns = [
            (r"\b(?:we|this study|our results|findings|results|data)\s+"
             r"(?:show|shows|showed|demonstrate|demonstrates|demonstrated|"
             r"indicate|indicates|indicated|suggest|suggests|suggested|"
             r"reveal|reveals|revealed|confirm|confirms|confirmed|found)\b", 0.95),
    
            (r"\b(?:increased|decreased|improved|reduced|enhanced|"
             r"outperformed|correlated|associated)\b", 0.85),
    
            (r"\b(?:accuracy|precision|recall|performance|efficiency|"
             r"survival|mortality|risk|error rate)\b", 0.80),
    
            (r"\b(?:significant|significantly|statistically significant|"
             r"p\s*[<>=]\s*0\.\d+)\b", 0.90),
    
            (r"\b(?:propose|proposed|develop|developed|introduce|"
             r"introduced|achieve|achieved|outperform)\b", 0.85),
    
            (r"\b(?:causes?|caused|leads? to|results? in|"
             r"associated with|correlated with|predicts?)\b", 0.80),
        ]
    
        scientific_terms = re.compile(
            r"\b(study|research|experiment|results|findings|data|"
            r"model|method|algorithm|system|patients|participants|"
            r"sample|accuracy|performance|effect|impact|risk|"
            r"correlation|prediction|analysis|measurement|"
            r"treatment|temperature|rate|percentage|population)\b",
            re.IGNORECASE,
        )
    
        factual_predicates = re.compile(
            r"\b(is|are|was|were|has|have|had|shows?|indicates?|"
            r"suggests?|demonstrates?|increases?|decreases?|"
            r"improves?|reduces?|achieves?|predicts?|"
            r"correlates?|affects?|causes?|remains?|"
            r"represents?|accounts for|outperforms?)\b",
            re.IGNORECASE,
        )
    
        excluded = re.compile(
            r"^(references|bibliography|acknowledgements?|"
            r"table of contents|figure \d+|table \d+|"
            r"keywords|abstract|introduction|conclusion)\b",
            re.IGNORECASE,
        )
    
        claims = []
        seen = set()
    
        for chunk in main_chunks:
            sentences = self._split_sentences(chunk.text)
    
            for sentence in sentences:
                sentence = re.sub(r"\s+", " ", sentence).strip()
    
                if len(sentence) < 35 or len(sentence) > 500:
                    continue
    
                if excluded.search(sentence):
                    continue
    
                if sentence.lower() in seen:
                    continue
    
                if not re.search(r"[a-zA-Z]", sentence):
                    continue
    
                confidence = 0.0
    
                # First: match explicit scientific claim patterns.
                for pattern, weight in strong_patterns:
                    if re.search(pattern, sentence, re.IGNORECASE):
                        confidence = max(confidence, weight)
    
                # Second: detect factual scientific statements that
                # don't use the exact phrases in the patterns.
                if (
                    confidence == 0.0
                    and scientific_terms.search(sentence)
                    and factual_predicates.search(sentence)
                ):
                    confidence = 0.65
    
                # Third: include quantitative research findings.
                if (
                    confidence == 0.0
                    and re.search(r"\d+(?:\.\d+)?\s*%|\bp\s*[<>=]", sentence, re.I)
                    and factual_predicates.search(sentence)
                ):
                    confidence = 0.70
    
                if confidence < 0.60:
                    continue
    
                seen.add(sentence.lower())
    
                claims.append(
                    ExtractedClaim(
                        claim_text=sentence[:500],
                        claim_type=self._classify_claim(sentence),
                        page_number=chunk.page_number,
                        confidence=confidence,
                    )
                )
    
                if len(claims) >= self.max_claims:
                    break
    
            if len(claims) >= self.max_claims:
                break
    
        claims.sort(key=lambda claim: claim.confidence, reverse=True)
    
        logger.info(
            f"Claim extraction completed: {len(claims)} claims found"
        )
    
        return claims
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences, handling common abbreviations."""
        # Protect common abbreviations
        abbreviations = [
            r"\bet\s+al\.", r"\bfig\.", r"\bfigs\.", r"\bsec\.", r"\bsecs\.",
            r"\bchap\.", r"\bchaps\.", r"\bvol\.", r"\bvols\.", r"\bno\.",
            r"\bpp\.", r"\bpg\.", r"\bpgs\.", r"\bcf\.", r"\bie\.", r"\beg\.",
            r"\bDr\.", r"\bProf\.", r"\bMr\.", r"\bMs\.", r"\bMrs\.",
            r"\bInc\.", r"\bLtd\.", r"\bCorp\.", r"\bCo\.", r"\bvs\.",
            r"\bJan\.", r"\bFeb\.", r"\bMar\.", r"\bApr\.", r"\bJun\.",
            r"\bJul\.", r"\bAug\.", r"\bSep\.", r"\bOct\.", r"\bNov\.", r"\bDec\.",
            r"\betc\.", r"\bi\.e\.", r"\be\.g\.", r"\bU\.S\.", r"\bU\.K\.",
            r"\bA\.I\.", r"\bM\.L\.", r"\bN\.L\.", r"\bP\.M\.", r"\bA\.M\.",
        ]

        protected_text = text
        placeholders = {}
        for i, abbr in enumerate(abbreviations):
            placeholder = f"__ABBR_{i}__"
            protected_text = re.sub(abbr, placeholder, protected_text)
            # Store the actual matched text
            match = re.search(abbr, text)
            placeholders[placeholder] = match.group(0) if match else abbr

        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", protected_text)

        # Restore abbreviations
        restored = []
        for sent in sentences:
            for placeholder, abbr in placeholders.items():
                sent = sent.replace(placeholder, abbr)
            restored.append(sent)

        return restored

    def _classify_claim(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["propose", "introduce", "develop", "novel", "new method", "new approach", "framework", "algorithm"]):
            return "methodological"
        elif any(w in text_lower for w in ["correlation", "association", "relationship", "correlated", "associated"]):
            return "correlational"
        elif any(w in text_lower for w in ["causal", "cause", "effect", "impact", "led to", "caused by", "results in"]):
            return "causal"
        elif "significant" in text_lower or "p <" in text_lower or "p-value" in text_lower or "p value" in text_lower:
            return "statistical"
        elif any(w in text_lower for w in ["predict", "prediction", "forecast", "estimate"]):
            return "predictive"
        return "general"

    def extract_citations(self, chunks: List[TextChunk]) -> List[ExtractedCitation]:
        """Extract citation references from bibliography section independently of claims."""
        bib_idx = self.find_bibliography_start(chunks)
        if bib_idx is None:
            logger.warning("Citation extraction: no bibliography section found")
            # Fallback: search entire document for citation patterns
            bib_chunks = chunks
        else:
            bib_chunks = chunks[bib_idx:]

        bib_text = "\n".join(c.text for c in bib_chunks)
        logger.info(f"Citation extraction: searching in {len(bib_chunks)} bibliography chunks ({len(bib_text)} chars)")

        citations = []

        # Enhanced patterns for different citation formats
        ref_patterns = [
            # [1] Author et al. Title. Journal, Year. DOI
            r"(?:^|\n)\s*[\[\]\\()]?(\d+)[\]()]?\s+(.+?)(?:\n\s*[\[\]()]?\d+[\]()]?|\Z)",
            # 1. Author et al. Title. Journal, Year.
            r"(?:^|\n)\s*(\d+)\.\s+(.+?)(?:\n\s*\d+\.|\Z)",
            # Author et al. (Year). Title. Journal.
            r"(?:^|\n)\s*([A-Z][a-z]+\s+et\s+al\.?\s*\(\d{4}\)).+?(?:\n\s*[A-Z][a-z]+\s+et\s+al\.?\s*\(\d{4}\)|\Z)",
        ]

        for pattern in ref_patterns:
            matches = list(re.finditer(pattern, bib_text, re.MULTILINE | re.DOTALL))
            if matches:
                for match in matches:
                    ref_num = match.group(1)
                    cite_text = match.group(2).strip()[:1000]
                    doi_match = re.search(r"10\.\d{4,}/[^\s]+", cite_text)
                    doi = doi_match.group(0) if doi_match else None

                    # Extract title, authors, year from citation
                    title = self._extract_title_from_citation(cite_text)
                    authors = self._extract_authors_from_citation(cite_text)
                    year = self._extract_year_from_citation(cite_text)

                    citations.append(ExtractedCitation(
                        citation_text=cite_text,
                        reference_number=ref_num,
                        doi=doi,
                        claim_text="",  # Will be mapped later
                        title=title,
                        authors=authors,
                        year=year
                    ))
                break

        logger.info(f"Citation extraction: found {len(citations)} citations")
        return citations

    def _extract_title_from_citation(self, citation: str) -> Optional[str]:
        """Extract likely title from citation text."""
        # Remove reference numbers
        text = re.sub(r"^[\[\]()']?\d+[\]()]?\s*", "", citation)

        # Common patterns: "Title. Journal, Year" or "Title. In: ..."
        # Title usually before first period followed by space and capital letter
        journal_markers = [
            r"\.\s+(?:In\s*:|Proc\.|Conf\.|Journal|IEEE|ACM|Nature|Science|Cell|[A-Z][a-z]+\s+\d{4})",
            r"\.\s+[A-Z][a-z]+\s+\d{4}",  # Journal Name Year
        ]

        for marker in journal_markers:
            match = re.search(r"^(.+?)" + marker, text)
            if match:
                return match.group(1).strip()

        # Fallback: first sentence up to reasonable length
        first_period = text.find(". ")
        if first_period > 10 and first_period < 200:
            return text[:first_period].strip()

        return text[:200].strip() if len(text) > 10 else None

    def _extract_authors_from_citation(self, citation: str) -> Optional[str]:
        """Extract authors from citation."""
        # Look for "Author et al." or "Author, Author, and Author" patterns
        author_patterns = [
            r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?)*)\s+et\s+al\.",
            r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?)*)\s*\(\d{4}\)",
            r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+and\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?)*)\s*\.",
        ]

        for pattern in author_patterns:
            match = re.search(pattern, citation)
            if match:
                return match.group(1).strip()
        return None

    def _extract_year_from_citation(self, citation: str) -> Optional[int]:
        """Extract year from citation."""
        year_match = re.search(r"(?:19|20)\d{2}", citation)
        if year_match:
            year = int(year_match.group(0))
            if 1900 <= year <= 2100:
                return year
        return None

    def map_claims_to_citations(
        self,
        claims: List[ExtractedClaim],
        citations: List[ExtractedCitation],
        chunks: List[TextChunk]
    ) -> List[ExtractedCitation]:
        """Map citations to claims based on reference numbers in text.
        Returns citations with claim_text populated where mapping succeeds.
        Citations that cannot be mapped keep claim_text empty.
        """
        if not citations or not claims:
            return citations

        # Build full text before bibliography
        bib_idx = self.find_bibliography_start(chunks)
        main_chunks = chunks[:bib_idx] if bib_idx is not None else chunks
        full_text = "\n".join(c.text for c in main_chunks)

        # Create reference number -> citation mapping
        ref_to_citation = {}
        for cite in citations:
            if cite.reference_number:
                ref_to_citation[cite.reference_number] = cite

        # Look for reference numbers in claim text context
        for claim in claims:
            claim_pos = full_text.find(claim.claim_text[:100])
            if claim_pos >= 0:
                context = full_text[max(0, claim_pos-300):claim_pos+len(claim.claim_text)+300]
                ref_matches = re.findall(r"[\[\\(](\d+(?:,\s*\d+)*)[\]\\)]", context)
                for match in ref_matches:
                    for num in match.split(","):
                        num = num.strip()
                        if num in ref_to_citation:
                            ref_to_citation[num].claim_text = claim.claim_text

        # Also map by proximity for unmapped citations
        for cite in citations:
            if not cite.claim_text and cite.reference_number:
                # Search backwards for nearest citation marker
                for claim in claims:
                    claim_pos = full_text.find(claim.claim_text[:100])
                    if claim_pos >= 0:
                        before_text = full_text[max(0, claim_pos-500):claim_pos]
                        ref_matches = list(re.finditer(r"[\[\\(](\d+)[\]\\)]", before_text))
                        if ref_matches:
                            nearest = ref_matches[-1].group(1)
                            if nearest == cite.reference_number and not cite.claim_text:
                                cite.claim_text = claim.claim_text

        return citations

    def extract_metadata(self, file_bytes: bytes, file_type: str) -> Dict:
        """Extract document metadata (title, authors, etc.)."""
        chunks = self.extract_text(file_bytes, file_type)
        full_text = "\n".join(c.text for c in chunks[:3])  # First few pages

        metadata = {
            "title": None,
            "authors": None,
            "abstract": None,
        }

        # Try to find title (usually in first few lines)
        lines = full_text.split("\n")
        for line in lines[:10]:
            line = line.strip()
            if len(line) > 10 and len(line) < 200 and not line.startswith(("Abstract", "ABSTRACT", "1.", "Introduction")):
                metadata["title"] = line
                break

        # Try to find authors
        for line in lines[:20]:
            if re.search(r"(?:author|by)\s*:", line, re.IGNORECASE):
                metadata["authors"] = line.split(":", 1)[1].strip()
                break

        # Try to find abstract
        abstract_match = re.search(r"(?:abstract|ABSTRACT)\s*:?\s*(.+?)(?:\n\s*(?:1\.|Introduction|Keywords|KEYWORDS)|$)",
                                   full_text, re.IGNORECASE | re.DOTALL)
        if abstract_match:
            metadata["abstract"] = abstract_match.group(1).strip()[:2000]

        return metadata
