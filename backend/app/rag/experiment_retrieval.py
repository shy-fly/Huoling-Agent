"""Multi-pass retrieval for experimental evidence, sharing the existing index."""
import re
from collections.abc import Callable

from app.rag.retriever import QUERY_ALIASES, retrieve

_STOP = set("do does did how why what which compare across the a an of in on and is are was were always necessarily can could by to".split())


def retrieveExperimentEvidence(question: str, top_k: int, *, search: Callable = retrieve) -> list[dict]:
    terms = [word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9-]*", question.lower()) if word not in _STOP]
    topic = " ".join(dict.fromkeys(terms)) if len(terms) >= 3 and not re.search(r"[\u3400-\u9fff]", question) else question
    expanded = " ".join(dict.fromkeys(aliases[0] for label, aliases in QUERY_ALIASES.items() if label in question))
    queries = dict.fromkeys(filter(None, (question, expanded, topic, f"{topic} experimental results control",
                             f"{topic} no significant effect inhibition")))
    scores = {}
    chunks = {}
    for query in queries:
        for rank, chunk in enumerate(search(query, top_k=top_k), 1):
            key = chunk["id"]
            chunks[key] = chunk
            scores[key] = scores.get(key, 0.0) + 1 / (20 + rank)
    return sorted(chunks.values(), key=lambda chunk: -scores[chunk["id"]])[:top_k]

