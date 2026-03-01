"""Pytest configuration and fixtures."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the project-root client/ package importable when tests run from sync-server/
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture(autouse=True)
def temp_upload_dir(monkeypatch):
    """Use temporary directory for uploads during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("UPLOAD_DIR", tmpdir)
        yield tmpdir
