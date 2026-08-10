"""
Re-bucket E2 10-minute throughput data by real elapsed-time minute.

The original per-minute breakdown showed identical values (550.0 for all 10 minutes),
which suggests the aggregate was repeated rather than genuinely bucketed.
This script uses the raw timestamped batch data to compute real per-minute throughput.
"""

import json

# Load raw timestamped batch data
with open('batch_timestamps.json', 'r') as f:
    batch_data = json.load(f)

batch_timestamps = batch_data['batch_timestamps']

if not batch_timestamps:
    print("ERROR: No batch timestamps found")
    exit(1)

# Get start time (first batch)
start_time = batch_timestamps[0][0]
print(f"Start time: {start_time}")

# Initialize minute buckets (10 minutes: 0-1, 1-2, ..., 9-10)
minute_buckets = {i: {'docs': 0, 'batches': 0} for i in range(10)}

# Bucket each batch by its elapsed time
for timestamp, doc_count in batch_timestamps:
    elapsed_seconds = timestamp - start_time
    elapsed_minute = int(elapsed_seconds // 60)
    
    # Cap at minute 9 (anything beyond 10 minutes goes into last bucket)
    if elapsed_minute >= 10:
        elapsed_minute = 9
    
    minute_buckets[elapsed_minute]['docs'] += doc_count
    minute_buckets[elapsed_minute]['batches'] += 1

# Compute docs/min for each minute
per_minute_results = []
for minute in range(10):
    bucket = minute_buckets[minute]
    docs = bucket['docs']
    batches = bucket['batches']
    
    # Estimate the actual time window for this minute
    # For simplicity, assume 60 seconds per minute (could be refined with actual timestamps)
    docs_per_minute = docs  # Since batches are already per-minute scale
    
    per_minute_results.append({
        'minute': minute + 1,  # 1-indexed for display
        'docs_per_minute': docs_per_minute,
        'batches': batches,
        'meets_target': docs_per_minute >= 500
    })

# Print results
print("\n" + "=" * 80)
print("REAL PER-MINUTE THROUGHPUT BREAKDOWN (from raw timestamped batch data)")
print("=" * 80)

total_docs = sum(bucket['docs'] for bucket in minute_buckets.values())
total_batches = sum(bucket['batches'] for bucket in minute_buckets.values())

print(f"\nTotal documents: {total_docs}")
print(f"Total batches: {total_batches}")
print(f"\nPer-minute breakdown:\n")

for result in per_minute_results:
    status = "✓" if result['meets_target'] else "✗"
    print(f"  Minute {result['minute']:2d}: {result['docs_per_minute']:7.1f} docs/min ({result['batches']} batches) {status}")

# Check if all minutes meet target
all_meet_target = all(r['meets_target'] for r in per_minute_results)

print("\n" + "=" * 80)
if all_meet_target:
    print("RESULT: PASS - All 10 minutes meet ≥500 docs/min target")
else:
    print("RESULT: FAIL - One or more minutes below ≥500 docs/min target")
print("=" * 80)

# Save corrected results
corrected_results = {
    "test_type": "E2 10-minute sustained throughput (CORRECTED)",
    "start_time": start_time,
    "aggregate_metrics": {
        "overall_docs_per_minute": total_docs / 10,
        "total_documents": total_docs,
        "total_batches": total_batches,
        "actual_duration_seconds": batch_timestamps[-1][0] - start_time
    },
    "per_minute_breakdown": per_minute_results,
    "meets_target": all_meet_target
}

with open('e2_10min_results_corrected.json', 'w') as f:
    json.dump(corrected_results, f, indent=2)

print("\nCorrected results saved to e2_10min_results_corrected.json")
