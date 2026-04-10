#!/usr/bin/env python3
"""CSV file upload client with CLI support, retry logic, and file version management."""
import argparse
import sys
import time
from pathlib import Path

import httpx


def list_file_versions(file_name: str, server_url: str, timeout: int = 30) -> bool:
    """List all versions of a file."""
    base_name = Path(file_name).stem if "." in file_name else file_name
    url = f"{server_url.rstrip('/')}/api/files/{base_name}/versions"
    
    print(f"🔍 Fetching versions for: {file_name}")
    print(f"📍 Endpoint: {url}")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
        
        if response.status_code == 200:
            versions = response.json()
            if not versions:
                print("ℹ️ No versions found for this file")
                return True
            
            print(f"\n📋 Found {len(versions)} version(s):")
            print("-" * 80)
            print(f"{'Version':<8} {'Upload Time':<25} {'Size (bytes)':<15} {'Rows':<8}")
            print("-" * 80)
            
            for v in versions:
                print(f"{v['version']:<8} {v['upload_time']:<25} {v['file_size']:<15} {v['row_count']:<8}")
            
            print("-" * 80)
            return True
        else:
            error = response.json().get("detail", "Unknown error")
            print(f"❌ Server error ({response.status_code}): {error}")
            return False
            
    except httpx.ConnectError:
        print(f"❌ Connection error: Cannot connect to {server_url}")
        return False


def compare_file_versions(file_name: str, v1: int, v2: int, server_url: str, timeout: int = 30) -> bool:
    """Compare two file versions."""
    base_name = Path(file_name).stem if "." in file_name else file_name
    url = f"{server_url.rstrip('/')}/api/files/{base_name}/diff?v1={v1}&v2={v2}"
    
    print(f"🔍 Comparing versions: v{v1} vs v{v2}")
    print(f"📍 Endpoint: {url}")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
        
        if response.status_code == 200:
            result = response.json()
            print("\n📊 Diff Results:")
            print(f"  • Rows added: {result['rows_added']}")
            print(f"  • Rows deleted: {result['rows_deleted']}")
            print(f"  • Rows modified: {result['rows_modified']}")
            return True
        else:
            error = response.json().get("detail", "Unknown error")
            print(f"❌ Server error ({response.status_code}): {error}")
            return False
            
    except httpx.ConnectError:
        print(f"❌ Connection error: Cannot connect to {server_url}")
        return False


def delete_file_version(file_name: str, version: int, server_url: str, timeout: int = 30) -> bool:
    """Delete a specific file version."""
    base_name = Path(file_name).stem if "." in file_name else file_name
    url = f"{server_url.rstrip('/')}/api/files/{base_name}/versions/{version}"
    
    print(f"🗑️  Deleting version: v{version}")
    print(f"📍 Endpoint: {url}")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.delete(url)
        
        if response.status_code == 204:
            print(f"✅ Version {version} deleted successfully!")
            return True
        else:
            error = response.json().get("detail", "Unknown error")
            print(f"❌ Server error ({response.status_code}): {error}")
            return False
            
    except httpx.ConnectError:
        print(f"❌ Connection error: Cannot connect to {server_url}")
        return False


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


def main():
    parser = argparse.ArgumentParser(
        description="CSV file management client for the sync server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a file
  python client.py upload data.csv
  python client.py upload data.csv --url http://localhost:8000 --timeout 60
  
  # List file versions
  python client.py versions myfile.csv
  python client.py versions myfile
  
  # Compare two versions
  python client.py diff myfile.csv 1 2
  
  # Delete a version (cannot delete latest version)
  python client.py delete myfile.csv 1
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    upload_parser = subparsers.add_parser("upload", help="Upload a CSV file")
    upload_parser.add_argument("file", help="Path to the CSV file to upload")
    upload_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    upload_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    upload_parser.add_argument("--retries", "-r", type=int, default=3, help="Max upload attempts")
    
    versions_parser = subparsers.add_parser("versions", help="List file versions")
    versions_parser.add_argument("file", help="Name of the CSV file")
    versions_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    versions_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    
    diff_parser = subparsers.add_parser("diff", help="Compare two file versions")
    diff_parser.add_argument("file", help="Name of the CSV file")
    diff_parser.add_argument("v1", type=int, help="First version number")
    diff_parser.add_argument("v2", type=int, help="Second version number")
    diff_parser.add_argument("--url", "-u", default="http://localhost:8000", help="Server URL")
    diff_parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout")
    
    delete_parser = subparsers.add_parser("delete", help="Delete a file version")
    delete_parser.add_argument("file", help="Name of the CSV file")
    delete_parser.add_argument("version", type=int, help="Version number to delete")
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
        success = list_file_versions(args.file, args.url, args.timeout)
    elif args.command == "diff":
        success = compare_file_versions(args.file, args.v1, args.v2, args.url, args.timeout)
    elif args.command == "delete":
        success = delete_file_version(args.file, args.version, args.url, args.timeout)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
