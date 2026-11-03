"""Union device intervals in the main-attention span; never a clean E2E claim."""
import collections
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

root = Path(sys.argv[1]).resolve()  # External campaign root containing retained raw traces
result = {}

def ns(value):
    return int(Decimal(value.strip()) * 1000)

def union_duration(intervals):
    end = None
    total = 0
    for start, stop in sorted(intervals):
        if end is None or start > end:
            total += stop - start
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total

for path in sorted((root/'runs/profile-lifecycle-5s-five-steps/traces').glob('diffusion_rank*/*/ASCEND_PROFILER_OUTPUT/kernel_details.csv')):
    rows = list(csv.DictReader(path.open()))
    attention = [r for r in rows if r['Type'] == 'LaserAttention' and '82944' in r['Input Shapes']]
    assert len(attention) == 250
    start = min(ns(r['Start Time(us)']) for r in attention)
    stop = max(ns(r['Start Time(us)']) + ns(r['Duration(us)']) for r in attention)
    groups = collections.defaultdict(list)
    categories = collections.Counter()
    for row in rows:
        a = max(start, ns(row['Start Time(us)']))
        b = min(stop, ns(row['Start Time(us)']) + ns(row['Duration(us)']))
        if b <= a:
            continue
        category = 'communication' if row['Type'].startswith('hcom_') else 'other_device_tasks'
        groups[category].append((a,b))
        categories[(row['Type'],row['Accelerator Core'])] += (b-a)/1e9
    other = union_duration(groups['other_device_tasks'])
    comm = union_duration(groups['communication'])
    combined = union_duration(groups['other_device_tasks']+groups['communication'])
    result[path.parts[-4]] = {
        'span_s':(stop-start)/1e9,
        'other_device_union_s':other/1e9,
        'communication_union_s':comm/1e9,
        'communication_outside_other_device_tasks_s':(combined-other)/1e9,
        'no_kernel_interval_s':(stop-start-combined)/1e9,
        'largest_task_type_sums_s':[(list(k),v) for k,v in categories.most_common(16)],
    }
(root/'profile-denoise-intervals-v2.json').write_text(json.dumps({
    'arithmetic':'Integer nanosecond interval arithmetic parsed from decimal microseconds; avoids rounding large absolute timestamps.',
    'scope':'Profiled five-step diagnostic, first through last main LaserAttention interval; excludes pre/post edges, not E2E or achievable speedup. Other device tasks include compute/copy; no-kernel intervals can include synchronization and dispatch.',
    'ranks':result},indent=2)+'\n')
print(json.dumps(result,indent=2))
