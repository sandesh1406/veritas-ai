import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { ArrowRight, Check, FileText, UploadCloud, X, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageIntro } from '@/components/PageIntro';
import { api } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

export function VerifyDocument() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { user } = useAuth();

  const selectFile = (nextFile: File | undefined) => {
    if (!nextFile) return;
    if (!['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'].includes(nextFile.type)) {
      setMessage('Please choose a PDF or DOCX document.');
      return;
    }
    if (nextFile.size > 20 * 1024 * 1024) {
      setMessage('Files must be smaller than 20 MB.');
      return;
    }
    setMessage('');
    setFile(nextFile);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      setMessage('Add a research document to continue.');
      return;
    }
    if (!user) {
      setMessage('Your session has expired. Please sign in again.');
      return;
    }

    setIsSubmitting(true);
    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Upload document using API
      const uploadResponse = await api.uploadDocument(file);

      // Start processing
      await api.processDocument(uploadResponse.document_id);

      // Navigate to workspace with document ID to view progress
      navigate(`/workspace/${uploadResponse.document_id}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Upload failed. Please try again.');
    } finally {
      setIsSubmitting(false);
      setIsUploading(false);
    }
  };

  return (
    <div className="inner-page">
      <PageIntro
        eyebrow="VERITAS AI / New analysis"
        title="Verify a Document"
        description="Upload a research paper and we will map its claims to the evidence behind each citation."
      />
      <form className="upload-layout" onSubmit={handleSubmit}>
        <div className="panel upload-panel">
          <div
            className={`dropzone ${isDragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'Enter') inputRef.current?.click();
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.doc,.docx"
              onChange={handleChange}
              hidden
              disabled={isSubmitting}
            />
            {file ? (
              <>
                <div className="upload-file-icon">
                  <FileText size={28} />
                </div>
                <strong>{file.name}</strong>
                <span>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready to analyze</span>
                <button
                  type="button"
                  className="remove-file"
                  onClick={(event) => {
                    event.stopPropagation();
                    setFile(null);
                  }}
                  disabled={isSubmitting}
                >
                  <X size={14} /> Remove
                </button>
              </>
            ) : (
              <>
                <div className="upload-icon">
                  <UploadCloud size={30} />
                </div>
                <strong>Drop your research paper here</strong>
                <span>or click to browse from your computer</span>
                <small>PDF or DOCX · Maximum file size 20 MB</small>
              </>
            )}
          </div>
          {message && <div className="form-message error-message">{message}</div>}
          <div className="upload-footer">
            <div>
              <Check size={15} /> Your document stays private
            </div>
            <button className="primary-button" disabled={isSubmitting || !file}>
              {isSubmitting ? (
                <>
                  <Loader2 size={17} className="animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  Start Verification
                  <ArrowRight size={17} />
                </>
              )}
            </button>
          </div>
        </div>
        <aside className="panel upload-aside">
          <span className="eyebrow">Before you begin</span>
          <h2>Make every citation count.</h2>
          <p>VERITAS AI checks the relationship between claims and their referenced sources so your review starts with a clear evidence map.</p>
          <ul>
            <li><Check size={16} /> Best with papers that include references</li>
            <li><Check size={16} /> Supports scientific and academic formats</li>
            <li><Check size={16} /> You can review every match before reporting</li>
          </ul>
        </aside>
      </form>
    </div>
  );
}