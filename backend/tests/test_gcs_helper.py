"""Tests for the GCS helper's upload paths.

Hermetic: the storage client is a mock injected behind the lazy `client`
property. Regression coverage for the content-type mismatch found live on
Cloud Run during Phase 7 QA: upload_file_from_bytes must hand content_type
to upload_from_string itself — presetting it as blob metadata while the
upload request defaults to text/plain is a GCS 400.
"""
from unittest.mock import MagicMock

from api.helpers.gcs_helper import GCSHelper


def _helper_with_mock_client():
    helper = GCSHelper()
    helper._client = MagicMock()
    blob = helper._client.bucket.return_value.blob.return_value
    return helper, blob


def test_upload_from_bytes_passes_content_type_to_upload(monkeypatch):
    helper, blob = _helper_with_mock_client()
    ok, gcs_uri, error = helper.upload_file_from_bytes(
        b"mp3-bytes", "audio/s1/t1.wav", content_type="audio/mpeg"
    )
    assert ok and error is None
    assert gcs_uri == f"gs://{helper.bucket_name}/audio/s1/t1.wav"
    blob.upload_from_string.assert_called_once_with(
        b"mp3-bytes", content_type="audio/mpeg"
    )


def test_upload_from_bytes_failure_returns_error_tuple():
    helper, blob = _helper_with_mock_client()
    blob.upload_from_string.side_effect = RuntimeError("boom")
    ok, gcs_uri, error = helper.upload_file_from_bytes(b"x", "a/b.wav", "audio/wav")
    assert not ok and gcs_uri is None
    assert "boom" in error
