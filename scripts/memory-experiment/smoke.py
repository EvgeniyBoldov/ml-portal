"""Exercise real OpenIE, persistent job status, graph/dense search and answering."""
import json
import time
from run import ROOT, call, database

index = 'smoke-' + time.strftime('%Y%m%d-%H%M%S')
policy = 'Изменение ACL гостевой сети требует согласования Security Lead. Исключение OFR-STD-07 действует только в проекте Office Refresh.'
job = call('/indexes', {'index': index, 'documents': [
    {'id': 'policy', 'content': policy},
    {'id': 'policy-copy', 'content': policy},
    {'id': 'ticket', 'content': 'Заявка OFR-2026-07 относится к проекту Office Refresh и изменяет ACL гостевой сети. Для заявки применяется политика изменения ACL.'},
]})
print(json.dumps(job), flush=True)
deadline = time.monotonic() + 300
while time.monotonic() < deadline:
    status = call('/jobs/' + job['job_id'])
    if status['status'] in ('succeeded', 'failed'):
        break
    time.sleep(2)
else:
    raise TimeoutError('Smoke index timeout')
print(json.dumps(status, ensure_ascii=False), flush=True)
if status['status'] != 'succeeded':
    raise RuntimeError(status.get('error'))
results = {'job': status}
for mode in ('dense', 'graph'):
    result = call('/search', {'index': index, 'query': 'Кто должен согласовать заявку OFR-2026-07 на изменение ACL гостевой сети?', 'mode': mode, 'top_k': 3})
    assert result['hits'], result
    assert any(len(hit['metadata'].get('source_refs', [])) == 2 for hit in result['hits']), 'Duplicate provenance lost'
    if mode == 'graph':
        assert result['graph_seeded'], 'Graph request fell back to dense in smoke fixture'
    results[mode] = result
results['answer'] = call('/answer', {'index': index, 'question': 'Кто согласовывает изменение ACL гостевой сети по заявке OFR-2026-07?', 'hits': results['graph']['hits']})
conn = database()
conn.execute('INSERT INTO runs(id,stage,index_name,metadata) VALUES(?,?,?,?)', (index, 'smoke', index, json.dumps(call('/health'))))
conn.execute('INSERT INTO results VALUES(?,?,?,?)', (index, 'smoke', 'all', json.dumps(results, ensure_ascii=False)))
conn.commit()
(ROOT / 'results' / 'hipporag-http-smoke.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
