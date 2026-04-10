#!/usr/bin/env python3
"""CSV file upload client with CLI support, retry logic, and progress display."""
import argparse
import sys
import time
from datetime import datetime
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
            print(f"   Version  : {data['version']}")
            print(f"   Size     : {data['file_size']} bytes")
            return True

        last_error = error_msg
        print(f"\n❌ {last_error}")

    print(f"❌ All {retries} attempt(s) failed. Last error: {last_error}")
    return False


def list_versions(filename: str, server_url: str, timeout: int = 30) -> bool:
    """List all versions of a file.

    Args:
        filename: Name of the file (without extension).
        server_url: Server base URL.
        timeout: Request timeout in seconds.

    Returns:
        True if successful, False otherwise.
    """
    versions_url = f"{server_url.rstrip('/')}/api/v1/files/{filename}/versions"

    print(f"📋 Listing versions for: {filename}")
    print(f"📍 Server: {versions_url}")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(versions_url)

        if response.status_code == 200:
            data = response.json()
            versions = data.get("versions", [])

            if not versions:
                print("ℹ️  No versions found.")
                return True

            print(f"\n📁 File: {data['filename']}")
            print(f"📊 Total versions: {len(versions)}")
            print("\n" + "-" * 70)
            print(f"{'Version':<10} {'Upload Time':<25} {'Size':<12} {'Rows':<10}")
            print("-" * 70)

            for v in versions:
                upload_time = v['upload_time']
                # Format datetime
                try:
                    dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_str = upload_time

                size_str = f"{v['file_size']:,} B"
                print(f"{v['version']:<10} {time_str:<25} {size_str:<12} {v['row_count']:<10}")

            print("-" * 70)
            return True
        elif response.status_code == 404:
            error = response.json().get("detail", "File not found")
            print(f"❌ Error: {error}")
            return False
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
        print(f"❌ Error: {e}")
        return False


def compare_versions(filename: str, v1: int, v2: int, server_url: str, timeout: int = 30) -> bool:
    """Compare two versions of a file.

    Args:
        filename: Name of the file (without extension).
        v1: First version number.
        v2: Second version number.
        server_url: Server base URL.
        timeout: Request timeout in seconds.

    Returns:
        True if successful, False otherwise.
    """
    diff_url = f"{server_url.rstrip('/')}/api/v1/files/{filename}/diff"

    print(f"🔍 Comparing versions of: {filename}")
    print(f"📍 Server: {diff_url}")
    print(f"📊 Comparing v{v1} → v{v2}")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(diff_url, params={"v1": v1, "v2": v2})

        if response.status_code == 200:
            data = response.json()

            print(f"\n📁 File: {data['filename']}")
            print(f"📊 Version {data['version1']} → Version {data['version2']}")
            print("\n" + "-" * 40)
            print(f"  ➕ Added rows:    {data['added_rows']}")
            print(f"  ➖ Deleted rows:  {data['deleted_rows']}")
            print(f"  ✏️  Modified rows: {data['modified_rows']}")
            print("-" * 40)
            return True
        elif response.status_code == 404:
            error = response.json().get("detail", "Version not found")
            print(f"❌ Error: {error}")
            return False
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
        print(f"❌ Error: {e}")
        return False


def delete_version(filename: str, version: int, server_url: str, timeout: int = 30) -> bool:
    """Delete a specific version of a file.

    Args:
        filename: Name of the file (without extension).
        version: Version number to delete.
        server_url: Server base URL.
        timeout: Request timeout in seconds.

    Returns:
        True if successful, False otherwise.
    """
    delete_url = f"{server_url.rstrip('/')}/api/v1/files/{filename}/versions/{version}"

    print(f"🗑️  Deleting version {version} of: {filename}")
    print(f"📍 Server: {delete_url}")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.delete(delete_url)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ {data['message']}")
            return True
        elif response.status_code == 400:
            error = response.json().get("detail", "Cannot delete this version")
            print(f"❌ Error: {error}")
            return False
        elif response.status_code == 404:
            error = response.json().get("detail", "Version not found")
            print(f"❌ Error: {error}")
            return False
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
        print(f"❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="CSV file upload client with version management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a file
  python client.py upload data.csv
  python client.py upload data.csv --url http://localhost:8000

  # List all versions of a file
  python client.py versions data

  # Compare two versions
  python client.py diff data --v1 1 --v2 2

  # Delete a specific version
  python client.py delete data --version 1
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload a CSV file")
    upload_parser.add_argument("file", help="Path to the CSV file to upload")
    upload_parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    upload_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    upload_parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        help="Maximum number of upload attempts (default: 3)",
    )

    # Versions command
    versions_parser = subparsers.add_parser("versions", help="List all versions of a file")
    versions_parser.add_argument("filename", help="Name of the file (without extension)")
    versions_parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    versions_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )

    # Diff command
    diff_parser = subparsers.add_parser("diff", help="Compare two versions of a file")
    diff_parser.add_argument("filename", help="Name of the file (without extension)")
    diff_parser.add_argument("--v1", type=int, required=True, help="First version number")
    diff_parser.add_argument("--v2", type=int, required=True, help="Second version number")
    diff_parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    diff_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a specific version of a file")
    delete_parser.add_argument("filename", help="Name of the file (without extension)")
    delete_parser.add_argument("--version", "-v", type=int, required=True, help="Version number to delete")
    delete_parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    delete_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "upload":
        success = upload_file(args.file, args.url, args.timeout, args.retries)
    elif args.command == "versions":
        success = list_versions(args.filename, args.url, args.timeout)
    elif args.command == "diff":
        success = compare_versions(args.filename, args.v1, args.v2, args.url, args.timeout)
    elif args.command == "delete":
        success = delete_version(args.filename, args.version, args.url, args.timeout)
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
