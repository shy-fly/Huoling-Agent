"""Prompt template registry."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=select_autoescape(enabled_extensions=()),
)


def render_prompt(name: str, **kwargs) -> str:
    path = name if name.endswith(".jinja") else f"{name}.jinja"
    return _env.get_template(path).render(**kwargs)
