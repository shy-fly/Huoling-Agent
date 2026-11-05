"""Check rendered citation numbers and allow one evidence-preserving repair."""
import re
from collections.abc import Callable


def validateAnswer(answer: str, evidenceCount: int, messages: list[dict],
                   repair: Callable[[list[dict]], str]) -> str:
    def invalid(text: str) -> bool:
        return any(not 1 <= int(number) <= evidenceCount for number in re.findall(r"\[(\d+)\]", text))

    if not invalid(answer):
        return answer
    repaired = repair([*messages, {"role": "assistant", "content": answer}, {
        "role": "user",
        "content": f"引用编号校验失败。系统只有 {evidenceCount} 条参考资料。重新输出完整回答，"
                   "只使用这些资料的序号，不复制原论文参考文献目录序号。二手转述请标记为转引。"
                   "同时逐项核对单位、实验体系和结论边界。无法核对的公式或结论不要补写。",
    }])
    if invalid(repaired):
        raise ValueError("citation validation failed after repair")
    return repaired
