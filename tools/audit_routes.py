
import argparse, json, os, re
from pathlib import Path

ROUTE_PATTERNS = [
    # FastAPI/APIRouter style
    r'\brouter\s*=\s*APIRouter\([^)]*\)',
    r'@router\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]+)[\'"]',
    r'@app\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]+)[\'"]',
    # Flask/FastAPI style app
    r'@app\.route\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*methods=\[(.*?)\]',
]

def iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        # Skip venv and caches
        if any(part in {".venv","venv","__pycache__",".pytest_cache",".mypy_cache"} for part in p.parts):
            continue
        yield p

def scan_routes(root: Path):
    routes = []
    for file in iter_py_files(root):
        try:
            text = file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for pat in ROUTE_PATTERNS:
            for m in re.finditer(pat, text, flags=re.M):
                if m.lastindex is None:  # router=... lines, ignore
                    continue
                if m.re.pattern.startswith('@app.route'):
                    # Flask-like capture
                    path = m.group(1)
                    methods = [s.strip(" '\"") for s in m.group(2).split(',')]
                    for method in methods:
                        routes.append({"method": method.upper(), "path": path, "file": str(file)})
                else:
                    method = m.group(1).upper()
                    path = m.group(2)
                    routes.append({"method": method, "path": path, "file": str(file)})
    # normalize
    for r in routes:
        if not r["path"].startswith("/"):
            r["path"] = "/" + r["path"]
    return routes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="tools/implemented_routes.json")
    args = ap.parse_args()

    routes = scan_routes(Path(args.root))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(routes, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Found {len(routes)} routes. Saved to {out}")

if __name__ == "__main__":
    main()
