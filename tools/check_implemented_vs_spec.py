
import argparse, json, yaml
from pathlib import Path
from collections import defaultdict

def load_spec(spec_path: Path):
    spec = yaml.safe_load(spec_path.read_text(encoding='utf-8'))
    paths = spec.get("paths", {})
    spec_routes = set()
    for pth, methods in paths.items():
        for m in methods.keys():
            spec_routes.add((m.upper(), pth))
    return spec_routes

def load_impl(impl_path: Path):
    data = json.loads(impl_path.read_text(encoding='utf-8'))
    impl_routes = set((r["method"].upper(), r["path"]) for r in data)
    return impl_routes, data

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--impl", required=True)
    ap.add_argument("--report", default="tools/compliance_report.md")
    args = ap.parse_args()

    spec_routes = load_spec(Path(args.spec))
    impl_routes, impl_data = load_impl(Path(args.impl))

    in_both = sorted(spec_routes & impl_routes)
    only_spec = sorted(spec_routes - impl_routes)
    only_impl = sorted(impl_routes - spec_routes)

    lines = []
    lines.append("# API Compliance Report\n")
    lines.append(f"- Implemented & in spec: {len(in_both)}")
    lines.append(f"- In spec but MISSING: {len(only_spec)}")
    lines.append(f"- Implemented but NOT in spec: {len(only_impl)}\n")

    def section(title, items):
        lines.append(f"## {title}\n")
        if not items:
            lines.append("_None_\n")
            return
        lines.append("| Method | Path |\n|---|---|\n")
        for m,p in items:
            lines.append(f"| {m} | {p} |\n")
        lines.append("\n")

    section("Implemented & In Spec", in_both)
    section("Missing (In Spec only)", only_spec)
    section("Legacy/Extra (Implemented only)", only_impl)

    Path(args.report).write_text("".join(lines), encoding='utf-8')
    print(f"Wrote report to {args.report}")

if __name__ == "__main__":
    main()
