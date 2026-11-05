"""Conservative stance mapping for reviewed original-study endpoints."""
import re


def reviewProfile(claim: str) -> tuple[str, str] | None:
    if "微塑料" in claim or "microplastic" in claim.lower():
        return ("microplastic", "microplastic anaerobic digestion methane production")
    if "驯化" in claim and "氨" in claim:
        return ("acclimation", "ammonia acclimation adaptation methanogenesis")
    if re.search(r"\bTAN\b", claim, re.I) and ("甲烷产量下降" in claim or "抑制产甲烷" in claim):
        return ("tan", "Yang ammonia methane production TAN inhibition")
    return None


def classifyPrimaryEndpoints(profile: str, records: list[dict]) -> list[dict]:
    """Classify only endpoints whose original-study interpretation is established."""
    if profile != "tan":
        return []
    evidence = []
    for record in records:
        if record["metric"] != "TAN" or record["endpoint"] != "甲烷产量 IC₅₀":
            continue
        qualifier = record["qualifier"]
        if qualifier == "lower_bound":
            classification = "support"
            reason = "原始实验报告中温组甲烷产量降低达到 IC₅₀。支持方向，仅适用于该实验组。"
        elif qualifier == "not_reached":
            classification = "conditional"
            reason = "高温组在实验范围内未达到 IC₅₀。仍可能存在低于 50% 的下降。"
        else:
            continue
        evidence.append({**record, "classification": classification, "reason": reason})
    return evidence

