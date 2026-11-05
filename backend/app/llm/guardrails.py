"""Guardrails — LLM output must not contradict structured brief."""
import re

FORBIDDEN_PATTERNS = [
    re.compile(r"无需预警|可以忽略|没有问题|一切正常"),
]


def check_narrative(brief: dict, narrative: str) -> tuple[bool, str]:
    if not narrative or len(narrative.strip()) < 5:
        return False, "输出过短"

    level = brief.get("level", "")
    health = brief.get("health")
    fault_types = {f.get("type") for f in brief.get("faults") or []}

    for pat in FORBIDDEN_PATTERNS:
        if pat.search(narrative) and level in ("warning", "critical"):
            return False, "预警状态下出现否定性表述"

    if health is not None:
        nums = re.findall(r"健康度?\s*[:：]?\s*(\d+(?:\.\d+)?)", narrative)
        for n in nums:
            if abs(float(n) - float(health)) > 5:
                return False, f"健康度数值与事实包不一致: {n} vs {health}"

    invented = re.findall(r"(acidification|ammonia|ph_drop|cod_shock|h2s)", narrative)
    for t in invented:
        if t not in fault_types and level == "normal":
            return False, f"编造故障类型: {t}"

    return True, ""
