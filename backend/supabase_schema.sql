-- VERITAS AI Complete Database Schema
-- Run this in Supabase SQL Editor BEFORE supabase_functions.sql

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Documents table - stores uploaded research documents
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN (
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword'
    )),
    file_size BIGINT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'queued' CHECK (processing_status IN (
        'queued', 'processing', 'completed', 'failed'
    )),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Claims table - extracted claims from documents
CREATE TABLE IF NOT EXISTS public.claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    claim_type TEXT,
    page_number INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Citations table - extracted citations from bibliography
CREATE TABLE IF NOT EXISTS public.citations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    claim_id UUID REFERENCES public.claims(id) ON DELETE SET NULL,
    citation_text TEXT NOT NULL,
    reference_number TEXT,
    doi TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Publications table - retrieved publication metadata
CREATE TABLE IF NOT EXISTS public.publications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    citation_id UUID NOT NULL REFERENCES public.citations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    authors TEXT,
    doi TEXT,
    publication_year INTEGER,
    source_url TEXT,
    abstract TEXT,
    full_text_url TEXT,
    retrieval_status TEXT NOT NULL DEFAULT 'pending' CHECK (retrieval_status IN (
        'pending', 'completed', 'partial', 'failed'
    )),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Evidence table - extracted evidence passages
CREATE TABLE IF NOT EXISTS public.evidence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
    publication_id UUID NOT NULL REFERENCES public.publications(id) ON DELETE CASCADE,
    evidence_text TEXT NOT NULL,
    source_location TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Verifications table - AI verification results
CREATE TABLE IF NOT EXISTS public.verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN (
        'SUPPORTED',
        'PARTIALLY_SUPPORTED',
        'UNSUPPORTED',
        'CONTRADICTORY',
        'POTENTIALLY_OUTDATED',
        'NEEDS_REVIEW'
    )),
    confidence_score REAL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    explanation TEXT,
    evidence_status TEXT,
    model_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Reports table - generated PDF reports
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    report_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Profiles table - extended user profile
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Documents indexes
CREATE INDEX IF NOT EXISTS documents_user_id_idx ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS documents_status_idx ON public.documents(processing_status);
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON public.documents(created_at DESC);

-- Claims indexes
CREATE INDEX IF NOT EXISTS claims_document_id_idx ON public.claims(document_id);

-- Citations indexes
CREATE INDEX IF NOT EXISTS citations_document_id_idx ON public.citations(document_id);
CREATE INDEX IF NOT EXISTS citations_claim_id_idx ON public.citations(claim_id);

-- Publications indexes
CREATE INDEX IF NOT EXISTS publications_citation_id_idx ON public.publications(citation_id);
CREATE INDEX IF NOT EXISTS publications_retrieval_status_idx ON public.publications(retrieval_status);
CREATE INDEX IF NOT EXISTS publications_doi_idx ON public.publications(doi);

-- Evidence indexes
CREATE INDEX IF NOT EXISTS evidence_claim_id_idx ON public.evidence(claim_id);
CREATE INDEX IF NOT EXISTS evidence_publication_id_idx ON public.evidence(publication_id);

-- Verifications indexes
CREATE INDEX IF NOT EXISTS verifications_claim_id_idx ON public.verifications(claim_id);
CREATE INDEX IF NOT EXISTS verifications_verdict_idx ON public.verifications(verdict);

-- Reports indexes
CREATE INDEX IF NOT EXISTS reports_user_id_idx ON public.reports(user_id);
CREATE INDEX IF NOT EXISTS reports_document_id_idx ON public.reports(document_id);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- RLS POLICIES
-- ============================================================

-- Documents: Users can only access their own documents
CREATE POLICY "Users can view own documents" ON public.documents
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents" ON public.documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents" ON public.documents
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents" ON public.documents
    FOR DELETE USING (auth.uid() = user_id);

-- Claims: Users can only access claims from their documents
CREATE POLICY "Users can view claims from own documents" ON public.claims
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.documents d
            WHERE d.id = claims.document_id AND d.user_id = auth.uid()
        )
    );

-- Citations: Users can only access citations from their documents
CREATE POLICY "Users can view citations from own documents" ON public.citations
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.documents d
            WHERE d.id = citations.document_id AND d.user_id = auth.uid()
        )
    );

-- Publications: Users can only access publications linked to their citations
CREATE POLICY "Users can view publications from own citations" ON public.publications
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.citations c
            JOIN public.documents d ON d.id = c.document_id
            WHERE c.id = publications.citation_id AND d.user_id = auth.uid()
        )
    );

-- Evidence: Users can only access evidence from their claims
CREATE POLICY "Users can view evidence from own claims" ON public.evidence
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.claims cl
            JOIN public.documents d ON d.id = cl.document_id
            WHERE cl.id = evidence.claim_id AND d.user_id = auth.uid()
        )
    );

-- Verifications: Users can only access verifications from their claims
CREATE POLICY "Users can view verifications from own claims" ON public.verifications
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.claims cl
            JOIN public.documents d ON d.id = cl.document_id
            WHERE cl.id = verifications.claim_id AND d.user_id = auth.uid()
        )
    );

-- Reports: Users can only access their own reports
CREATE POLICY "Users can view own reports" ON public.reports
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own reports" ON public.reports
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Profiles: Users can only access their own profile
CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile" ON public.profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- ============================================================
-- TRIGGERS FOR UPDATED_AT
-- ============================================================

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================================
-- STORAGE BUCKETS (Run separately in Supabase Storage)
-- ============================================================

-- These are created via Supabase Dashboard or API:
-- 1. research-documents (private bucket for user uploads)
-- 2. verification-reports (private bucket for generated PDFs)
--
-- Storage policies:
-- research-documents:
--   - Users can upload to their own folder: user_id/*
--   - Users can read from their own folder
-- verification-reports:
--   - Users can upload to their own folder
--   - Users can read from their own folder