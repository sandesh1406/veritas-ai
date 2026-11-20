import io
from datetime import datetime
from typing import List, Optional
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from app.models.schemas import (
    ClaimExtracted, CitationExtracted, PublicationRetrieved,
    EvidenceExtracted, VerificationResult, VerificationVerdict
)


# Color palette matching VERITAS UI
DARK_NAVY = HexColor("#080b1b")
DARK_CARD = HexColor("#141a34")
PRIMARY_VIOLET = HexColor("#9d65ff")
PRIMARY_BLUE = HexColor("#6686ff")
GREEN = HexColor("#4ade97")
YELLOW = HexColor("#f4c35b")
RED = HexColor("#fa656c")
ORANGE = HexColor("#f09a67")
WHITE = HexColor("#f2f4ff")
TEXT_SOFT = HexColor("#a7afd0")
TEXT_FAINT = HexColor("#707a9f")
BORDER = HexColor("#293155")


VERDICT_COLORS = {
    VerificationVerdict.SUPPORTED: GREEN,
    VerificationVerdict.PARTIALLY_SUPPORTED: YELLOW,
    VerificationVerdict.UNSUPPORTED: RED,
    VerificationVerdict.CONTRADICTORY: RED,
    VerificationVerdict.POTENTIALLY_OUTDATED: ORANGE,
    VerificationVerdict.NEEDS_REVIEW: TEXT_FAINT,
}

VERDICT_LABELS = {
    VerificationVerdict.SUPPORTED: "SUPPORTED",
    VerificationVerdict.PARTIALLY_SUPPORTED: "PARTIALLY SUPPORTED",
    VerificationVerdict.UNSUPPORTED: "UNSUPPORTED",
    VerificationVerdict.CONTRADICTORY: "CONTRADICTORY",
    VerificationVerdict.POTENTIALLY_OUTDATED: "POTENTIALLY OUTDATED",
    VerificationVerdict.NEEDS_REVIEW: "NEEDS REVIEW",
}


