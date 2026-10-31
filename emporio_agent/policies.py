"""Manual sections, addressable by number. See ADR-002 for why there is no vector index."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_FILE = Path(__file__).parent / "knowledge" / "policies.md"
HEADING = re.compile(r"^#{2,3} (\d+(?:\.\d+)?) (.+)$")


@dataclass(frozen=True)
class PolicySection:
    id: str
    title: str
    body: str


class PolicyBook:
    def __init__(self, path: Path = KNOWLEDGE_FILE) -> None:
        self.sections: dict[str, PolicySection] = {}
        current: tuple[str, str] | None = None
        buffer: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = HEADING.match(line)
            if match:
                self._close(current, buffer)
                current, buffer = (match.group(1), match.group(2)), []
            elif current:
                buffer.append(line)
        self._close(current, buffer)

    def _close(self, current: tuple[str, str] | None, buffer: list[str]) -> None:
        if current:
            self.sections[current[0]] = PolicySection(current[0], current[1], "\n".join(buffer).strip())

    def table_of_contents(self) -> str:
        return "\n".join(f"{s.id} {s.title}" for s in self.sections.values())

    def get(self, section_ids: list[str]) -> dict:
        """Return requested sections in full. A top-level id includes its subsections."""
        found: dict[str, PolicySection] = {}
        unknown: list[str] = []
        for requested in section_ids:
            requested = str(requested).strip().rstrip(".")
            matches = [s for s in self.sections.values() if s.id == requested or s.id.startswith(f"{requested}.")]
            if matches:
                found.update({s.id: s for s in matches})
            else:
                unknown.append(requested)
        result = {"secoes": [{"secao": s.id, "titulo": s.title, "texto": s.body} for s in found.values()]}
        if unknown:
            result["secoes_inexistentes"] = unknown
        return result
