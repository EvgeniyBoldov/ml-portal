
# API Audit Tools

These tools scan your repo (FastAPI-like or similar) to find implemented HTTP routes and compare them to `api/openapi.yaml`.

## 1) Scan routes
```bash
python tools/audit_routes.py --root . --out tools/implemented_routes.json
```

## 2) Compare with contract
```bash
python tools/check_implemented_vs_spec.py   --spec api/openapi.yaml   --impl tools/implemented_routes.json   --report tools/compliance_report.md
```

Open `tools/compliance_report.md` — it contains:
- Implemented & in-spec
- Implemented but not in spec (LEGACY?)
- In spec but not implemented (TODO)
- Method/path diffs

Re-run these after each PR.
