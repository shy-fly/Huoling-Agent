import json
import re
import time
from pathlib import Path

import httpx
import pymupdf
from pypdf import PdfReader
import logging
logging.getLogger("pypdf").setLevel(logging.ERROR)


import argparse
parser = argparse.ArgumentParser(description="Live multilingual acceptance; starts no model service.")
parser.add_argument("--url", default="http://127.0.0.1:8001")
parser.add_argument("--output", type=Path, default=Path("multilingual-results.json"))
parser.add_argument("--corpus", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge/literature_corpus")
args = parser.parse_args()
corpus = args.corpus

cases = [
    ("wang-zh", "Wang 2015 的研究中，氨水平对甲烷产量有显著影响吗？请总结实验对象、方法、结论和适用边界。"),
    ("wang-en", "In Wang 2015, did ammonia levels have a significant effect on methane production? Summarize the study organisms, methods, results and limitations in Chinese."),
    ("yang-zh", "Yang 2018 的研究怎样比较中温和高温厌氧消化？游离氨 FAN 与总氨氮 TAN 有何区别，表1的浓度能否直接视为抑制阈值？"),
    ("yang-en", "How did Yang 2018 compare mesophilic and thermophilic anaerobic digestion? Distinguish free ammonia nitrogen (FAN) from total ammonia nitrogen (TAN). Are Table 1 concentrations inhibition thresholds? Summarize in Chinese."),
    ("mixed", "厌氧消化中 mesophilic 和 thermophilic 条件如何影响 free ammonia (FAN)？请区分 TAN、FAN 和 methane inhibition threshold，并比较论文证据。"),
    ("english", "How do mesophilic and thermophilic conditions affect free ammonia (FAN) in anaerobic digestion? Distinguish TAN, FAN and methane inhibition thresholds and compare the paper evidence. Answer in Chinese."),
]
report = []
with httpx.Client(base_url=args.url, timeout=180) as client:
    print(json.dumps({"health": client.get("/health").json()["use_llm"]}), flush=True)
    for caseId, question in cases:
        start = time.monotonic()
        response = client.post("/v1/research/qa", json={"question": question, "top_k": 8})
        data = response.json()
        checks = {"http": response.status_code == 200,
                  "realModel": data.get("runtime", {}).get("answer_mode") == "model_with_references"}
        chunks = data.get("chunks", [])
        indices = [int(n) for n in re.findall(r"\[(\d+)\]", data.get("answer", ""))]
        checks["validCitations"] = bool(indices) and all(1 <= n <= len(chunks) for n in indices)
        evidence = []
        for chunk in chunks:
            path = corpus / chunk["collection"].removeprefix("literature_") / chunk["source"]
            with pymupdf.open(path) as pdf:
                page = chunk["page"]
                text = pdf[page - 1].get_text() if page and 1 <= page <= len(pdf) else ""
                # PDF extraction engines can disagree on whitespace and ligatures.
                normalize = lambda value: re.sub(r"\W", "", value.casefold().replace("ﬁ", "fi").replace("ﬂ", "fl"))
                snippet = chunk["snippet"].rstrip("…")
                matched = normalize(snippet[:100]) in normalize(text)
                if not matched:
                    alternate = PdfReader(path).pages[page - 1].extract_text() or ""
                    matched = normalize(snippet[:100]) in normalize(alternate)
                evidence.append({"source": chunk["source"], "page": page, "snippetVerified": matched})
        checks["pdfPages"] = bool(evidence) and all(item["snippetVerified"] for item in evidence)
        report.append({"caseId": caseId, "question": question, "seconds": round(time.monotonic()-start, 2),
                       "checks": checks, "evidenceVerification": evidence, "response": data})
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"caseId": caseId, "checks": checks, "seconds": report[-1]["seconds"]}), flush=True)

if not all(all(case["checks"].values()) for case in report):
    raise SystemExit("Live model acceptance failed; inspect the JSON report.")
