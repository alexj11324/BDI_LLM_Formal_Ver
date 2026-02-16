
import sys
import argparse
from pathlib import Path

# Add script directory to path to import harness
sys.path.append(str(Path(__file__).resolve().parent))

from swe_bench_harness import LocalSWEBenchHarness

def main():
    parser = argparse.ArgumentParser(description="Run iterative fixes on SWE-bench instances")
    parser.add_argument("--instances", type=str, nargs="+", help="List of instance IDs to run")
    parser.add_argument("--limit", type=int, default=1, help="Limit number of instances if auto-selecting")
    parser.add_argument("--workspace", type=str, default="swe_bench_workspace", help="Workspace directory")
    args = parser.parse_args()
    
    harness = LocalSWEBenchHarness(workspace_dir=args.workspace)
    
    # If no instances provided, pick from dataset
    instances_to_run = args.instances
    if not instances_to_run:
        print(f"No instances provided. Selecting first {args.limit} from dataset...")
        # Accessing the dataset triggers the download
        ds = harness.dataset
        instances_to_run = [item['instance_id'] for item in ds.select(range(args.limit))]
        
    print(f"Starting Iterative Fix for {len(instances_to_run)} instances...")
    
    results = []
    for instance_id in instances_to_run:
        try:
            print(f"\n>>> Processing {instance_id}")
            result = harness.run_instance(instance_id)
            results.append(result)
            
            # Fail-fast check? 
            # The harness run_instance returns a dict. We can add status check.
            # For now, we just print result.
            print("Result:", result)
            
        except Exception as e:
            print(f"!!! Error processing {instance_id}: {e}")
            # If fail-fast is desired, we could break here.
            # But usually we want to see the attempt.
            
    # Summary
    print("\n=== Summary ===")
    for res in results:
        print(f"{res['instance_id']}: {res.get('changed_files', [])}")

if __name__ == "__main__":
    main()
