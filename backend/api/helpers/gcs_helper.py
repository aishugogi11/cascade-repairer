"""
Google Cloud Storage helper for audio recordings and artifacts
"""
from google.cloud import storage
import logging
import os
import yaml
from typing import Tuple, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Load config
config_path = Path(__file__).parent.parent.parent / "config.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

PROJECT_ID = os.getenv("GCP_PROJECT_ID", config["build_env_vars"]["PROJECT_ID"])
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", config["metadata"]["gcs_bucket_name"])


class GCSHelper:
    """Helper class for Google Cloud Storage operations"""

    def __init__(self):
        self._client = None
        self.project_id = PROJECT_ID
        self.bucket_name = BUCKET_NAME

    @property
    def client(self) -> storage.Client:
        """Lazy client so importing this module (and unit tests) never needs
        GCP credentials."""
        if self._client is None:
            self._client = storage.Client(project=self.project_id)
        return self._client

    def upload_file(
        self,
        local_file_path: str,
        destination_blob_name: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Upload a file to GCS

        Args:
            local_file_path: Path to the local file
            destination_blob_name: Destination path in GCS (e.g., "audio/session_id/turn.wav")

        Returns:
            Tuple of (success: bool, gcs_uri: Optional[str], error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(destination_blob_name)

            blob.upload_from_filename(local_file_path)

            gcs_uri = f"gs://{self.bucket_name}/{destination_blob_name}"
            logger.info(f"Uploaded {local_file_path} to {gcs_uri}")

            return True, gcs_uri, None

        except Exception as e:
            logger.error(f"Error uploading file to GCS: {e}")
            return False, None, str(e)

    def upload_file_from_bytes(
        self,
        file_content: bytes,
        destination_blob_name: str,
        content_type: str = "application/octet-stream"
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Upload file content directly from bytes to GCS

        Args:
            file_content: File content as bytes
            destination_blob_name: Destination path in GCS
            content_type: MIME type of the file

        Returns:
            Tuple of (success: bool, gcs_uri: Optional[str], error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(destination_blob_name)

            # content_type must go to upload_from_string itself: presetting
            # blob.content_type while the upload defaults to text/plain makes
            # GCS reject the request as a metadata/header mismatch (400).
            blob.upload_from_string(file_content, content_type=content_type)

            gcs_uri = f"gs://{self.bucket_name}/{destination_blob_name}"
            logger.info(f"Uploaded bytes to {gcs_uri}")

            return True, gcs_uri, None

        except Exception as e:
            logger.error(f"Error uploading bytes to GCS: {e}")
            return False, None, str(e)

    def download_file(
        self,
        blob_name: str,
        local_file_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Download a file from GCS

        Args:
            blob_name: Path of the blob in GCS
            local_file_path: Local path to save the file

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            blob.download_to_filename(local_file_path)
            logger.info(f"Downloaded {blob_name} to {local_file_path}")

            return True, None

        except Exception as e:
            logger.error(f"Error downloading file from GCS: {e}")
            return False, str(e)

    def download_as_bytes(
        self,
        blob_name: str
    ) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Download a file from GCS as bytes

        Args:
            blob_name: Path of the blob in GCS

        Returns:
            Tuple of (success: bool, content: Optional[bytes], error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            content = blob.download_as_bytes()
            logger.info(f"Downloaded {blob_name} as bytes")

            return True, content, None

        except Exception as e:
            logger.error(f"Error downloading file from GCS: {e}")
            return False, None, str(e)

    def delete_file(
        self,
        blob_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a file from GCS

        Args:
            blob_name: Path of the blob in GCS

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            blob.delete()
            logger.info(f"Deleted {blob_name}")

            return True, None

        except Exception as e:
            logger.error(f"Error deleting file from GCS: {e}")
            return False, str(e)

    def list_files(
        self,
        prefix: str = ""
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        List files in GCS with optional prefix

        Args:
            prefix: Optional prefix to filter files

        Returns:
            Tuple of (success: bool, file_list: List[str], error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)

            file_list = [blob.name for blob in blobs]
            logger.info(f"Listed {len(file_list)} files with prefix '{prefix}'")

            return True, file_list, None

        except Exception as e:
            logger.error(f"Error listing files from GCS: {e}")
            return False, [], str(e)

    def file_exists(
        self,
        blob_name: str
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Check if a file exists in GCS

        Args:
            blob_name: Path of the blob in GCS

        Returns:
            Tuple of (success: bool, exists: bool, error_message: Optional[str])
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            exists = blob.exists()
            return True, exists, None

        except Exception as e:
            logger.error(f"Error checking file existence in GCS: {e}")
            return False, False, str(e)


# Create singleton instance
gcs_helper = GCSHelper()
