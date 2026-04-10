"""Unit tests for CSV upload API."""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestUploadEndpoint:
    """Tests for /api/v1/upload endpoint."""

    def test_upload_valid_csv(self, client, tmp_path):
        """Test successful CSV upload."""
        csv_content = b"id,name\n1,Alice\n2,Bob"
        files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
        
        response = client.post("/api/v1/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "File uploaded successfully" in data["message"]
        assert data["file_size"] == len(csv_content)
        assert data["filename"] == "test.csv"
        assert data["version"] >= 1
        assert data["row_count"] == 3

    def test_upload_invalid_extension(self, client):
        """Test rejection of non-CSV files."""
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        
        response = client.post("/api/v1/upload", files=files)
        
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_upload_empty_file(self, client):
        """Test rejection of empty files."""
        files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
        
        response = client.post("/api/v1/upload", files=files)
        
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]

    def test_upload_no_file(self, client):
        """Test request without file."""
        response = client.post("/api/v1/upload")

        assert response.status_code == 422  # Validation error

    def test_upload_binary_content_rejected(self, client):
        """Test that a file with binary content is rejected even if extension is .csv."""
        binary_content = b"\x00\x01\x02\x03\xff\xfe" * 50
        files = {"file": ("data.csv", binary_content, "text/csv")}

        response = client.post("/api/v1/upload", files=files)

        assert response.status_code == 400
        assert "binary" in response.json()["detail"].lower()

    def test_upload_non_utf8_content_rejected(self, client):
        """Test that a CSV file with non-UTF-8 encoding is rejected."""
        # Latin-1 encoded content with bytes invalid in UTF-8
        non_utf8 = "id,name\n1,Ren\xe9e".encode("latin-1")
        files = {"file": ("data.csv", non_utf8, "text/csv")}

        response = client.post("/api/v1/upload", files=files)

        assert response.status_code == 400
        assert "utf-8" in response.json()["detail"].lower()


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
