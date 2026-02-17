import ast
import re
from pathlib import Path
from typing import Any


ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^#\n]*)(\s*#.*)?(\r?\n?)$")


class OptionsAdapter:
    def __init__(self, options_path: Path):
        self.options_path = options_path

    def load(self) -> dict[str, Any]:
        if not self.options_path.exists():
            raise FileNotFoundError(f"options.py not found: {self.options_path}")

        payload: dict[str, Any] = {}
        for line in self.options_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            left, right = line.split("=", 1)
            name = left.strip()
            if not name.isidentifier():
                continue
            value_expr = right.split("#", 1)[0].strip()
            try:
                payload[name] = ast.literal_eval(value_expr)
            except Exception:
                continue
        return payload

    def update(self, updates: dict[str, Any]) -> None:
        if not self.options_path.exists():
            raise FileNotFoundError(f"options.py not found: {self.options_path}")

        lines = self.options_path.read_text(encoding="utf-8").splitlines(keepends=True)
        remaining = dict(updates)
        out_lines: list[str] = []

        for line in lines:
            match = ASSIGNMENT_RE.match(line)
            if not match:
                out_lines.append(line)
                continue

            indent, name, _value, comment, newline = match.groups()
            if name not in remaining:
                out_lines.append(line)
                continue

            serialized = self._serialize(remaining.pop(name))
            newline_text = newline if newline else "\n"
            out_lines.append(f"{indent}{name} = {serialized}{comment or ''}{newline_text}")

        for name, value in remaining.items():
            out_lines.append(f"{name} = {self._serialize(value)}\n")

        self.options_path.write_text("".join(out_lines), encoding="utf-8")

    def _serialize(self, value: Any) -> str:
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return repr(value)
        return repr(value)
