"""Normalize supported bilingual terminology without changing the user's question."""
import re

from app.rag.retriever import QUERY_ALIASES

_TERMS = {
    **{key: value[0] for key, value in QUERY_ALIASES.items()},
    "中温": "mesophilic", "高温": "thermophilic", "低温": "psychrophilic",
    "温度": "temperature", "驯化": "acclimation", "对照组": "control group",
    "处理组": "treatment group", "方法": "methods", "结论": "results",
}
_STOP = set("how did do does in on of to the a an and or is are were was from with "
            "have has what which please summarize summary answer chinese english "
            "distinguish compare comparison study paper research conditions affect evidence".split())
_NAMED = re.compile(r"(?<!\w)([a-z]{2,30})\s*(?:等|et\s+al\.?)?\s*[（(]?\s*((?:19|20)\d{2})", re.I)
_METHOD = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:materials and methods|experimental (?:design|setup)|methods)\b")


def searchQuestion(question: str) -> str:
    text = question.casefold()
    for label in sorted(_TERMS, key=len, reverse=True):
        text = text.replace(label, " " + _TERMS[label] + " ")
    tokens = re.findall(r"[a-z][a-z0-9-]*|\d+(?:\.\d+)?", text)
    singular = {"thresholds": "threshold", "concentrations": "concentration", "levels": "level"}
    tokens = [singular.get(token, token) for token in tokens]
    return " ".join(dict.fromkeys(token for token in tokens if token not in _STOP)) or question


def namedPaperIds(question: str, chunks: list[dict]) -> set[str] | None:
    named = list(_NAMED.finditer(question))
    if not named:
        return None
    patterns = [re.compile(rf"^{re.escape(match[1])}[-_ ]+{match[2]}[-_ .]", re.I) for match in named]
    return {chunk["source_id"] for chunk in chunks if chunk.get("source_id") and
            any(pattern.search(chunk.get("source") or "") for pattern in patterns)}


def includeMethods(ranked: list[dict], indexed: list[dict], limit: int) -> list[dict]:
    if limit < 2:
        return ranked
    def completePage(chunk: dict) -> dict:
        siblings = [item for item in indexed if item.get("source_id") == chunk.get("source_id")
                    and item.get("page") == chunk.get("page")]
        body = "\n".join(item["text"] for item in siblings) or chunk["text"]
        heading = _METHOD.search(body)
        return {**chunk, "text": body[heading.start():] if heading else body}

    ranked = [completePage(chunk) if _METHOD.search(chunk.get("text") or "") else chunk for chunk in ranked]
    existing = {chunk["id"] for chunk in ranked}
    additions = []
    for sourceId in dict.fromkeys(chunk.get("source_id") for chunk in ranked):
        if any(chunk.get("source_id") == sourceId and _METHOD.search(chunk.get("text") or "")
               for chunk in ranked):
            continue
        method = next((chunk for chunk in indexed if chunk.get("source_id") == sourceId and
                       chunk.get("page") and chunk["id"] not in existing and
                       _METHOD.search(chunk.get("text") or "")), None)
        if method:
            additions.append(completePage(method))
        if len(additions) >= max(1, min(2, limit // 3)):
            break
    return ranked[:limit - len(additions)] + additions
