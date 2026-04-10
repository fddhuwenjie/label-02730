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
        assert data["message"] == "File uploaded successfully"
        assert data["file_size"] == len(csv_content)
        assert data["filename"] == "test"
        assert data["version"] >= 1
        assert "v" in data["file_path"]

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


class TestVersionManagement:
    """Tests for version management endpoints."""

    def test_get_versions(self, client):
        """Test getting versions of a file."""
        # First upload a file
        csv_content = b"id,name\n1,Alice\n2,Bob"
        files = {"file": ("version_test.csv", io.BytesIO(csv_content), "text/csv")}
        response = client.post("/api/v1/upload", files=files)
        assert response.status_code == 200

        # Get versions
        response = client.get("/api/v1/files/version_test/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "version_test"
        assert len(data["versions"]) >= 1
        assert "version" in data["versions"][0]
        assert "upload_time" in data["versions"][0]
        assert "file_size" in data["versions"][0]
        assert "row_count" in data["versions"][0]

    def test_get_versions_not_found(self, client):
        """Test getting versions of a non-existent file."""
        response = client.get("/api/v1/files/nonexistent_file_xyz/versions")
        assert response.status_code == 404

    def test_upload_same_file_creates_new_version(self, client):
        """Test that uploading the same file creates a new version."""
        csv_content = b"id,name\n1,Alice"
        files = {"file": ("multi_version.csv", io.BytesIO(csv_content), "text/csv")}

        # Upload first version
        response1 = client.post("/api/v1/upload", files=files)
        assert response1.status_code == 200
        version1 = response1.json()["version"]

        # Upload second version
        response2 = client.post("/api/v1/upload", files=files)
        assert response2.status_code == 200
        version2 = response2.json()["version"]

        assert version2 > version1

    def test_compare_versions(self, client):
        """Test comparing two versions."""
        # Upload first version
        csv_content1 = b"id,name\n1,Alice\n2,Bob"
        files1 = {"file": ("diff_test.csv", io.BytesIO(csv_content1), "text/csv")}
        response1 = client.post("/api/v1/upload", files=files1)
        assert response1.status_code == 200
        version1 = response1.json()["version"]

        # Upload second version with different content
        csv_content2 = b"id,name\n1,Alice\n2,Bob\n3,Charlie"
        files2 = {"file": ("diff_test.csv", io.BytesIO(csv_content2), "text/csv")}
        response2 = client.post("/api/v1/upload", files=files2)
        assert response2.status_code == 200
        version2 = response2.json()["version"]

        # Compare versions
        response = client.get(f"/api/v1/files/diff_test/diff?v1={version1}&v2={version2}")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "diff_test"
        assert data["version1"] == version1
        assert data["version2"] == version2
        assert "added_rows" in data
        assert "deleted_rows" in data
        assert "modified_rows" in data

    def test_compare_versions_not_found(self, client):
        """Test comparing non-existent versions."""
        response = client.get("/api/v1/files/nonexistent/diff?v1=1&v2=999")
        assert response.status_code == 404

    def test_delete_version(self, client):
        """Test deleting a version."""
        # Upload two versions
        csv_content = b"id,name\n1,Alice"
        files = {"file": ("delete_test.csv", io.BytesIO(csv_content), "text/csv")}

        response1 = client.post("/api/v1/upload", files=files)
        assert response1.status_code == 200
        version1 = response1.json()["version"]

        response2 = client.post("/api/v1/upload", files=files)
        assert response2.status_code == 200
        version2 = response2.json()["version"]

        # Delete the older version
        response = client.delete(f"/api/v1/files/delete_test/versions/{version1}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's deleted
        versions_response = client.get("/api/v1/files/delete_test/versions")
        versions = versions_response.json()["versions"]
        assert version1 not in [v["version"] for v in versions]

    def test_delete_latest_version_fails(self, client):
        """Test that deleting the latest version returns 400."""
        # Upload a file
        csv_content = b"id,name\n1,Alice"
        files = {"file": ("latest_delete_test.csv", io.BytesIO(csv_content), "text/csv")}

        response = client.post("/api/v1/upload", files=files)
        assert response.status_code == 200
        version = response.json()["version"]

        # Try to delete the latest version
        response = client.delete(f"/api/v1/files/latest_delete_test/versions/{version}")
        assert response.status_code == 400
        assert "latest version" in response.json()["detail"].lower()

    def test_delete_version_not_found(self, client):
        """Test deleting a non-existent version."""
        response = client.delete("/api/v1/files/nonexistent/versions/999")
        assert response.status_code == 404


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
