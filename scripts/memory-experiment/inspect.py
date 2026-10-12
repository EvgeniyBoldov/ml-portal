"""Export a saved comparison, including answer context, for independent judging."""
import argparse
import json
from run import ROOT, database

parser = argparse.ArgumentParser()
parser.add_argument('--index', required=True)
parser.add_argument('--run-id')
args = parser.parse_args()
conn = database()
conn.row_factory = __import__('sqlite3').Row
row = conn.execute('SELECT * FROM runs WHERE index_name=? AND stage=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (args.index, 'compare')).fetchone()
if args.run_id:
    row = conn.execute('SELECT * FROM runs WHERE id=?', (args.run_id,)).fetchone()
if row is None:
    raise SystemExit('No saved comparison for this index')
results = [{'question_id': r['question_id'], 'mode': r['mode'], **json.loads(r['payload'])}
           for r in conn.execute('SELECT * FROM results WHERE run_id=? ORDER BY question_id, mode', (row['id'],))]
payload = {'run': dict(row), 'results': results}
path = ROOT / 'results' / f"{row['index_name']}-{row['id']}-review.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
print(path)
