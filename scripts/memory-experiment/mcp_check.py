"""Check the live JSON-RPC shim against a completed index."""
import argparse
import json
from urllib.request import Request, urlopen
from run import URL

parser = argparse.ArgumentParser()
parser.add_argument('--index', required=True)
args = parser.parse_args()
session = None


def rpc(method, params=None):
    global session
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
    headers = {'Content-Type': 'application/json'}
    if session:
        headers['mcp-session-id'] = session
    with urlopen(Request(URL + '/mcp', data=json.dumps(payload).encode(), headers=headers), timeout=120) as response:
        session = response.headers.get('mcp-session-id') or session
        result = json.load(response)
    if 'error' in result:
        raise RuntimeError(result['error'])
    return result['result']


print(rpc('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'experiment', 'version': '1'}}))
tools = rpc('tools/list')['tools']
print('Tools:', [t['name'] for t in tools])
result = rpc('tools/call', {'name': 'hipporag_search', 'arguments': {'index': args.index, 'query': 'Изменение ACL гостевой сети', 'mode': 'dense', 'top_k': 2}})
assert not result.get('isError'), result
hits = json.loads(result['content'][0]['text'])['hits']
assert hits
print('MCP search OK, hits:', len(hits))
