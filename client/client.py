#!/usr/bin/env python3
"""CSV file upload client with CLI support, retry logic, and progress display."""
import argparse
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


def main():
    parser = argparse.ArgumentParser(
        description="Upload CSV files to the sync server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python client.py data.csv
  python client.py data.csv --url http://localhost:8000
  python client.py data.csv --timeout 60 --retries 5
        """,
    )
    parser.add_argument("file", help="Path to the CSV file to upload")
    parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        help="Maximum number of upload attempts (default: 3)",
    )

    args = parser.parse_args()

    success = upload_file(args.file, args.url, args.timeout, args.retries)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
