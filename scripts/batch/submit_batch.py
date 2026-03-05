#!/usr/bin/env python3
"""
Phase 2: Submit JSONL to Alibaba Cloud Batch Inference API.

Uses OpenAI-compatible Batch API:
  1. Upload JSONL file
  2. Create Batch job  
  3. Poll until completion
  4. Download results

Requires: DASHSCOPE_API_KEY environment variable

Usage:
  python scripts/submit_batch.py --domain blocksworld
  python scripts/submit_batch.py --domain blocksworld --test   # Use test model
  python scripts/submit_batch.py --status <batch_id>           # Check status
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_client() -> OpenAI:
    """Initialize OpenAI client for Alibaba Cloud."""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY not set.")
        print("Get your key from: https://bailian.console.aliyun.com/")
        print("Then: export DASHSCOPE_API_KEY=sk-xxx")
        sys.exit(1)
    
    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def upload_file(client: OpenAI, file_path: str) -> str:
    """Upload JSONL file and return file ID."""
    print(f"Uploading {file_path}...")
    file_obj = client.files.create(
        file=Path(file_path),
        purpose="batch"
    )
    print(f"  ✓ File ID: {file_obj.id}")
    return file_obj.id


def create_batch(client: OpenAI, file_id: str, is_test: bool = False) -> str:
    """Create a batch job and return batch ID."""
    endpoint = "/v1/chat/ds-test" if is_test else "/v1/chat/completions"
    print(f"Creating batch job (endpoint: {endpoint})...")
    
    batch = client.batches.create(
        input_file_id=file_id,
        endpoint=endpoint,
        completion_window="24h"
    )
    print(f"  ✓ Batch ID: {batch.id}")
    print(f"  Status: {batch.status}")
    return batch.id


def poll_status(client: OpenAI, batch_id: str, interval: int = 30) -> dict:
    """Poll batch job until completion. Returns final batch object."""
    print(f"\nPolling batch {batch_id}...")
    
    while True:
        batch = client.batches.retrieve(batch_id)
        completed = batch.request_counts.completed if batch.request_counts else 0
        failed = batch.request_counts.failed if batch.request_counts else 0
        total = batch.request_counts.total if batch.request_counts else 0
        
        print(f"  [{time.strftime('%H:%M:%S')}] Status: {batch.status} "
              f"| Progress: {completed}/{total} done, {failed} failed")
        
        if batch.status in ("completed", "failed", "expired", "cancelled"):
            return batch
        
        time.sleep(interval)


def download_results(client: OpenAI, batch, output_dir: Path, domain: str):
    """Download result and error files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if batch.output_file_id:
        result_path = output_dir / f"{domain}_results.jsonl"
        content = client.files.content(batch.output_file_id)
        content.write_to_file(str(result_path))
        print(f"  ✓ Results: {result_path}")
    
    if batch.error_file_id:
        error_path = output_dir / f"{domain}_errors.jsonl"
        content = client.files.content(batch.error_file_id)
        content.write_to_file(str(error_path))
        print(f"  ✗ Errors: {error_path}")


def check_status(client: OpenAI, batch_id: str):
    """Check status of an existing batch job."""
    batch = client.batches.retrieve(batch_id)
    completed = batch.request_counts.completed if batch.request_counts else 0
    failed = batch.request_counts.failed if batch.request_counts else 0
    total = batch.request_counts.total if batch.request_counts else 0
    
    print(f"\nBatch: {batch_id}")
    print(f"Status: {batch.status}")
    print(f"Progress: {completed}/{total} completed, {failed} failed")
    
    if batch.output_file_id:
        print(f"Output file: {batch.output_file_id}")
    if batch.error_file_id:
        print(f"Error file: {batch.error_file_id}")
    
    return batch


def main():
    parser = argparse.ArgumentParser(description="Submit batch inference to Alibaba Cloud")
    parser.add_argument("--domain", type=str,
                        help="Domain to submit (blocksworld/logistics/depots)")
    parser.add_argument("--input-file", type=str,
                        help="Custom JSONL input file path")
    parser.add_argument("--test", action="store_true",
                        help="Use test model (free, no actual inference)")
    parser.add_argument("--status", type=str,
                        help="Check status of batch ID")
    parser.add_argument("--download", type=str,
                        help="Download results for batch ID")
    parser.add_argument("--poll-interval", type=int, default=60,
                        help="Poll interval in seconds (default: 60)")
    parser.add_argument("--no-wait", action="store_true",
                        help="Don't wait for completion, just submit")
    parser.add_argument("--output-dir", default="runs/batch_inference",
                        help="Output directory")
    args = parser.parse_args()
    
    client = get_client()
    output_dir = Path(args.output_dir)
    
    # Status check mode
    if args.status:
        check_status(client, args.status)
        return
    
    # Download mode
    if args.download:
        batch = client.batches.retrieve(args.download)
        domain = args.domain or "unknown"
        download_results(client, batch, output_dir, domain)
        return
    
    # Submit mode
    if not args.domain and not args.input_file:
        parser.error("--domain or --input-file required for submission")
    
    input_file = args.input_file or f"runs/batch_inference/{args.domain}.jsonl"
    if not os.path.exists(input_file):
        print(f"ERROR: Input file not found: {input_file}")
        print(f"Run first: python scripts/prepare_batch_jsonl.py --domains {args.domain}")
        sys.exit(1)
    
    domain = args.domain or Path(input_file).stem
    
    # Line count
    with open(input_file) as f:
        n_lines = sum(1 for _ in f)
    print(f"\n{'='*60}")
    print(f"  Batch Inference Submission")
    print(f"  Domain: {domain}")
    print(f"  Requests: {n_lines}")
    print(f"  Test mode: {args.test}")
    print(f"{'='*60}\n")
    
    # Step 1: Upload
    file_id = upload_file(client, input_file)
    
    # Step 2: Create batch
    batch_id = create_batch(client, file_id, is_test=args.test)
    
    # Save batch info
    batch_info = {
        "domain": domain,
        "batch_id": batch_id,
        "file_id": file_id,
        "input_file": input_file,
        "n_requests": n_lines,
        "test_mode": args.test,
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    info_file = output_dir / f"{domain}_batch_info.json"
    with open(info_file, "w") as f:
        json.dump(batch_info, f, indent=2)
    print(f"  Batch info saved: {info_file}")
    
    if args.no_wait:
        print(f"\nBatch submitted. Check status later with:")
        print(f"  python scripts/submit_batch.py --status {batch_id}")
        return
    
    # Step 3: Poll
    batch = poll_status(client, batch_id, interval=args.poll_interval)
    
    # Step 4: Download
    if batch.status == "completed":
        print(f"\n✓ Batch completed!")
        download_results(client, batch, output_dir, domain)
        print(f"\nNext step: python scripts/parse_batch_results.py --domain {domain}")
    else:
        print(f"\n✗ Batch ended with status: {batch.status}")
        if hasattr(batch, 'errors') and batch.errors:
            print(f"Errors: {batch.errors}")


if __name__ == "__main__":
    main()
