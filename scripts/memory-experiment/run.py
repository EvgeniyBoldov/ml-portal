"""HTTP-only experiment client; SQLite is built into Python, no portal imports."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, urlopen
import uuid
from urllib.error import HTTPError

ROOT = Path(os.getenv("EXPERIMENT_ROOT", "/experiment"))
URL = os.getenv("HIPPO_URL", "http://hipporag:8080").rstrip("/")


def call(path, payload=None):
    req = Request(URL + path, data=None if payload is None else json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=600) as response:
        return json.load(response)


def database():
    (ROOT / "results").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ROOT / "results" / "hipporag-http.sqlite3")
    conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, stage TEXT, index_name TEXT, metadata TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS results (run_id TEXT, question_id TEXT, mode TEXT, payload TEXT, PRIMARY KEY(run_id, question_id, mode))")
    return conn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["health", "index", "compare"])
    parser.add_argument("--index", default="fixture-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--retry", action="store_true", help="Resume a failed index with exactly the same input")
    parser.add_argument("--limit-docs", type=int)
    parser.add_argument("--timeout", type=int, default=14400)
    args = parser.parse_args()
    if args.stage == "health":
        print(json.dumps(call("/health"), ensure_ascii=False))
        return
    conn = database()
    run_id = str(uuid.uuid4())
    health = call("/health")
    conn.execute("INSERT INTO runs(id,stage,index_name,metadata) VALUES(?,?,?,?)", (run_id, args.stage, args.index, json.dumps(health)))
    conn.commit()
    if args.stage == "index":
        paths = sorted((ROOT / "corpus").glob("*.md"))
        if args.limit_docs:
            paths = paths[:args.limit_docs]
        docs = [{"id": p.name, "content": p.read_text(), "metadata": {"filename": p.name}} for p in paths]
        if not docs:
            raise RuntimeError("No corpus documents found")
        corpus_hash = hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest()
        job = call("/indexes", {"index": args.index, "documents": docs, "retry": args.retry})
        conn.execute("INSERT INTO results VALUES(?,?,?,?)", (run_id, "index", "job", json.dumps({**job, "corpus_sha256": corpus_hash})))
        conn.commit()
        print(json.dumps(job), flush=True)
        deadline = time.monotonic() + args.timeout
        previous = None
        while time.monotonic() < deadline:
            result = call("/jobs/" + job["job_id"])
            if result != previous:
                print(json.dumps(result, ensure_ascii=False), flush=True)
                previous = result
            conn.execute("INSERT OR REPLACE INTO results VALUES(?,?,?,?)", (run_id, "index", "status", json.dumps(result, ensure_ascii=False)))
            conn.commit()
            if result["status"] == "succeeded":
                return
            if result["status"] == "failed":
                raise RuntimeError(result.get("error"))
            time.sleep(10)
        raise TimeoutError("Index still running; query its job status before submitting anything else")
    questions = json.loads((ROOT / "eval" / "questions.json").read_text())
    summary = []
    for question in questions:
        for mode in ("dense", "graph"):
            try:
                result = call("/search", {"index": args.index, "query": question["question"], "mode": mode, "top_k": args.top_k})
            except Exception as error:
                detail = error.read().decode() if isinstance(error, HTTPError) else str(error)
                result = {"status": "failed", "error": detail}
                conn.execute("INSERT INTO results VALUES(?,?,?,?)", (run_id, question["id"], mode, json.dumps(result, ensure_ascii=False)))
                conn.commit()
                summary.append({"question": question["id"], "mode": mode, **result})
                print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
                continue
            found = {h["metadata"].get("document_id") for h in result["hits"]}
            # Some versions nest metadata under source_refs. Preserve raw hits for inspection.
            for hit in result["hits"]:
                for ref in hit["metadata"].get("source_refs", []):
                    found.add(ref.get("metadata", {}).get("document_id", ref.get("document_id")))
            required = set(question["source_documents"])
            result["source_document_recall"] = len(required & found) / len(required)
            result["missing_source_documents"] = sorted(required - found)
            result["required_claims"] = question["required_claims"]
            if args.answers:
                try:
                    result["answer"] = call("/answer", {"index": args.index, "question": question["question"], "hits": result["hits"]})
                except Exception as error:
                    detail = error.read().decode() if isinstance(error, HTTPError) else str(error)
                    result["answer"] = {"status": "failed", "error": detail}
            conn.execute("INSERT INTO results VALUES(?,?,?,?)", (run_id, question["id"], mode, json.dumps(result, ensure_ascii=False)))
            conn.commit()
            row = {"question": question["id"], "mode": mode, "source_document_recall": result["source_document_recall"], "graph_seeded": result["graph_seeded"]}
            summary.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    output = ROOT / "results" / f"{args.index}-{run_id}.json"
    output.write_text(json.dumps({"run_id": run_id, "index": args.index, "summary": summary}, indent=2, ensure_ascii=False))
    print(f"Saved {output}; raw retrieval and answers in hipporag-http.sqlite3", flush=True)


if __name__ == "__main__":
    main()