class ReportGenerator:
    """Generate PDF verification reports."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            'VeritasTitle',
            parent=self.styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=28,
            leading=34,
            textColor=WHITE,
            spaceAfter=6,
            alignment=TA_LEFT,
        ))
        self.styles.add(ParagraphStyle(
            'VeritasSubtitle',
            parent=self.styles['Normal'],
            fontName='Helvetica',
            fontSize=13,
            leading=18,
            textColor=PRIMARY_VIOLET,
            spaceAfter=20,
            alignment=TA_LEFT,
        ))
        self.styles.add(ParagraphStyle(
            'SectionHeader',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=22,
            textColor=WHITE,
            spaceBefore=18,
            spaceAfter=10,
            borderWidth=0,
            borderPadding=0,
        ))
        self.styles.add(ParagraphStyle(
            'SubSectionHeader',
            parent=self.styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=TEXT_SOFT,
            spaceBefore=12,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            'BodyText2',
            parent=self.styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=WHITE,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
        ))
        self.styles.add(ParagraphStyle(
            'ClaimText',
            parent=self.styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=WHITE,
            spaceAfter=8,
            leftIndent=12,
            rightIndent=12,
            backColor=DARK_CARD,
            borderWidth=0.5,
            borderColor=BORDER,
            borderPadding=8,
            alignment=TA_JUSTIFY,
        ))
        self.styles.add(ParagraphStyle(
            'EvidenceText',
            parent=self.styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            leading=13,
            textColor=TEXT_SOFT,
            spaceAfter=6,
            leftIndent=18,
            rightIndent=12,
        ))
        self.styles.add(ParagraphStyle(
            'SmallMuted',
            parent=self.styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=TEXT_FAINT,
            spaceAfter=4,
        ))
        self.styles.add(ParagraphStyle(
            'TableHeader',
            parent=self.styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=WHITE,
            alignment=TA_CENTER,
        ))
        self.styles.add(ParagraphStyle(
            'TableCell',
            parent=self.styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=WHITE,
            alignment=TA_LEFT,
        ))
        self.styles.add(ParagraphStyle(
            'VerdictCell',
            parent=self.styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=WHITE,
            alignment=TA_CENTER,
        ))

    def generate_report(
        self,
        filename: str,
        claims: List[ClaimExtracted],
        citations: List[CitationExtracted],
        publications: List[PublicationRetrieved],
        evidence: List[EvidenceExtracted],
        verifications: List[VerificationResult],
    ) -> bytes:
        """Generate full verification report as PDF bytes."""

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=25*mm,
            rightMargin=25*mm,
            topMargin=20*mm,
            bottomMargin=20*mm,
        )

        story = []

        # ---- Cover Page ----
        story.append(Spacer(1, 40*mm))
        story.append(Paragraph("VERITAS AI", self.styles['VeritasTitle']))
        story.append(Paragraph("Scientific Claim & Citation Verification Report", self.styles['VeritasSubtitle']))
        story.append(Spacer(1, 10*mm))
        story.append(HRFlowable(width="80%", thickness=2, color=PRIMARY_VIOLET, spaceAfter=10*mm))
        story.append(Paragraph(f"Document: {filename}", self.styles['BodyText2']))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}", self.styles['SmallMuted']))
        story.append(Spacer(1, 15*mm))

        # Summary stats
        verdict_counts = self._count_verdicts(verifications)
        total_claims = len(claims)
        summary_data = [
            ["Metric", "Count"],
            ["Total Claims Analyzed", str(total_claims)],
            ["Citations Processed", str(len(citations))],
            ["Publications Retrieved", str(len(publications))],
            ["Evidence Passages Found", str(len(evidence))],
            ["", ""],
            ["Verification Outcomes", ""],
            ["Supported", str(verdict_counts.get(VerificationVerdict.SUPPORTED, 0))],
            ["Partially Supported", str(verdict_counts.get(VerificationVerdict.PARTIALLY_SUPPORTED, 0))],
            ["Unsupported", str(verdict_counts.get(VerificationVerdict.UNSUPPORTED, 0))],
            ["Contradictory", str(verdict_counts.get(VerificationVerdict.CONTRADICTORY, 0))],
            ["Potentially Outdated", str(verdict_counts.get(VerificationVerdict.POTENTIALLY_OUTDATED, 0))],
            ["Needs Review", str(verdict_counts.get(VerificationVerdict.NEEDS_REVIEW, 0))],
        ]

        summary_table = Table(summary_data, colWidths=[100*mm, 40*mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_CARD),
            ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [DARK_NAVY, DARK_CARD]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('SPAN', (0, 5), (-1, 5)),
            ('BACKGROUND', (0, 5), (-1, 5), PRIMARY_VIOLET),
            ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
        ]))
        story.append(summary_table)

        story.append(PageBreak())

        # ---- Limitations & Methodology ----
        story.append(Paragraph("Methodology & Limitations", self.styles['SectionHeader']))
        story.append(Paragraph(
            "This report presents the results of an automated verification process using VERITAS AI. "
            "The system extracts claims from the uploaded document, identifies cited references, retrieves "
            "publication metadata and accessible full text from Crossref, OpenAlex, and Semantic Scholar, "
            "and uses Claude AI to compare claims against retrieved evidence.",
            self.styles['BodyText2']
        ))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("Key Limitations:", self.styles['SubSectionHeader']))
        limitations = [
            "Full text access is limited to open-access publications; paywalled content cannot be retrieved.",
            "Claim extraction uses heuristic patterns and may miss implicit or nuanced claims.",
            "Citation parsing relies on bibliography formatting conventions and may not capture all references.",
            "AI verification is based solely on retrieved evidence passages; external knowledge is not used.",
            "Confidence scores reflect evidence quality and relevance, not absolute truth.",
            "NEEDS_REVIEW verdicts indicate insufficient accessible evidence, not necessarily an incorrect claim.",
        ]
        for lim in limitations:
            story.append(Paragraph(f"• {lim}", self.styles['BodyText2']))

        story.append(PageBreak())

        # ---- Claims & Verifications Detail ----
        story.append(Paragraph("Claim Verification Details", self.styles['SectionHeader']))

        # Build lookup maps
        citations_by_claim = {}
        for cite in citations:
            if cite.claim_id not in citations_by_claim:
                citations_by_claim[cite.claim_id] = []
            citations_by_claim[cite.claim_id].append(cite)

        pubs_by_citation = {}
        for pub in publications:
            if pub.citation_id not in pubs_by_citation:
                pubs_by_citation[pub.citation_id] = []
            pubs_by_citation[pub.citation_id].append(pub)

        evidence_by_claim = {}
        for ev in evidence:
            if ev.claim_id not in evidence_by_claim:
                evidence_by_claim[ev.claim_id] = []
            evidence_by_claim[ev.claim_id].append(ev)

        verifications_by_claim = {v.claim_id: v for v in verifications}

        for i, claim in enumerate(claims, 1):
            # Keep claim group together
            claim_elements = []

            # Claim header
            claim_elements.append(Paragraph(f"Claim {i}", self.styles['SubSectionHeader']))
            claim_elements.append(Paragraph(claim.claim_text, self.styles['ClaimText']))

            claim_meta = []
            if claim.claim_type:
                claim_meta.append(f"Type: {claim.claim_type}")
            if claim.page_number:
                claim_meta.append(f"Page: {claim.page_number}")
            if claim_meta:
                claim_elements.append(Paragraph(" | ".join(claim_meta), self.styles['SmallMuted']))

            # Citations for this claim
            claim_citations = citations_by_claim.get(claim.id, [])
            if claim_citations:
                claim_elements.append(Paragraph("Cited References:", self.styles['SubSectionHeader']))
                for cite in claim_citations:
                    cite_text = cite.citation_text[:300] + ("..." if len(cite.citation_text) > 300 else "")
                    claim_elements.append(Paragraph(f"[{cite.reference_number or '?'}] {cite_text}", self.styles['SmallMuted']))
                    if cite.doi:
                        claim_elements.append(Paragraph(f"DOI: {cite.doi}", self.styles['SmallMuted']))

            # Publications retrieved
            all_pubs = []
            for cite in claim_citations:
                all_pubs.extend(pubs_by_citation.get(cite.id, []))

            if all_pubs:
                claim_elements.append(Paragraph("Retrieved Publications:", self.styles['SubSectionHeader']))
                for pub in all_pubs:
                    pub_info = f"<b>{pub.title}</b>"
                    if pub.authors:
                        pub_info += f" — {pub.authors}"
                    if pub.publication_year:
                        pub_info += f" ({pub.publication_year})"
                    if pub.doi:
                        pub_info += f" | DOI: {pub.doi}"
                    claim_elements.append(Paragraph(pub_info, self.styles['BodyText2']))
                    if pub.abstract:
                        claim_elements.append(Paragraph(f"Abstract: {pub.abstract[:500]}...", self.styles['EvidenceText']))

            # Evidence passages
            claim_evidence = evidence_by_claim.get(claim.id, [])
            if claim_evidence:
                claim_elements.append(Paragraph("Supporting Evidence Passages:", self.styles['SubSectionHeader']))
                for ev in claim_evidence[:3]:  # Limit to 3 passages
                    pub = next((p for p in all_pubs if p.id == ev.publication_id), None)
                    pub_ref = f" (from: {pub.title[:50]}...)" if pub else ""
                    claim_elements.append(Paragraph(f"{ev.evidence_text[:800]}...{pub_ref}", self.styles['EvidenceText']))

            # Verification result
            verification = verifications_by_claim.get(claim.id)
            if verification:
                verdict_color = VERDICT_COLORS.get(verification.verdict, TEXT_FAINT)
                verdict_label = VERDICT_LABELS.get(verification.verdict, verification.verdict.value)

                claim_elements.append(Spacer(1, 3*mm))
                claim_elements.append(Paragraph("Verification Result:", self.styles['SubSectionHeader']))

                # Verdict badge table
                verdict_data = [[
                    Paragraph("VERDICT", self.styles['TableHeader']),
                    Paragraph(verdict_label, ParagraphStyle('VerdictBadge', parent=self.styles['VerdictCell'], textColor=verdict_color)),
                    Paragraph("CONFIDENCE", self.styles['TableHeader']),
                    Paragraph(f"{verification.confidence_score:.0f}%", self.styles['TableCell']),
                ]]
                verdict_table = Table(verdict_data, colWidths=[30*mm, 40*mm, 30*mm, 25*mm])
                verdict_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), DARK_CARD),
                    ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('SPAN', (1, 0), (1, 0)),  # verdict spans
                ]))
                claim_elements.append(verdict_table)

                if verification.explanation:
                    claim_elements.append(Spacer(1, 2*mm))
                    claim_elements.append(Paragraph("Explanation:", self.styles['SubSectionHeader']))
                    claim_elements.append(Paragraph(verification.explanation, self.styles['BodyText2']))

                if verification.evidence_status:
                    claim_elements.append(Paragraph(f"Evidence Status: {verification.evidence_status}", self.styles['SmallMuted']))

                claim_elements.append(Paragraph(f"Model: {verification.model_version}", self.styles['SmallMuted']))

            # Add claim group to story
            story.append(KeepTogether(claim_elements))
            if i < len(claims):
                story.append(Spacer(1, 6*mm))

        # ---- Unverified References ----
        # A citation is "verified" if there's at least one publication for it that has evidence linked to the claim
        # Build lookup: publication_id -> list of evidence for that publication
        evidence_by_pub = {}
        for ev in evidence:
            if ev.publication_id not in evidence_by_pub:
                evidence_by_pub[ev.publication_id] = []
            evidence_by_pub[ev.publication_id].append(ev)

        # Build lookup: citation_id -> list of publications
        pubs_by_citation = {}
        for pub in publications:
            if pub.citation_id not in pubs_by_citation:
                pubs_by_citation[pub.citation_id] = []
            pubs_by_citation[pub.citation_id].append(pub)

        # Check each citation: does it have at least one publication with evidence for the related claim?
        unverified_cites = []
        for cite in citations:
            claim_pubs = pubs_by_citation.get(cite.id, [])
            has_evidence = False
            for pub in claim_pubs:
                if pub.id in evidence_by_pub:
                    has_evidence = True
                    break
            if not has_evidence:
                unverified_cites.append(cite)

        if unverified_cites:
            story.append(PageBreak())
            story.append(Paragraph("Unverified / Unresolved References", self.styles['SectionHeader']))
            story.append(Paragraph(
                "The following cited references could not be matched to retrieved publications or evidence:",
                self.styles['BodyText2']
            ))
            for cite in unverified_cites[:10]:
                story.append(Paragraph(f"[{cite.reference_number or '?'}] {cite.citation_text[:200]}...", self.styles['SmallMuted']))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    def _count_verdicts(self, verifications: List[VerificationResult]) -> dict:
        counts = {}
        for v in verifications:
            counts[v.verdict] = counts.get(v.verdict, 0) + 1
        return counts