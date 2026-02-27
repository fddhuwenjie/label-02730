"""CSV file upload API endpoints."""
import os
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
    """Validate uploaded file type and size."""
    # Check file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Invalid file type: {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Only {', '.join(ALLOWED_EXTENSIONS)} allowed."
        )


def generate_filename(original_name: str) -> str:
    """Generate unique filename with timestamp and UUID."""
    ext = Path(original_name).suffix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique_id}{ext}"


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(..., description="CSV file to upload")):
    """
    Upload a CSV file to the server.
    
    - Validates file type (.csv only)
    - Checks file size (max 10MB)
    - Stores file with unique timestamp-based name
    """
    validate_file(file)
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Check file size
    if file_size > MAX_FILE_SIZE:
        logger.warning(f"File too large: {file_size} bytes")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB."
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed."
        )
    
    # Generate unique filename and save
    new_filename = generate_filename(file.filename)
    date_folder = datetime.now().strftime("%Y-%m-%d")
    save_dir = Path(UPLOAD_DIR) / date_folder
    save_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    return UploadResponse(
        success=True,
        message="File uploaded successfully",
        filename=new_filename,
        file_path=str(file_path),
        file_size=file_size
    )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
