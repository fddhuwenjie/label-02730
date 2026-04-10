"""CSV file version management API endpoints."""
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import UPLOAD_DIR
from app.core.logging import logger


class VersionInfo(BaseModel):
    """Model for file version info."""
    version: int
    upload_time: str
    file_size: int
    row_count: int


class DiffResult(BaseModel):
    """Model for diff result."""
    v1: int
    v2: int
    rows_added: int
    rows_deleted: int
    rows_modified: int


class FileVersionManager:
    """File version manager using dependency injection."""

    def __init__(self, upload_dir: str = UPLOAD_DIR):
        self.upload_dir = Path(upload_dir)

    def get_file_dir(self, filename: str) -> Path:
        """Get directory for a file."""
        base_name = Path(filename).stem if "." in filename else filename
        return self.upload_dir / base_name

    def get_all_versions(self, filename: str) -> list[dict]:
        """Get all versions for a file."""
        file_dir = self.get_file_dir(filename)
        if not file_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No versions found for file: {filename}"
            )

        versions = []
        for version_file in file_dir.glob("v*.csv"):
            try:
                version_num = int(version_file.stem[1:])
                stat = version_file.stat()
                upload_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
                file_size = stat.st_size

                with open(version_file, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    row_count = len(list(reader))

                versions.append({
                    "version": version_num,
                    "upload_time": upload_time,
                    "file_size": file_size,
                    "row_count": row_count
                })
            except ValueError:
                continue

        versions.sort(key=lambda x: x["version"])
        return versions

    def get_latest_version(self, filename: str) -> int:
        """Get the latest version number for a file."""
        versions = self.get_all_versions(filename)
        if not versions:
            return 0
        return max(v["version"] for v in versions)

    def get_version_content(self, filename: str, version: int) -> set[str]:
        """Get CSV content for a specific version as set of rows."""
        file_dir = self.get_file_dir(filename)
        version_file = file_dir / f"v{version}.csv"
        
        if not version_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found for file: {filename}"
            )

        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        reader = csv.reader(io.StringIO(content))
        return {str(row) for row in reader}
    
    def get_version_rows(self, filename: str, version: int) -> list[str]:
        """Get CSV content for a specific version as list of rows."""
        file_dir = self.get_file_dir(filename)
        version_file = file_dir / f"v{version}.csv"
        
        if not version_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found for file: {filename}"
            )

        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        reader = csv.reader(io.StringIO(content))
        return [str(row) for row in reader]

    def delete_version(self, filename: str, version: int) -> None:
        """Delete a specific file version."""
        latest_version = self.get_latest_version(filename)
        
        if version == latest_version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete latest version (v{version})"
            )

        file_dir = self.get_file_dir(filename)
        version_file = file_dir / f"v{version}.csv"
        
        if not version_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found for file: {filename}"
            )

        try:
            version_file.unlink()
            logger.info(f"Deleted version: {filename} v{version}")
        except IOError as e:
            logger.error(f"Failed to delete file version: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file version."
            )


def get_version_manager():
    """Dependency for file version manager."""
    return FileVersionManager()


router = APIRouter(prefix="/api/files", tags=["file-versions"])


@router.get("/{filename}/versions", response_model=list[VersionInfo])
async def get_file_versions(
    filename: str,
    manager: FileVersionManager = Depends(get_version_manager)
):
    """Get all versions for a file."""
    return manager.get_all_versions(filename)


@router.get("/{filename}/diff", response_model=DiffResult)
async def compare_versions(
    filename: str,
    v1: Annotated[int, Query(..., ge=1, description="First version number")],
    v2: Annotated[int, Query(..., ge=1, description="Second version number")],
    manager: FileVersionManager = Depends(get_version_manager)
):
    """Compare two file versions and return diff statistics."""
    rows_v1 = manager.get_version_rows(filename, v1)
    rows_v2 = manager.get_version_rows(filename, v2)
    
    set_v1 = set(rows_v1)
    set_v2 = set(rows_v2)
    
    rows_added = len(set_v2 - set_v1)
    rows_deleted = len(set_v1 - set_v2)
    
    rows_modified = 0
    common = set_v1 & set_v2
    v1_ordered = [r for r in rows_v1 if r in common]
    v2_ordered = [r for r in rows_v2 if r in common]
    if v1_ordered != v2_ordered:
        rows_modified = min(len(set_v1), len(set_v2)) - len(common)
    
    return {
        "v1": v1,
        "v2": v2,
        "rows_added": rows_added,
        "rows_deleted": rows_deleted,
        "rows_modified": max(0, rows_modified)
    }


@router.delete("/{filename}/versions/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_version(
    filename: str,
    version: int,
    manager: FileVersionManager = Depends(get_version_manager)
):
    """Delete a specific file version (cannot delete the latest version)."""
    manager.delete_version(filename, version)
