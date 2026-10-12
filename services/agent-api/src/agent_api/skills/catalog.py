"""从仓库的 skills 目录读取 Agent Skills（SKILL.md）。"""

import re
from dataclasses import dataclass
from pathlib import Path

from agent_api.config import REPO_ROOT, Settings

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Skill:
    name: str
    title: str
    description: str
    body: str
    source: str  # builtin | user


def resolve_skills_dir(settings: Settings) -> Path:
    if settings.skills_dir.strip():
        return Path(settings.skills_dir).expanduser()
    return REPO_ROOT / "skills"


def resolve_user_skills_dir(settings: Settings) -> Path:
    if settings.user_skills_dir.strip():
        return Path(settings.user_skills_dir).expanduser()
    return REPO_ROOT / "data" / "skills"


def load_skills(root: Path | None, *, source: str = "builtin") -> list[Skill]:
    if root is None or not root.is_dir():
        return []
    skills: list[Skill] = []
    for path in sorted(root.iterdir()):
        skill = _load_one(path, source)
        if skill is not None:
            skills.append(skill)
    return skills


def load_catalog(platform: Path | None, user: Path | None) -> list[Skill]:
    """市场、内置、外部安装分开存放。外部技能若与内置同名，不进入目录。"""
    market = load_skills(None if platform is None else platform / "market", source="market")
    builtin = load_skills(None if platform is None else platform / "builtin", source="builtin")
    builtin_names = {skill.name for skill in builtin}
    external = [
        skill
        for skill in load_skills(user, source="user")
        if skill.name not in builtin_names
    ]
    return sorted([*market, *builtin, *external], key=lambda skill: (skill.source, skill.name))


def find_skill(root: Path | None, name: str) -> Skill | None:
    for skill in load_skills(root):
        if skill.name == name:
            return skill
    return None


def find_in_catalog(platform: Path | None, user: Path | None, name: str) -> Skill | None:
    matches = [skill for skill in load_catalog(platform, user) if skill.name == name]
    for skill in matches:
        if skill.source == "user":
            return skill
    return matches[0] if matches else None


def builtin_names(platform: Path | None) -> set[str]:
    root = None if platform is None else platform / "builtin"
    return {skill.name for skill in load_skills(root, source="builtin")}


def _load_one(directory: Path, source: str) -> Skill | None:
    document = directory / "SKILL.md"
    if not directory.is_dir() or not document.is_file():
        return None
    try:
        text = document.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = _split_frontmatter(text)
    if meta is None:
        return None
    name = meta.get("name", "")
    description = meta.get("description", "")
    if not _NAME.fullmatch(name) or len(name) > 64 or name != directory.name:
        return None
    if not description or len(description) > 1024:
        return None
    title = meta.get("title") or name
    return Skill(name=name, title=title, description=description, body=body.strip(), source=source)


def _split_frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    if not text.startswith("---"):
        return None, ""
    end = text.find("\n---", 3)
    if end < 0:
        return None, ""
    return _parse_frontmatter(text[4:end]), text[end + 4 :].lstrip("\n")


def _parse_frontmatter(block: str) -> dict[str, str]:
    """只解析本项目用到的平铺字段，以及 metadata 里的 title。"""
    data: dict[str, str] = {}
    in_metadata = False
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and in_metadata:
            key, _, value = raw.strip().partition(":")
            if key.strip() == "title":
                data["title"] = _unquote(value)
            continue
        in_metadata = False
        key, _, value = raw.partition(":")
        key = key.strip()
        if key == "metadata" and not value.strip():
            in_metadata = True
            continue
        data[key] = _unquote(value)
    return data


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text
