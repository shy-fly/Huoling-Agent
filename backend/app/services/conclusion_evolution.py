"""Project dated papers and source-checked graph claims onto a bounded timeline."""
from collections import defaultdict

from app.services.evidence_graph import stableId

_PRIORITY = {"issue": 2, "publisherPublished": 1}
_STANCES = {"supports", "contradicts", "qualifies"}


def selectPublications(metadata: dict, start: int | None, end: int | None) -> tuple[dict, dict]:
    buckets = defaultdict(list)
    skipped = {"duplicates": 0, "missingYear": 0, "outsideRange": 0}
    for paperId, date in metadata.items():
        buckets[("doi", date["doi"].casefold()) if date.get("doi") else ("paper", paperId)].append((paperId, date))
    chosen = {}
    for versions in buckets.values():
        skipped["duplicates"] += len(versions) - 1
        paperId, date = max(versions, key=lambda row: _PRIORITY.get(row[1]["kind"], 0))
        priority = _PRIORITY.get(date["kind"], 0)
        peers = {item["year"] for _, item in versions if _PRIORITY.get(item["kind"], 0) == priority}
        if not date["year"] or len(peers) != 1:
            skipped["missingYear"] += 1
        elif (start and date["year"] < start) or (end and date["year"] > end):
            skipped["outsideRange"] += 1
        else:
            chosen[paperId] = date
    return chosen, skipped


def timelineFromGraph(graph: dict, publications: dict, grouping: int, studies: dict | None = None) -> dict:
    nodes = {item["id"]: item for item in graph["nodes"]}
    claims = defaultdict(list)
    evidence = defaultdict(dict)
    media = defaultdict(dict)
    for edge in graph["edges"]:
        if edge["verificationStatus"] != "sourceChecked":
            continue
        if edge["type"] == "derivedFrom":
            for ref in edge["evidence"]:
                evidence[edge["source"]][ref["id"]] = ref
        elif edge["type"] == "citesMedia" and (item := nodes.get(edge["target"], {}).get("media")):
            media[edge["source"]][item["mediaId"]] = item
    for node in nodes.values():
        if node["type"] == "claim" and evidence[node["id"]]:
            claims[node["paperId"]].append(node)
    papers = {node["paperId"]: node for node in nodes.values() if node["type"] == "paper"}
    events = {}
    byClaim = {}
    for paperId, date in sorted(publications.items(), key=lambda row: (row[1]["year"], row[0])):
        paper = papers.get(paperId)
        if not paper:
            continue
        publication = {key: date[key] for key in ("year", "kind", "doi", "onlineYear", "excerpt", "onlineExcerpt")}
        event = {
            "eventId": stableId("publication-event", paperId, date["year"]), "paperId": paperId,
            "year": date["year"], "source": paper["source"], "collection": paper["collection"],
            "publication": publication, "claims": [], "method": (studies or {}).get(paperId),
        }
        events[paperId] = event
        for claim in claims[paperId]:
            byClaim[claim["id"]] = event
            event["claims"].append({
                "claimId": claim["id"], "statement": claim["label"], "conditions": claim.get("attributes", {}),
                "references": list(evidence[claim["id"]].values()), "media": list(media[claim["id"]].values()),
            })
    relations = []
    for edge in graph["edges"]:
        left, right = byClaim.get(edge["source"]), byClaim.get(edge["target"])
        if not left or not right or left["paperId"] == right["paperId"]:
            continue
        kind = edge["type"]
        checked = kind == "notComparableWith" and edge["verificationStatus"] == "sourceChecked"
        checked |= kind in _STANCES and edge.get("scientificStatus") == "verified"
        if not checked or not edge["evidence"]:
            continue
        if {ref["paperId"] for ref in edge["evidence"]} != {left["paperId"], right["paperId"]}:
            continue
        original = [edge["source"], edge["target"]]
        if (left["year"], left["paperId"]) > (right["year"], right["paperId"]):
            left, right = right, left
        relations.append({
            "relationId": edge["id"], "sourceEventId": left["eventId"], "targetEventId": right["eventId"],
            "type": kind, "claimIds": original, "sameYear": left["year"] == right["year"],
            "references": edge["evidence"], "basis": edge.get("notes", []),
        })
    periods = {}
    for event in events.values():
        year = event["year"]
        start = year - year % grouping
        counts = periods.setdefault(start, {"startYear": start, "endYear": start + grouping - 1, "paperCount": 0,
                                            "experimentRecordCount": 0, "directEvidenceCount": 0})
        counts["paperCount"] += 1
        counts["experimentRecordCount"] += len(event["claims"])
        counts["directEvidenceCount"] += len({ref["id"] for claim in event["claims"] for ref in claim["references"]})
    return {"events": list(events.values()), "relations": relations, "periods": list(periods.values())}
