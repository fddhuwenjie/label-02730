"""Pytest configuration and fixtures."""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def temp_upload_dir(monkeypatch):
    """Use temporary directory for uploads during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("UPLOAD_DIR", tmpdir)
        yield tmpdir
