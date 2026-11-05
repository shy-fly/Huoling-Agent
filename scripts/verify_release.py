"""Real localhost acceptance using an initialized evidence database."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

root = Path(__file__).resolve().parents[1]
with socket.socket() as address:
    address.bind(("127.0.0.1", 0))
    port = address.getsockname()[1]
process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
    cwd=root / "backend", env={**os.environ, "USE_LLM": "false"},
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
results = {}
try:
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=180, trust_env=False) as client:
        for attempt in range(100):
            try:
                if client.get("/health").is_success:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.2)
        def post(name, data):
            reply = client.post("/v1/research/" + name, json=data)
            reply.raise_for_status()
            results[name] = {"status": reply.status_code}
            return reply.json()
        question = "比较 Wang 2015 与 Yang 2018：氨水平对甲烷产量有显著影响吗？"
        qa = post("qa", {"question": question, "top_k": 8})
        assert qa["chunks"]
        context = {"question": question, "traceId": qa["trace_id"], "evidence": [
            {"chunkId": item["chunk_id"], "source": item["source"], "collection": item["collection"], "page": item["page"]}
            for item in qa["chunks"] if item["page"]
        ]}
        comparison = post("compare", {"question": question, "qaContext": context,
                                      "dimensions": ["TAN", "FAN"], "paperLimit": 6})
        assert comparison["qaContext"]["traceId"] == qa["trace_id"]
        expected = {item["paperId"] for item in comparison["qaContext"]["evidence"]}
        assert set(comparison["papers"]) == expected and len(expected) >= 2
        results["qaToCompare"] = {"paperCount": len(expected), "identityCheck": "passed"}
        endpoint = next(record for record in comparison["thresholdComparison"]["records"] if record["metric"] == "TAN")
        sourceId = endpoint["sourceId"]
        page = endpoint["page"]
        claim = "TAN 升高如何限定甲烷产量下降的结论？"
        challenge = post("falsification", {"hypothesis": claim, "sourceId": sourceId, "sourcePage": page})
        assert challenge["evidence"]
        gaps = post("gaps", {"question": claim, "includeIds": [sourceId], "sourcePages": {sourceId: [page]},
            "xAxis": {"field": "FAN", "unit": "mg/L", "edges": [0,100,300,500]}, "yAxis": {"field": "regime"}})
        cell = next(cell for cell in gaps["coverageMatrix"] if cell["recordCount"])
        design = post("experiment-design", {"question": claim, "outcome": "methane production",
            "context": {"origin": "gaps", "paperIds": cell["paperIds"], "recordIds": cell["recordIds"],
                "sourcePages": {sourceId: [page]}, "conditions": {"FAN": cell["x"], "regime": cell["y"]}},
            "factors": [{"name": "FAN", "levels": ["25 mg/L", "75 mg/L"]}],
            "control": {"FAN": "25 mg/L"}, "replicates": 2, "maxUnits": 4})
        assert design["totalExperimentalUnits"] == 4
        media = post("media/search", {"question": "ammonia Table 1", "kind": "table", "number": "1", "paperIds": [sourceId]})
        assert media["items"]
        item = media["items"][0]
        assert client.get(f'/v1/research/media/{item["chunkId"]}/{item["mediaId"]}/image').content.startswith(b"\x89PNG")
        built = post("knowledge-graph/build", {"question": claim, "paperIds": list(comparison["papers"]), "sourcePages": {sourceId: [page]}})
        graphId = built["graphId"]
        graph = client.get(f"/v1/research/knowledge-graph/{graphId}?limit=120").json()
        node = next(node for node in graph["nodes"] if node["type"] == "claim")
        audit = post("reliability-audit", {"type": "claim", "graphId": graphId, "entityId": node["id"]})
        assert audit["claimAssessments"]
        evolution = post("evolution", {"question": claim, "graphId": graphId, "claimId": node["id"]})
        assert evolution["events"]
        pdf = client.get("/v1/research/literature/" + quote(endpoint["source"], safe=""),
                         params={"collection": endpoint["collection"], "page": page})
        assert pdf.content.startswith(b"%PDF") and pdf.headers["x-pdf-page"] == str(page)
        results["evidence"] = {"source": endpoint["source"], "page": page,
            "records": len(gaps["experimentRecords"]), "experimentalUnits": design["totalExperimentalUnits"]}
finally:
    process.terminate()
    process.wait(timeout=10)
    print(json.dumps(results, ensure_ascii=True))
