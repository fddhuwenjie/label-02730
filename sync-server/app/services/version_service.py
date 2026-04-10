"""File version management service."""
import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, HTTPException, status

from app.core.config import UPLOAD_DIR
from app.core.logging import logger


@dataclass
class VersionInfo:
    """Information about a file version."""
    version: int
    upload_time: datetime
    file_size: int
    row_count: int


@dataclass
class DiffResult:
    """Result of comparing two file versions."""
    added_rows: int
    deleted_rows: int
    modified_rows: int


class VersionService:
    """Service for managing file versions."""

    def __init__(self, upload_dir: str = UPLOAD_DIR):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_dir(self, filename: str) -> Path:
        """Get the directory for a specific file's versions."""
        safe_name = Path(filename).stem
        return self.upload_dir / safe_name

    def _get_version_path(self, filename: str, version: int) -> Path:
        """Get the path for a specific version of a file."""
        file_dir = self._get_file_dir(filename)
        return file_dir / f"v{version}.csv"

    def get_next_version(self, filename: str) -> int:
        """Get the next version number for a file."""
        file_dir = self._get_file_dir(filename)
        if not file_dir.exists():
            return 1

        versions = []
        for f in file_dir.glob("v*.csv"):
            try:
                version = int(f.stem[1:])  # Remove 'v' prefix
                versions.append(version)
            except ValueError:
                continue

        return max(versions, default=0) + 1

    def save_version(self, filename: str, content: bytes) -> tuple[int, Path]:
        """Save a new version of a file.

        Returns:
            Tuple of (version_number, file_path)
        """
        version = self.get_next_version(filename)
        file_dir = self._get_file_dir(filename)
        file_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_version_path(filename, version)
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved version {version} of {filename} to {file_path}")
        return version, file_path

    def get_versions(self, filename: str) -> List[VersionInfo]:
        """Get all versions of a file."""
        file_dir = self._get_file_dir(filename)
        if not file_dir.exists():
            return []

        versions = []
        for f in file_dir.glob("v*.csv"):
            try:
                version = int(f.stem[1:])
                stat = f.stat()
                upload_time = datetime.fromtimestamp(stat.st_mtime)
                file_size = stat.st_size
                row_count = self._count_rows(f)

                versions.append(VersionInfo(
                    version=version,
                    upload_time=upload_time,
                    file_size=file_size,
                    row_count=row_count
                ))
            except (ValueError, IOError):
                continue

        return sorted(versions, key=lambda v: v.version)

    def _count_rows(self, file_path: Path) -> int:
        """Count the number of rows in a CSV file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                return sum(1 for _ in reader)
        except Exception:
            return 0

    def get_version_path(self, filename: str, version: int) -> Optional[Path]:
        """Get the path for a specific version if it exists."""
        file_path = self._get_version_path(filename, version)
        if file_path.exists():
            return file_path
        return None

    def get_latest_version(self, filename: str) -> int:
        """Get the latest version number for a file."""
        versions = self.get_versions(filename)
        if not versions:
            return 0
        return max(v.version for v in versions)

    def delete_version(self, filename: str, version: int) -> bool:
        """Delete a specific version of a file.

        Returns:
            True if deleted, False if not found.

        Raises:
            HTTPException: If trying to delete the latest version.
        """
        latest = self.get_latest_version(filename)
        if version == latest:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the latest version of a file."
            )

        file_path = self._get_version_path(filename, version)
        if not file_path.exists():
            return False

        file_path.unlink()
        logger.info(f"Deleted version {version} of {filename}")

        # Clean up empty directory
        file_dir = self._get_file_dir(filename)
        if file_dir.exists() and not any(file_dir.iterdir()):
            file_dir.rmdir()

        return True

    def compare_versions(self, filename: str, v1: int, v2: int) -> DiffResult:
        """Compare two versions of a file and return the differences."""
        path1 = self.get_version_path(filename, v1)
        path2 = self.get_version_path(filename, v2)

        if not path1:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {v1} of {filename} not found."
            )
        if not path2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {v2} of {filename} not found."
            )

        rows1 = self._read_csv_rows(path1)
        rows2 = self._read_csv_rows(path2)

        # Use a simple row-by-row comparison
        # For CSV diff, we consider rows as units
        set1 = set(rows1)
        set2 = set(rows2)

        added = len(set2 - set1)
        deleted = len(set1 - set2)

        # For modified rows, we look at rows with same "key" (first column) but different content
        # If no clear key, we just count rows that exist in both but are different
        common_keys = set()
        modified = 0

        # Create a mapping of first column to full row for both versions
        dict1 = {row[0] if row else "": row for row in rows1}
        dict2 = {row[0] if row else "": row for row in rows2}

        for key in dict1:
            if key in dict2:
                if dict1[key] != dict2[key]:
                    modified += 1

        return DiffResult(
            added_rows=added,
            deleted_rows=deleted,
            modified_rows=modified
        )

    def _read_csv_rows(self, file_path: Path) -> List[tuple]:
        """Read all rows from a CSV file as tuples for comparison."""
        rows = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(tuple(row))
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
        return rows


def get_version_service() -> VersionService:
    """Dependency to get the version service."""
    return VersionService()
