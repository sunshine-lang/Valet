"""用户上传的图片和文件：校验、落盘，以及拼进发给模型的消息。"""

import base64
import html
import io
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agent_api.config import REPO_ROOT, Settings
from agent_api.workspace import Workspace, WorkspaceError

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".css",
    ".sql",
    ".toml",
    ".ini",
}


class AttachmentError(Exception):
    pass


def resolve_upload_dir(settings: Settings) -> Path:
    raw = settings.workspace_root.strip() or settings.upload_dir.strip()
    return Path(raw) if raw else REPO_ROOT


def _safe_name(name: str) -> str:
    base = Path(name).name.replace("\x00", "").strip()
    return base[:200] or "file"


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _decode_text(data: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return None


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        xml = package.read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:p>", "\n")
    return html.unescape(re.sub(r"<[^>]+>", "", xml)).strip()


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _clip(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "\n…（已截断）"


def _looks_textual(name: str, media_type: str) -> bool:
    if media_type.startswith("text/"):
        return True
    return Path(name).suffix.lower() in TEXT_EXTENSIONS


def _unique_name(directory: Path, name: str) -> str:
    candidate = _safe_name(name)
    if not (directory / candidate).exists():
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    number = 2
    while (directory / f"{stem}-{number}{suffix}").exists():
        number += 1
    return f"{stem}-{number}{suffix}"


def save_attachment(
    workspace: Workspace,
    *,
    name: str,
    media_type: str,
    data_base64: str,
    allow_images: bool,
) -> dict[str, Any]:
    """把上传文件放进 /uploads。文档另存一份可 read_file 的文本。"""
    if len(data_base64) > 12_000_000:
        raise AttachmentError("单个文件不能超过 8 MB")
    try:
        data = base64.b64decode(data_base64, validate=True)
    except Exception as e:
        raise AttachmentError(f"{_safe_name(name)} 不是合法的文件内容") from e
    if not data:
        raise AttachmentError(f"{_safe_name(name)} 是空文件")
    if len(data) > MAX_BYTES:
        raise AttachmentError("单个文件不能超过 8 MB")

    declared = (media_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    image_type = sniff_image(data)
    excerpt = ""
    safe_name = _safe_name(name)
    if image_type:
        if not allow_images:
            raise AttachmentError("当前配置未开启图片输入，请到设置 → 模型里打开后再上传图片")
        kind = "image"
        declared = image_type
        if Path(safe_name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            safe_name = f"{Path(safe_name).stem}.{image_type.split('/')[-1].replace('jpeg', 'jpg')}"
    else:
        kind = "file"
        suffix = Path(safe_name).suffix.lower()
        try:
            if suffix == ".docx" or declared.endswith("wordprocessingml.document"):
                excerpt = _docx_text(data)
            elif suffix == ".pdf" or declared == "application/pdf" or data.startswith(b"%PDF"):
                excerpt = _pdf_text(data)
            elif _looks_textual(safe_name, declared):
                excerpt = _decode_text(data) or ""
        except Exception:
            excerpt = ""
        if excerpt:
            kind = "text"
            excerpt = _clip(excerpt)

    uploads = workspace.uploads
    uploads.mkdir(parents=True, exist_ok=True)
    stored_name = _unique_name(uploads, safe_name)
    (uploads / stored_name).write_bytes(data)
    record: dict[str, Any] = {
        "name": stored_name,
        "media_type": declared or "application/octet-stream",
        "size": len(data),
        "kind": kind,
        "path": f"/uploads/{stored_name}",
    }
    if excerpt and not _looks_textual(stored_name, declared):
        text_name = _unique_name(uploads, f"{stored_name}.txt")
        (uploads / text_name).write_text(excerpt, encoding="utf-8")
        record["text_path"] = f"/uploads/{text_name}"
    return record


def public_attachment(item: dict[str, Any], session_id: str) -> dict[str, Any]:
    path = item["path"]
    return {
        "name": item["name"],
        "media_type": item["media_type"],
        "size": item["size"],
        "kind": item["kind"],
        "path": path,
        "text_path": item.get("text_path"),
        "url": f"/api/sessions/{session_id}/files/content?path={quote(path)}",
    }


def user_llm_content(
    content: str,
    attachments: list[dict[str, Any]] | None,
    *,
    include_images: bool,
    workspace_root: Path | None,
    session_id: str | None,
) -> str | list[dict[str, Any]]:
    """正文不塞进提示词，只告诉模型路径。图片在开启图片输入时另附图像段。"""
    notes: list[str] = []
    images: list[dict[str, Any]] = []
    for item in attachments or []:
        if item.get("kind") == "image":
            if include_images and workspace_root is not None and session_id is not None:
                images.append(item)
                notes.append(f"- {item['path']}（图片）")
            else:
                notes.append(f"- {item.get('path') or item.get('name')}（图片未发送）")
            continue
        text_path = item.get("text_path")
        if text_path:
            notes.append(f"- {item['path']}，抽出的正文在 {text_path}")
        elif item.get("kind") == "text":
            notes.append(f"- {item['path']}")
        else:
            notes.append(f"- {item['path']}（正文未能解析）")

    body = content.strip()
    if notes:
        listing = "用户上传了文件。需要内容时用 read_file：\n" + "\n".join(notes)
        body = f"{body}\n\n{listing}" if body else listing
    if not images or workspace_root is None or session_id is None:
        return body

    parts: list[dict[str, Any]] = [{"type": "text", "text": body or "请查看附件。"}]
    workspace = Workspace.open(workspace_root, uuid.UUID(session_id))
    for item in images:
        try:
            located = workspace.locate(str(item["path"]))
            if located.denied or located.outside:
                raise WorkspaceError("不能读取该附件")
            encoded = base64.b64encode(located.path.read_bytes()).decode("ascii")
        except (FileNotFoundError, OSError, WorkspaceError):
            parts.append({"type": "text", "text": f"{item.get('name', '图片')} 已丢失。"})
            continue
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{item['media_type']};base64,{encoded}"},
            }
        )
    return parts


def redact_llm_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """追踪里不保存图片的 base64，避免一步记录膨胀到几兆。"""
    redacted: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            redacted.append(message)
            continue
        copied = dict(message)
        copied["content"] = [
            {"type": "image_url", "image_url": {"url": "[image]"}}
            if isinstance(part, dict) and part.get("type") == "image_url"
            else part
            for part in content
        ]
        redacted.append(copied)
    return redacted
