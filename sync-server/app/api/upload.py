"""CSV file upload API endpoints."""
import csv
import io
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.core.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_DIR
from app.core.logging import logger

router = APIRouter(prefix="/api/v1", tags=["upload"])


class UploadResponse(BaseModel):
    """Response model for file upload."""
    success: bool
    message: str
    filename: str
    version: int
    file_path: str
    file_size: int


class VersionInfo(BaseModel):
    """Version information model."""
    version: int
    upload_time: str
    file_size: int
    row_count: int


class DiffResponse(BaseModel):
    """Diff response model."""
    filename: str
    v1: int
    v2: int
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


def get_next_version(file_dir: Path) -> int:
    """Get the next version number for a file.
    
    Args:
        file_dir: Directory containing versioned files.
        
    Returns:
        Next version number (starts at 1).
    """
    if not file_dir.exists():
        return 1
    versions = []
    for f in file_dir.glob("v*.csv"):
        try:
            version = int(f.stem[1:])
            versions.append(version)
        except ValueError:
            continue
    return max(versions, default=0) + 1


def count_csv_rows(file_path: Path) -> int:
    """Count the number of rows in a CSV file."""
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        return sum(1 for _ in reader)


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(..., description="CSV file to upload")):
    """
    Upload a CSV file to the server with versioning support.
    
    - Validates file type (.csv only)
    - Checks file size (max 10MB)
    - Stores file with versioning: uploads/{base_filename}/v{version}.csv
    """
    validate_file(file)

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

    base_filename = Path(file.filename).stem
    file_dir = Path(UPLOAD_DIR) / base_filename
    file_dir.mkdir(parents=True, exist_ok=True)

    version = get_next_version(file_dir)
    versioned_filename = f"v{version}.csv"
    file_path = file_dir / versioned_filename

    try:
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"File saved: {file_path}")
    except IOError as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file."
        )

    relative_path = f"{base_filename}/{versioned_filename}"

    return UploadResponse(
        success=True,
        message=f"File uploaded successfully as version {version}",
        filename=base_filename,
        version=version,
        file_path=relative_path,
        file_size=file_size
    )


def get_file_versions_dir(filename: str) -> Path:
    """Dependency to get the versions directory for a file."""
    base_filename = Path(filename).stem
    file_dir = Path(UPLOAD_DIR) / base_filename
    return file_dir


@router.get("/files/{filename}/versions", response_model=list[VersionInfo])
def get_file_versions(
    filename: str,
    file_dir: Path = Depends(get_file_versions_dir)
):
    """Get all versions for a specific file."""
    if not file_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No versions found for file: {filename}"
        )
    
    versions = []
    for f in sorted(file_dir.glob("v*.csv")):
        try:
            version = int(f.stem[1:])
            stat = os.stat(f)
            upload_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
            file_size = stat.st_size
            row_count = count_csv_rows(f)
            
            versions.append(VersionInfo(
                version=version,
                upload_time=upload_time,
                file_size=file_size,
                row_count=row_count
            ))
        except ValueError:
            continue
    
    return versions


def read_csv_lines(file_path: Path) -> list[str]:
    """Read CSV file and return lines as strings."""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


@router.get("/files/{filename}/diff", response_model=DiffResponse)
def diff_file_versions(
    filename: str,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
    file_dir: Path = Depends(get_file_versions_dir)
):
    """Diff two versions of a file and return row statistics."""
    if not file_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No versions found for file: {filename}"
        )
    
    v1_path = file_dir / f"v{v1}.csv"
    v2_path = file_dir / f"v{v2}.csv"
    
    if not v1_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {v1} not found for file: {filename}"
        )
    if not v2_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {v2} not found for file: {filename}"
        )
    
    lines_v1 = read_csv_lines(v1_path)
    lines_v2 = read_csv_lines(v2_path)
    
    min_len = min(len(lines_v1), len(lines_v2))
    max_len = max(len(lines_v1), len(lines_v2))
    
    modified = 0
    for i in range(min_len):
        if lines_v1[i] != lines_v2[i]:
            modified += 1
    
    len_diff = max_len - min_len
    if len(lines_v2) > len(lines_v1):
        added = len_diff
        deleted = 0
    else:
        added = 0
        deleted = len_diff
    
    return DiffResponse(
        filename=filename,
        v1=v1,
        v2=v2,
        added_rows=added,
        deleted_rows=deleted,
        modified_rows=modified
    )


@router.delete("/files/{filename}/versions/{version}")
def delete_version(
    filename: str,
    version: int,
    file_dir: Path = Depends(get_file_versions_dir)
):
    """Delete a specific version (cannot delete the latest version)."""
    if not file_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No versions found for file: {filename}"
        )
    
    current_max = get_next_version(file_dir) - 1
    if version == current_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete the latest version (version {version})"
        )
    
    version_path = file_dir / f"v{version}.csv"
    if not version_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} not found for file: {filename}"
        )
    
    try:
        os.remove(version_path)
    except IOError as e:
        logger.error(f"Failed to delete version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete version."
        )
    
    return {
        "success": True,
        "message": f"Version {version} deleted successfully"
    }


