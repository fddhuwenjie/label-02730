"""CSV file upload API endpoints."""
import csv
import io
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_DIR
from app.core.logging import logger

router = APIRouter(prefix="/api/v1", tags=["upload"])


class UploadResponse(BaseModel):
    """Response model for file upload."""
    success: bool
    message: str
    filename: str
    file_path: str
    file_size: int


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


def generate_filename(original_name: str, save_dir: Path) -> str:
    """Generate a collision-free filename with timestamp and UUID.

    Uses the full UUID hex (32 chars) to make collisions virtually impossible.
    Falls back to retrying if the target path already exists.
    """
    ext = Path(original_name).suffix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for _ in range(5):
        unique_id = uuid.uuid4().hex
        filename = f"{timestamp}_{unique_id}{ext}"
        if not (save_dir / filename).exists():
            return filename
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique filename. Please retry.",
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(..., description="CSV file to upload")):
    """
    Upload a CSV file to the server.
    
    - Validates file type (.csv only)
    - Checks file size (max 10MB)
    - Stores file with unique timestamp-based name
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

    date_folder = datetime.now().strftime("%Y-%m-%d")
    save_dir = Path(UPLOAD_DIR) / date_folder
    save_dir.mkdir(parents=True, exist_ok=True)

    new_filename = generate_filename(file.filename, save_dir)
    file_path = save_dir / new_filename
    
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
    
    # Return a relative storage path (date_folder/filename) instead of the
    # absolute host path to avoid leaking server filesystem layout.
    relative_path = f"{date_folder}/{new_filename}"

    return UploadResponse(
        success=True,
        message="File uploaded successfully",
        filename=new_filename,
        file_path=relative_path,
        file_size=file_size
    )


