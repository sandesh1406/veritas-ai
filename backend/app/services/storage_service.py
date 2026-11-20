"""Supabase Storage service for VERITAS AI.

Handles document upload, download, and management in Supabase Storage.
"""

import logging
import uuid
from typing import Optional, BinaryIO
from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for managing file storage in Supabase."""

    DOCUMENTS_BUCKET = "research-documents"
    REPORTS_BUCKET = "verification-reports"

    def __init__(self, admin_client: Client):
        self.admin = admin_client

    def _get_user_path(self, user_id: str, filename: str) -> str:
        """Generate storage path with user_id as first folder."""
        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
        unique_id = str(uuid.uuid4())[:8]
        return f"{user_id}/{unique_id}_{safe_filename}"

    async def upload_document(
        self,
        user_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str
    ) -> str:
        """Upload a research document to storage.

        Args:
            user_id: The user's UUID
            file_bytes: File content
            filename: Original filename
            content_type: MIME type

        Returns:
            Storage path of uploaded file

        Raises:
            Exception: If upload fails
        """
        path = self._get_user_path(user_id, filename)

        try:
            result = self.admin.storage.from_(self.DOCUMENTS_BUCKET).upload(
                path=path,
                file=file_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": "false"
                }
            )

            if isinstance(result, Exception):
                raise result

            logger.info(f"Uploaded document to {path}")
            return path

        except Exception as e:
            logger.error(f"Document upload failed: {e}")
            raise

    async def download_document(self, storage_path: str) -> bytes:
        """Download a document from storage.

        Args:
            storage_path: Path returned by upload_document

        Returns:
            File content as bytes

        Raises:
            Exception: If download fails
        """
        try:
            result = self.admin.storage.from_(self.DOCUMENTS_BUCKET).download(storage_path)

            if isinstance(result, Exception):
                raise result

            return result

        except Exception as e:
            logger.error(f"Document download failed for {storage_path}: {e}")
            raise

    async def delete_document(self, storage_path: str) -> bool:
        """Delete a document from storage.

        Args:
            storage_path: Path to delete

        Returns:
            True if deleted successfully
        """
        try:
            result = self.admin.storage.from_(self.DOCUMENTS_BUCKET).remove([storage_path])

            if isinstance(result, Exception):
                raise result

            logger.info(f"Deleted document {storage_path}")
            return True

        except Exception as e:
            logger.error(f"Document deletion failed for {storage_path}: {e}")
            return False

    async def upload_report(
        self,
        user_id: str,
        file_bytes: bytes,
        filename: str
    ) -> str:
        """Upload a verification report to storage.

        Args:
            user_id: The user's UUID
            file_bytes: Report PDF content
            filename: Report filename

        Returns:
            Storage path of uploaded report
        """
        path = f"{user_id}/{filename}"

        try:
            result = self.admin.storage.from_(self.REPORTS_BUCKET).upload(
                path=path,
                file=file_bytes,
                file_options={
                    "content-type": "application/pdf",
                    "upsert": "true"
                }
            )

            if isinstance(result, Exception):
                raise result

            logger.info(f"Uploaded report to {path}")
            return path

        except Exception as e:
            logger.error(f"Report upload failed: {e}")
            raise

    async def download_report(self, storage_path: str) -> bytes:
        """Download a report from storage."""
        try:
            result = self.admin.storage.from_(self.REPORTS_BUCKET).download(storage_path)

            if isinstance(result, Exception):
                raise result

            return result

        except Exception as e:
            logger.error(f"Report download failed for {storage_path}: {e}")
            raise

    async def get_document_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Get a signed URL for document access.

        Args:
            storage_path: Path to document
            expires_in: URL expiration in seconds (default 1 hour)

        Returns:
            Signed URL
        """
        try:
            result = self.admin.storage.from_(self.DOCUMENTS_BUCKET).create_signed_url(
                storage_path, expires_in
            )

            if isinstance(result, Exception):
                raise result

            return result.get("signedURL", "")

        except Exception as e:
            logger.error(f"Failed to create signed URL: {e}")
            raise

    async def get_report_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Get a signed URL for report access."""
        try:
            result = self.admin.storage.from_(self.REPORTS_BUCKET).create_signed_url(
                storage_path, expires_in
            )

            if isinstance(result, Exception):
                raise result

            return result.get("signedURL", "")

        except Exception as e:
            logger.error(f"Failed to create signed URL for report: {e}")
            raise

    async def list_user_documents(self, user_id: str) -> list:
        """List all documents for a user.

        Args:
            user_id: The user's UUID

        Returns:
            List of file metadata
        """
        try:
            result = self.admin.storage.from_(self.DOCUMENTS_BUCKET).list(
                path=user_id,
                options={"limit": 1000}
            )

            if isinstance(result, Exception):
                raise result

            return result

        except Exception as e:
            logger.error(f"Failed to list documents for user {user_id}: {e}")
            return []

    async def list_user_reports(self, user_id: str) -> list:
        """List all reports for a user."""
        try:
            result = self.admin.storage.from_(self.REPORTS_BUCKET).list(
                path=user_id,
                options={"limit": 1000}
            )

            if isinstance(result, Exception):
                raise result

            return result

        except Exception as e:
            logger.error(f"Failed to list reports for user {user_id}: {e}")
            return []


async def get_storage_service() -> StorageService:
    """Get storage service with admin client."""
    from app.core.supabase_client import get_supabase_admin
    admin = get_supabase_admin()
    return StorageService(admin)