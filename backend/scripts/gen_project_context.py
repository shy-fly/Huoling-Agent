#!/usr/bin/env python3
"""生成 fireFairy 项目交接上下文文件（agent 文件）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.project_context import AGENT_CONTEXT_FILE, build_project_context, persist_project_context


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 fireFairy 项目上下文文件")
    parser.add_argument(
        "--print",
        action="store_true",
        help="仅输出上下文，不落盘",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=AGENT_CONTEXT_FILE,
        help="自定义输出路径（默认 project_agent_context.json）",
    )
    args = parser.parse_args()

    if args.print:
        payload = build_project_context()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    output_path = args.out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    persist_project_context(output_path)
    print(f"已生成: {output_path}")


if __name__ == "__main__":
    main()
