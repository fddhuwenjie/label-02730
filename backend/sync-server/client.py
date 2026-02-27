#!/usr/bin/env python3
"""CSV file upload client with CLI support."""
import argparse
import sys
from pathlib import Path

import httpx


def upload_file(file_path: str, server_url: str, timeout: int = 30) -> bool:
    """
    Upload a CSV file to the server.
    
    Args:
        file_path: Path to the CSV file
        server_url: Server base URL
        timeout: Request timeout in seconds
    
    Returns:
        True if upload successful, False otherwise
    """
    path = Path(file_path)
    
    # Validate file exists
    if not path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return False
    
    # Validate file extension
    if path.suffix.lower() != ".csv":
        print(f"❌ Error: Only .csv files are allowed")
        return False
    
    upload_url = f"{server_url.rstrip('/')}/api/v1/upload"
    
    print(f"📤 Uploading: {path.name}")
    print(f"📍 Server: {upload_url}")
    
    try:
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "text/csv")}
            
            with httpx.Client(timeout=timeout) as client:
                response = client.post(upload_url, files=files)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success: {data['message']}")
            print(f"   Filename: {data['filename']}")
            print(f"   Size: {data['file_size']} bytes")
            return True
        else:
            error = response.json().get("detail", "Unknown error")
            print(f"❌ Server error ({response.status_code}): {error}")
            return False
            
    except httpx.ConnectError:
        print(f"❌ Connection error: Cannot connect to {server_url}")
        return False
    except httpx.TimeoutException:
        print(f"❌ Timeout: Server did not respond within {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Upload CSV files to the sync server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python client.py data.csv
  python client.py data.csv --url http://localhost:8000
  python client.py data.csv --timeout 60
        """
    )
    parser.add_argument("file", help="Path to the CSV file to upload")
    parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    success = upload_file(args.file, args.url, args.timeout)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
