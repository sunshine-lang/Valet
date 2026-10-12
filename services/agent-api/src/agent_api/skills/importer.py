"""把用户上传的技能 zip 解压进用户技能目录。"""

import io
import stat
import zipfile
from pathlib import Path

from agent_api.skills.catalog import Skill, _load_one, _split_frontmatter

MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_FILES = 80
MAX_UNCOMPRESSED = 20 * 1024 * 1024


class SkillImportError(Exception):
    """压缩包不是一份合法技能。"""


def import_skill_zip(data: bytes, dest_root: Path) -> Skill:
    if len(data) > MAX_ZIP_BYTES:
        raise SkillImportError("压缩包超过 8 MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise SkillImportError("这不是有效的 zip 压缩包") from error

    infos = [info for info in archive.infolist() if not info.is_dir()]
    if not infos:
        raise SkillImportError("压缩包是空的")
    if len(infos) > MAX_FILES:
        raise SkillImportError(f"文件超过 {MAX_FILES} 个")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED:
        raise SkillImportError("解压后的内容超过 20 MB")

    skill_md = _locate_skill_md(infos)
    prefix = str(Path(skill_md.filename).parent)
    if prefix == ".":
        prefix = ""
    name_hint = Path(skill_md.filename).parent.name if prefix else ""

    dest_root.mkdir(parents=True, exist_ok=True)
    staging = dest_root / ".importing"
    if staging.exists():
        _remove_tree(staging)
    staging.mkdir()
    try:
        for info in infos:
            relative = _safe_relative(info, prefix)
            if relative is None:
                continue
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
        skill_file = staging / "SKILL.md"
        if not skill_file.is_file():
            raise SkillImportError("压缩包里需要有 SKILL.md")
        meta, _body = _split_frontmatter(skill_file.read_text(encoding="utf-8"))
        skill_name = (meta or {}).get("name", "")
        if not skill_name:
            raise SkillImportError("SKILL.md 需要包含 YAML 格式的技能名称和描述")
        if name_hint and name_hint != skill_name and prefix:
            raise SkillImportError(f"目录名 {name_hint} 和技能名 {skill_name} 不一致")
        final = dest_root / skill_name
        if final.exists():
            _remove_tree(final)
        staging.rename(final)
    except Exception:
        if staging.exists():
            _remove_tree(staging)
        raise
    loaded = _load_one(final, "user")
    if loaded is None:
        _remove_tree(final)
        raise SkillImportError("SKILL.md 需要包含 YAML 格式的技能名称和描述，且名称与目录名一致")
    return loaded


def _locate_skill_md(infos: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    matches = [info for info in infos if Path(info.filename).name == "SKILL.md"]
    if not matches:
        raise SkillImportError("压缩包里需要有 SKILL.md")
    return min(matches, key=lambda info: info.filename.count("/"))


def _safe_relative(info: zipfile.ZipInfo, prefix: str) -> Path | None:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise SkillImportError("压缩包里不能包含符号链接")
    name = info.filename.replace("\\", "/").lstrip("/")
    if prefix:
        lead = prefix.rstrip("/") + "/"
        if name == prefix:
            return None
        if not name.startswith(lead):
            return None
        name = name[len(lead) :]
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SkillImportError("压缩包里的路径不合法")
    return path


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    for child in path.iterdir():
        _remove_tree(child)
    path.rmdir()
