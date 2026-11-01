"""Internal rendering probe; these strings are not accepted manifest aliases."""
import json
from pathlib import Path
import sys
from pg_plan_evidence.io import write

report = json.loads(Path(sys.argv[1]).read_text())
report['warnings'].append('<img src="https://example.test/probe" onerror="alert(1)"><script>alert(1)</script>')
write(sys.argv[2], report, 'html')
