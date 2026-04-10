"""CSV file upload API endpoints."""
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from app.core.logging import logger
from app.services.version_service import VersionService, get_version_service, VersionInfo, DiffResult

router = APIRouter(prefix="/api/v1", tags=["upload"])


class UploadResponse(BaseModel):
    """Response model for file upload."""
    success: bool
    message: str
    filename: str
    version: int
    file_path: str
    file_size: int


class VersionListResponse(BaseModel):
    """Response model for version list."""
    filename: str
    versions: List[VersionInfo]


class DiffResponse(BaseModel):
    """Response model for version diff."""
    filename: str
    version1: int
    version2: int
    added_rows: int
    deleted_rows: int
    modified_rows: int


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file extension."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Invalid file type: {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Only {', '.join(ALLOWED_EXTENSIONS)} allowed."
        )


def validate_csv_content(content: bytes) -> None:
    """Validate file content is valid UTF-8 text and parseable CSV.

    1. Checks the first 512 bytes for null bytes (binary indicator).
    2. Confirms full content is decodable as UTF-8.
    3. Attempts to parse the content with csv.reader to catch malformed CSV.
    """
    probe = content[:512]
    if b"\x00" in probe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is not valid CSV (binary data detected).",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is not valid UTF-8 text. CSV files must be text-based.",
        )
    try:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows or all(len(row) == 0 for row in rows):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file contains no parseable rows.",
            )
    except csv.Error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid CSV format: {e}",
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file to upload"),
    version_service: VersionService = Depends(get_version_service)
):
    """
    Upload a CSV file to the server.

    - Validates file type (.csv only)
    - Checks file size (max 10MB)
    - Stores file with version management (uploads/{filename}/v{version}.csv)
    - Version auto-increments for files with the same name
    """
    validate_file(file)

    # Pre-check file size before reading into memory to avoid loading large files.
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed."
        )

    if file_size > MAX_FILE_SIZE:
        logger.warning(f"File too large: {file_size} bytes")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB."
        )

    content = await file.read()
    validate_csv_content(content)

    # Get the base filename (without extension for the folder name)
    base_filename = Path(file.filename).stem

    # Save the file with version management
    version, file_path = version_service.save_version(base_filename, content)

    # Return a relative storage path
    relative_path = f"{base_filename}/v{version}.csv"

    return UploadResponse(
        success=True,
        message="File uploaded successfully",
        filename=base_filename,
        version=version,
        file_path=relative_path,
        file_size=file_size
    )


@router.get("/files/{filename}/versions", response_model=VersionListResponse)
async def get_file_versions(
    filename: str,
    version_service: VersionService = Depends(get_version_service)
):
    """
    Get all versions of a file.

    Returns a list of versions with:
    - version number
    - upload time
    - file size
    - row count
    """
    versions = version_service.get_versions(filename)

    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' not found or has no versions."
        )

    return VersionListResponse(
        filename=filename,
        versions=versions
    )


@router.get("/files/{filename}/diff", response_model=DiffResponse)
async def compare_file_versions(
    filename: str,
    v1: int,
    v2: int,
    version_service: VersionService = Depends(get_version_service)
):
    """
    Compare two versions of a file.

    Returns:
    - added_rows: Number of rows added in v2 compared to v1
    - deleted_rows: Number of rows deleted in v2 compared to v1
    - modified_rows: Number of rows modified (same first column but different content)
    """
    diff_result = version_service.compare_versions(filename, v1, v2)

    return DiffResponse(
        filename=filename,
        version1=v1,
        version2=v2,
        added_rows=diff_result.added_rows,
        deleted_rows=diff_result.deleted_rows,
        modified_rows=diff_result.modified_rows
    )


@router.delete("/files/{filename}/versions/{version}")
async def delete_file_version(
    filename: str,
    version: int,
    version_service: VersionService = Depends(get_version_service)
):
    """
    Delete a specific version of a file.

    Note: Cannot delete the latest version of a file.
    """
    deleted = version_service.delete_version(filename, version)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} of '{filename}' not found."
        )

    return {
        "success": True,
        "message": f"Version {version} of '{filename}' deleted successfully."
    }
