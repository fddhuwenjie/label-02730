#!/usr/bin/env python3
"""CSV file upload client with CLI support, retry logic, and progress display."""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def _attempt_upload(path: Path, upload_url: str, timeout: int) -> tuple[bool, str, dict]:
    """Perform a single upload attempt.

    Returns:
        (success, error_message, response_data)
    """
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "text/csv")}
        with httpx.Client(timeout=timeout) as client:
            response = client.post(upload_url, files=files)

    if response.status_code == 200:
        return True, "", response.json()

    error = response.json().get("detail", "Unknown error")
    return False, f"Server error ({response.status_code}): {error}", {}


def upload_file(
    file_path: str,
    server_url: str,
    timeout: int = 30,
    retries: int = 3,
) -> bool:
    """Upload a CSV file to the server with retry and progress display.

    Args:
        file_path: Path to the CSV file.
        server_url: Server base URL.
        timeout: Request timeout in seconds.
        retries: Maximum number of attempts (including the first try).

    Returns:
        True if upload succeeded, False otherwise.
    """
    path = Path(file_path)

    if not path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return False

    if path.suffix.lower() != ".csv":
        print(f"❌ Error: Only .csv files are allowed")
        return False

    upload_url = f"{server_url.rstrip('/')}/api/v1/upload"
    file_size_kb = path.stat().st_size / 1024

    print(f"📤 Uploading: {path.name} ({file_size_kb:.1f} KB)")
    print(f"📍 Server: {upload_url}")

    last_error = ""
    for attempt in range(1, retries + 1):
        if attempt > 1:
            # Exponential backoff: 1s, 2s, 4s, …
            wait = 2 ** (attempt - 2)
            print(f"↩️  Attempt {attempt}/{retries} — waiting {wait}s before retry...")
            time.sleep(wait)

        print(f"⏳ Sending request{'.' * attempt}", end="\r")
        try:
            success, error_msg, data = _attempt_upload(path, upload_url, timeout)
        except httpx.ConnectError:
            last_error = f"Connection error: Cannot connect to {server_url}"
            print(f"\n❌ {last_error}")
            continue
        except httpx.TimeoutException:
            last_error = f"Timeout: Server did not respond within {timeout}s"
            print(f"\n❌ {last_error}")
            continue
        except httpx.RequestError as e:
            last_error = f"Request error: {e}"
            print(f"\n❌ {last_error}")
            continue
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return False

        if success:
            print(f"\n✅ Success: {data['message']}")
            print(f"   Filename : {data['filename']}")
            print(f"   Size     : {data['file_size']} bytes")
            return True

        last_error = error_msg
        print(f"\n❌ {last_error}")

    print(f"❌ All {retries} attempt(s) failed. Last error: {last_error}")
    return False


def list_versions(file_name: str, server_url: str, timeout: int = 30) -> bool:
    """List all versions of a file."""
    base_name = Path(file_name).stem
    url = f"{server_url.rstrip('/')}/api/v1/files/{base_name}/versions"
    
    print(f"📋 Listing versions for: {file_name}")
    
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
    
    if response.status_code == 200:
        versions = response.json()
        print(f"\n✅ Found {len(versions)} version(s):")
        for v in versions:
            print(f"\n   Version {v['version']}:")
            print(f"   ─────────────────────────")
            print(f"      Uploaded: {v['upload_time']}")
            print(f"      Size: {v['file_size']} bytes")
            print(f"      Rows: {v['row_count']}")
        return True
    else:
        error = response.json().get("detail", "Unknown error")
        print(f"❌ Failed to list versions: {error}")
        return False


def diff_versions(file_name: str, v1: int, v2: int, server_url: str, timeout: int = 30) -> bool:
    """Diff two versions of a file."""
    base_name = Path(file_name).stem
    url = f"{server_url.rstrip('/')}/api/v1/files/{base_name}/diff?v1={v1}&v2={v2}"
    
    print(f"🔍 Comparing version {v1} vs {v2} for: {file_name}")
    
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Diff results:")
        print(f"   Added rows:    {data['added_rows']}")
        print(f"   Deleted rows:  {data['deleted_rows']}")
        print(f"   Modified rows: {data['modified_rows']}")
        return True
    else:
        error = response.json().get("detail", "Unknown error")
        print(f"❌ Failed to diff versions: {error}")
        return False


def delete_version(file_name: str, version: int, server_url: str, timeout: int = 30) -> bool:
    """Delete a specific version of a file."""
    base_name = Path(file_name).stem
    url = f"{server_url.rstrip('/')}/api/v1/files/{base_name}/versions/{version}"
    
    print(f"🗑️  Deleting version {version} of: {file_name}")
    
    with httpx.Client(timeout=timeout) as client:
        response = client.delete(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ {data['message']}")
        return True
    else:
        error = response.json().get("detail", "Unknown error")
        print(f"❌ Failed to delete version: {error}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="CSV file version management client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python client.py upload data.csv
  python client.py versions data.csv
  python client.py diff data.csv --v1 1 --v2 2
  python client.py delete data.csv --version 1
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    upload_parser = subparsers.add_parser("upload", help="Upload a CSV file")
    upload_parser.add_argument("file", help="Path to the CSV file to upload")
    upload_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    upload_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    upload_parser.add_argument("--retries", "-r", type=int, default=3, help="Max retries")
    
    versions_parser = subparsers.add_parser("versions", help="List file versions")
    versions_parser.add_argument("file", help="File name to list versions for")
    versions_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    versions_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    
    diff_parser = subparsers.add_parser("diff", help="Diff two versions")
    diff_parser.add_argument("file", help="File name to diff")
    diff_parser.add_argument("--v1", type=int, required=True, help="First version")
    diff_parser.add_argument("--v2", type=int, required=True, help="Second version")
    diff_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    diff_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    
    delete_parser = subparsers.add_parser("delete", help="Delete a version")
    delete_parser.add_argument("file", help="File name")
    delete_parser.add_argument("--version", type=int, required=True, help="Version to delete")
    delete_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    delete_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")

    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    success = False
    if args.command == "upload":
        success = upload_file(args.file, args.url, args.timeout, args.retries)
    elif args.command == "versions":
        success = list_versions(args.file, args.url, args.timeout)
    elif args.command == "diff":
        success = diff_versions(args.file, args.v1, args.v2, args.url, args.timeout)
    elif args.command == "delete":
        success = delete_version(args.file, args.version, args.url, args.timeout)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
