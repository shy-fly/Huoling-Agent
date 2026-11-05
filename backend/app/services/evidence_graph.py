"""Project PDF-verified comparison records into an attributed research graph."""
from hashlib import sha256
from itertools import zip_longest
import json
import unicodedata

from app.rag.media_index import indexPage
from app.rag.media_search import INDEX_ROOT, mediaPayload, pdfForChunk, requestedVisual

_ALIASES = {
    "tan": "TAN", "total ammonia nitrogen": "TAN", "总氨氮": "TAN",
    "fan": "FAN", "free ammonia nitrogen": "FAN", "游离氨氮": "FAN",
}


def stableId(*parts) -> str:
    value = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(value.encode("utf-8")).hexdigest()[:24]


def _text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _endpointKey(record: dict) -> tuple:
    return tuple(record[key] for key in ("sourceId", "page", "group", "metric", "unit", "endpoint", "value", "evidenceText"))


def _node(kind: str, key: tuple, label: str, **fields) -> dict:
    return {"id": stableId(kind, *key), "type": kind, "label": label, **fields}


def _contrasts(result: dict, sourceId: str):
    for table in result.get("groupTables", {}).get(sourceId, ()):
        if table.get("provenance") != "explicit_prose":
            continue
        for pair in table["contrasts"]:
            anchor = pair.get("controlEvidence") or {}
            if anchor.get("page") != table["page"] or not anchor.get("quote"):
                continue
            treatment, control = pair["treatment"], pair["control"]
            if treatment["header"] != control["header"]:
                continue
            yield {
                "page": table["page"], "group": treatment["group"],
                "metric": treatment["header"], "unit": "",
                "endpoint": treatment["header"],
                "value": f'{treatment["verifiedValue"]} / {control["verifiedValue"]}',
                "control": control["group"], "evidenceText": anchor["quote"],
                "provenance": table.get("provenance", "explicit_table_control"),
            }


def projectEvidenceGraph(
    result: dict, maxNodes: int, *, includeMedia: bool = True, indexed: list[dict] | None = None,
) -> dict:
    papers = result["papers"]
    comparison = result.get("thresholdComparison", {})
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    claims = {}
    mediaPages = {}
    truncated = False

    def addEdge(kind: str, source: dict, target: dict, evidence: list[dict], method: str, notes=()) -> None:
        if not evidence or source["id"] not in nodes or target["id"] not in nodes:
            return
        edgeId = stableId(kind, source["id"], target["id"])
        edges.setdefault(edgeId, {
            "id": edgeId, "type": kind, "source": source["id"], "target": target["id"],
            "evidence": evidence, "method": method, "notes": list(notes), "verificationStatus": "sourceChecked",
        })

    paperNodes = {}
    records = {}
    for sourceId, chunks in papers.items():
        first = chunks[0]
        paper = _node("paper", (sourceId,), first["source"], paperId=sourceId,
                      source=first["source"], collection=first["collection"], page=first["page"],
                      excerpt=first["evidenceText"][:600])
        nodes[paper["id"]] = paperNodes[sourceId] = paper
        records[sourceId] = [
            (item, _endpointKey(item)) for item in comparison.get("records", []) if item["sourceId"] == sourceId
        ]
        records[sourceId].extend((item, None) for item in _contrasts(result, sourceId))

    for batch in zip_longest(*(records[sourceId] for sourceId in papers)):
        for sourceId, entry in zip(papers, batch):
            if not entry:
                continue
            record, endpointKey = entry
            page = record["page"]
            pageChunks = [chunk for chunk in papers[sourceId] if chunk["page"] == page]
            if not pageChunks and record.get("provenance") == "curated_pdf_anchor":
                # This adapter already checked the exact quote against the original page.
                pageChunks = [chunk for chunk in indexed or () if chunk["source_id"] == sourceId
                              and chunk["page"] == page and chunk["source"] == record["source"]
                              and chunk["collection"] == record["collection"]]
            quote = record["evidenceText"].strip()
            if not pageChunks or not quote:
                continue
            source = pageChunks[0]
            exact = next((chunk for chunk in pageChunks
                          if _text(quote) in _text(chunk.get("evidenceText") or chunk.get("text") or "")), None)
            evidence = _node("evidence", (sourceId, page, _text(quote)), f"PDF 第 {page} 页",
                             paperId=sourceId, source=source["source"], collection=source["collection"],
                             page=page, excerpt=quote, chunkId=exact["id"] if exact else None)
            identity = (sourceId, page, record["group"], record.get("control"), record["metric"],
                        record["endpoint"], record["value"], record["unit"], record.get("qualifier"), evidence["id"])
            details = {key: record[key] for key in ("group", "metric", "endpoint", "value", "unit")}
            if "control" in record:
                details["control"] = record["control"]
            claim = _node("claim", identity, f'{record["group"]} · {record["endpoint"]} · {record["value"]} {record["unit"]}'.strip(),
                          paperId=sourceId, attributes=details)
            experiment = _node("experiment", identity, record["group"], paperId=sourceId, attributes=details)
            core = [claim, experiment, evidence]
            if len(nodes) + sum(item["id"] not in nodes for item in core) > maxNodes:
                truncated = True
                continue
            nodes.update((item["id"], item) for item in core)
            provenance = record.get("provenance", "curated_pdf_anchor")
            addEdge("reports", paperNodes[sourceId], experiment, [evidence], provenance)
            addEdge("reports", experiment, claim, [evidence], provenance, ("保留原实验组与响应终点。",))
            addEdge("derivedFrom", claim, evidence, [evidence], provenance)
            if endpointKey:
                claims[endpointKey] = claim, evidence
            metric = record["metric"].strip()
            canonical = _ALIASES.get(metric.casefold(), metric)
            variable = _node("variable", (canonical, record["unit"]), canonical,
                             attributes={"originalTerm": metric, "unit": record["unit"],
                                         "alignment": "explicit_alias" if canonical != metric else "literal"})
            if variable["id"] in nodes or len(nodes) < maxNodes:
                nodes.setdefault(variable["id"], variable)
                addEdge("usesVariable", experiment, variable, [evidence], provenance)
            else:
                truncated = True
            visual = requestedVisual(quote) if includeMedia else None
            if not visual or not (path := pdfForChunk(source)):
                continue
            cacheKey = (sourceId, page)
            if cacheKey not in mediaPages:
                mediaPages[cacheKey] = indexPage(INDEX_ROOT, path, sourceId, page)["visuals"]
            for item in mediaPages[cacheKey]:
                if (item["kind"], item["number"].casefold()) != visual:
                    continue
                media = _node("media", (item["mediaId"],), f'{item["kind"]} {item["number"]}',
                              paperId=sourceId, media=mediaPayload(item, pageChunks))
                if media["id"] in nodes or len(nodes) < maxNodes:
                    nodes.setdefault(media["id"], media)
                    addEdge("citesMedia", claim, media, [evidence], "explicit_same_page_caption",
                            ("原句明确提及该图表。", "图表边界可到 PDF 核对。"))
                else:
                    truncated = True

    for pair in comparison.get("incompatible", []):
        left = claims.get(_endpointKey(pair["left"]))
        right = claims.get(_endpointKey(pair["right"]))
        if left and right:
            left, right = sorted((left, right), key=lambda value: value[0]["id"])
            addEdge("notComparableWith", left[0], right[0], [left[1], right[1]],
                    "reported_endpoint_comparison", pair["reasons"])
    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "truncated": truncated}
