"""Unit tests for upload client."""
import pytest
from unittest.mock import call, patch, MagicMock
import httpx

from client.client import upload_file


class TestUploadFile:
    """Tests for upload_file function."""

    def test_file_not_found(self, capsys):
        """Test handling of non-existent file."""
        result = upload_file("/nonexistent/file.csv", "http://localhost:8000")
        
        assert result is False
        captured = capsys.readouterr()
        assert "File not found" in captured.out

    def test_invalid_extension(self, tmp_path, capsys):
        """Test rejection of non-CSV files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        
        result = upload_file(str(txt_file), "http://localhost:8000")
        
        assert result is False
        captured = capsys.readouterr()
        assert "Only .csv files" in captured.out

    @patch("client.client.httpx.Client")
    def test_successful_upload(self, mock_client_class, tmp_path, capsys):
        """Test successful file upload."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "File uploaded successfully",
            "filename": "test.csv",
            "file_size": 100
        }
        
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client
        
        result = upload_file(str(csv_file), "http://localhost:8000")
        
        assert result is True
        captured = capsys.readouterr()
        assert "Success" in captured.out

    @patch("client.client.time.sleep")
    @patch("client.client.httpx.Client")
    def test_connection_error(self, mock_client_class, mock_sleep, tmp_path, capsys):
        """Test handling of connection errors — single attempt, no retry."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = upload_file(str(csv_file), "http://localhost:8000", retries=1)

        assert result is False
        captured = capsys.readouterr()
        assert "Connection error" in captured.out
        mock_sleep.assert_not_called()

    @patch("client.client.time.sleep")
    @patch("client.client.httpx.Client")
    def test_timeout_error(self, mock_client_class, mock_sleep, tmp_path, capsys):
        """Test handling of timeout errors — single attempt, no retry."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = upload_file(str(csv_file), "http://localhost:8000", retries=1)

        assert result is False
        captured = capsys.readouterr()
        assert "Timeout" in captured.out
        mock_sleep.assert_not_called()

    @patch("client.client.time.sleep")
    @patch("client.client.httpx.Client")
    def test_server_error(self, mock_client_class, mock_sleep, tmp_path, capsys):
        """Test handling of server errors — single attempt, no retry."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = upload_file(str(csv_file), "http://localhost:8000", retries=1)

        assert result is False
        captured = capsys.readouterr()
        assert "Server error" in captured.out
        mock_sleep.assert_not_called()

    @patch("client.client.time.sleep")
    @patch("client.client.httpx.Client")
    def test_retry_on_connection_error(self, mock_client_class, mock_sleep, tmp_path, capsys):
        """Test that upload is retried on connection errors with backoff delay."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = upload_file(str(csv_file), "http://localhost:8000", retries=3)

        assert result is False
        assert mock_client.post.call_count == 3
        # Backoff sleeps: 1s before attempt 2, 2s before attempt 3
        assert mock_sleep.call_args_list == [call(1), call(2)]

    @patch("client.client.time.sleep")
    @patch("client.client.httpx.Client")
    def test_retry_succeeds_on_second_attempt(self, mock_client_class, mock_sleep, tmp_path, capsys):
        """Test that a successful second attempt returns True."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice")

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {
            "success": True,
            "message": "File uploaded successfully",
            "filename": "test.csv",
            "file_size": 100,
        }

        mock_client = MagicMock()
        mock_client.post.side_effect = [
            httpx.ConnectError("Connection refused"),
            ok_response,
        ]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = upload_file(str(csv_file), "http://localhost:8000", retries=3)

        assert result is True
        assert mock_client.post.call_count == 2
        mock_sleep.assert_called_once_with(1)
        captured = capsys.readouterr()
        assert "Success" in captured.out
