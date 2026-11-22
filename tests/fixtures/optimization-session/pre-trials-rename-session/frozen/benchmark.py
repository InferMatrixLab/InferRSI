import json, runpy, sys
from pathlib import Path
value = runpy.run_path(sys.argv[1])['FACTOR']
output = Path(sys.argv[2])
output.mkdir()
with Path('calls.log').open('a') as stream:
    stream.write(str(value) + '\n')
status = 'completed' if value > 0 else 'candidate_failure'
result = {'status': status, 'verdict': 'PASS' if value > 0 else 'FAIL',
          'score': value if value > 0 else None}
(output / 'result.json').write_text(json.dumps(result))
