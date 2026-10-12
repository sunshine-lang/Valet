"""项目根目录是文件工具的工作区。上传和交付物放在项目内的会话子目录。"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

ZONES = ("uploads", "workspace", "outputs")
MAX_READ_BYTES = 100_000
MAX_WRITE_CHARS = 100_000
SECRET_NAMES = frozenset({".git", ".env", "credentials.json", "id_rsa", "id_ed25519"})
SECRET_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})
SKIP_LISTING = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "dist", ".pnpm-store"}
)

allow_outside: ContextVar[bool] = ContextVar("valet_allow_outside", default=False)


class WorkspaceError(Exception):
    pass


@dataclass(frozen=True)
class Location:
    virtual: str
    path: Path
    outside: bool = False
    denied: str = ""
    alias: str = ""


def _secret(name: str) -> bool:
    lowered = name.lower()
    if lowered in SECRET_NAMES or lowered.startswith(".env"):
        return True
    return Path(lowered).suffix in SECRET_SUFFIXES


class Workspace:
    def __init__(self, root: Path, session_id: uuid.UUID | None = None) -> None:
        self.root = root.resolve()
        self.session_id = session_id
        self.read_paths: set[str] = set()
        if session_id is not None:
            self.uploads.mkdir(parents=True, exist_ok=True)
            self.outputs.mkdir(parents=True, exist_ok=True)

    @classmethod
    def open(cls, root: Path, session_id: uuid.UUID) -> "Workspace":
        return cls(root, session_id)

    @property
    def uploads(self) -> Path:
        return self.root / ".valet" / "sessions" / str(self.session_id) / "uploads"

    @property
    def outputs(self) -> Path:
        return self.root / ".valet" / "sessions" / str(self.session_id) / "outputs"

    def locate(self, virtual: str) -> Location:
        raw = virtual.strip().replace("\\", "/")
        if raw in ("", "/"):
            return Location("/", self.root)
        root = self.root
        root_text = root.as_posix()
        if raw == root_text or raw.startswith(root_text + "/"):
            relative = raw[len(root_text) :].strip("/")
            return self._inside(relative.split("/") if relative else [], raw)
        if self._system_absolute(raw):
            target = Path(raw)
            if any(_secret(part) for part in target.parts):
                return Location(raw, target, denied="密钥、.env 和 .git 不能读写")
            return Location(raw, target, outside=True)
        parts = self._normalize(raw)
        if parts is None:
            return Location(raw or "/", Path(raw), outside=True)
        if parts and parts[0] in ("uploads", "outputs") and self.session_id is not None:
            base = self.uploads if parts[0] == "uploads" else self.outputs
            return self._join(base, parts[1:], "/" + "/".join(parts), alias=parts[0])
        if parts and parts[0] == "workspace":
            parts = parts[1:]
        return self._inside(parts, "/" + "/".join(parts) if parts else "/")

    def list_dir(self, virtual: str = "/") -> list[dict[str, object]]:
        located = self._checked(virtual, write=False)
        path = located.path
        if not path.exists():
            raise WorkspaceError(f"目录不存在：{located.virtual}")
        if not path.is_dir():
            raise WorkspaceError(f"不是目录：{located.virtual}")
        rows: list[dict[str, object]] = []
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            if child.is_symlink() or child.name in SKIP_LISTING or _secret(child.name):
                continue
            kind = "dir" if child.is_dir() else "file"
            shown = self._child_virtual(located, child.name)
            rows.append(
                {
                    "name": child.name,
                    "path": shown,
                    "kind": kind,
                    "size": child.stat().st_size if kind == "file" else 0,
                }
            )
        return rows

    def read_text(self, virtual: str) -> dict[str, object]:
        located = self._checked(virtual, write=False)
        path = located.path
        if not path.is_file():
            raise WorkspaceError(f"文件不存在：{located.virtual}")
        size = path.stat().st_size
        data = path.read_bytes()[: MAX_READ_BYTES + 1]
        truncated = len(data) > MAX_READ_BYTES
        if truncated:
            data = data[:MAX_READ_BYTES]
        text = _decode(data)
        if text is None:
            raise WorkspaceError(f"{located.virtual} 不是文本文件，不能用 read_file 读取")
        self.read_paths.add(located.virtual)
        return {"path": located.virtual, "content": text, "truncated": truncated, "size": size}

    def write_text(self, virtual: str, content: str) -> dict[str, object]:
        if len(content) > MAX_WRITE_CHARS:
            raise WorkspaceError(f"内容超过 {MAX_WRITE_CHARS} 个字符")
        located = self._checked(virtual, write=True)
        if located.alias == "uploads":
            raise WorkspaceError("上传目录只读")
        path = located.path
        if path.exists() and located.virtual not in self.read_paths:
            raise WorkspaceError("修改已有文件前请先 read_file")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.read_paths.add(located.virtual)
        return {"path": located.virtual, "bytes": path.stat().st_size}

    def replace_text(self, virtual: str, old: str, new: str) -> dict[str, object]:
        if not old:
            raise WorkspaceError("要替换的原文不能为空")
        located = self._checked(virtual, write=True)
        if located.alias == "uploads":
            raise WorkspaceError("上传目录只读")
        if located.virtual not in self.read_paths:
            raise WorkspaceError("修改已有文件前请先 read_file")
        path = located.path
        if not path.is_file():
            raise WorkspaceError(f"文件不存在：{located.virtual}")
        text = _decode(path.read_bytes())
        if text is None:
            raise WorkspaceError(f"{located.virtual} 不是文本文件")
        found = text.count(old)
        if found == 0:
            raise WorkspaceError("没有找到要替换的原文")
        if found > 1:
            raise WorkspaceError("原文出现了多次，请带上更多上下文，只匹配一处")
        updated = text.replace(old, new, 1)
        if len(updated) > MAX_WRITE_CHARS:
            raise WorkspaceError(f"替换后的内容超过 {MAX_WRITE_CHARS} 个字符")
        path.write_text(updated, encoding="utf-8")
        return {"path": located.virtual, "bytes": path.stat().st_size}

    def _checked(self, virtual: str, *, write: bool) -> Location:
        located = self.locate(virtual)
        if located.denied:
            raise WorkspaceError(located.denied)
        if located.outside and not allow_outside.get():
            verb = "写入" if write else "读取"
            raise WorkspaceError(f"路径在项目目录之外，需要授权后才能{verb}")
        if write and located.virtual in ("/", ""):
            raise WorkspaceError("请指定文件名")
        return located

    def _system_absolute(self, raw: str) -> bool:
        if not raw.startswith("/"):
            return False
        root = self.root
        if raw == root.as_posix() or raw.startswith(root.as_posix() + "/"):
            return False
        parts = [part for part in raw.split("/") if part]
        if parts and parts[0] in ("uploads", "outputs", "workspace"):
            return False
        path = Path(raw)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved == root or root in resolved.parents:
            return False
        return path.exists() or resolved.exists()

    def _normalize(self, raw: str) -> list[str] | None:
        parts: list[str] = []
        for part in raw.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    return None
                parts.pop()
                continue
            parts.append(part)
        return parts

    def _inside(self, parts: list[str], virtual: str) -> Location:
        if any(_secret(part) for part in parts):
            return Location(virtual, self.root, denied="密钥、.env 和 .git 不能读写")
        return self._join(self.root, parts, virtual or "/")

    def _join(self, base: Path, parts: list[str], virtual: str, alias: str = "") -> Location:
        if any(_secret(part) for part in parts):
            return Location(virtual, base, denied="密钥、.env 和 .git 不能读写", alias=alias)
        current = base
        for part in parts:
            if len(part) > 200:
                raise WorkspaceError("文件名过长")
            current = current / part
            if current.is_symlink():
                raise WorkspaceError("不能使用符号链接")
        try:
            target = current.resolve()
        except OSError:
            target = current
        root = self.root
        outside = target != root and root not in target.parents
        return Location(virtual, target, outside=outside, alias=alias)

    def _child_virtual(self, parent: Location, name: str) -> str:
        if parent.virtual in ("", "/"):
            return name
        return f"{parent.virtual.rstrip('/')}/{name}"


def _decode(data: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None
