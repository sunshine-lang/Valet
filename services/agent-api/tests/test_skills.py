import base64
import io
import uuid
import zipfile

from conftest import finished_run, new_session, parse_sse, text

from agent_api.config import get_settings
from agent_api.skills import resolve_skills_dir
from agent_api.tools.base import ToolContext
from agent_api.tools.skills import CreateSkill, ReadSkill


def test_repo_splits_market_and_builtin_skills():
    from agent_api.skills import load_catalog

    skills = {
        skill.name: skill
        for skill in load_catalog(resolve_skills_dir(get_settings()), None)
    }
    assert skills["read-uploads"].source == "builtin"
    assert skills["skill-creator"].source == "builtin"
    assert skills["pdf"].source == "builtin"
    assert skills["docx"].source == "builtin"
    assert skills["pptx"].source == "builtin"
    assert "/uploads" in skills["read-uploads"].body


async def test_read_skill_returns_instructions():
    ctx = ToolContext(
        session_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        skills_dir=resolve_skills_dir(get_settings()),
    )
    out = await ReadSkill().run(ReadSkill.Args(name="write-output"), ctx)
    assert "write_file" in out["instructions"]


async def test_selected_skill_is_in_the_prompt_not_the_user_text(client, fake_llm):
    fake_llm.script(text("看过说明了"))
    sid = await new_session(client)

    run = finished_run(
        await _send(client, sid, {"content": "整理一下", "skills": ["write-output"]})
    )

    assert run["status"] == "completed"
    system = fake_llm.requests[0].messages[0]["content"]
    user = fake_llm.requests[0].messages[-1]["content"]
    assert "read-uploads" in system
    assert "【本轮指定技能】" in system
    assert "write-output" in system
    assert "write_file" in system
    assert user == "整理一下"
    assert "【本轮指定技能】" not in user


async def test_unselected_skill_stays_out_of_the_body(client, fake_llm):
    fake_llm.script(text("好"))
    sid = await new_session(client)

    finished_run(await _send(client, sid, {"content": "你好"}))

    system = fake_llm.requests[0].messages[0]["content"]
    assert "read-uploads" in system
    assert "【本轮指定技能】" not in system
    assert "用 ls 查看" not in system


async def test_skill_page_lists_builtin_skills_and_their_body(client):
    listing = (await client.get("/api/skills")).json()["skills"]
    names = {item["name"]: item for item in listing}
    assert names["read-uploads"]["source"] == "builtin"
    assert names["read-uploads"]["installed"] is False
    assert names["pdf"]["source"] == "builtin"
    detail = (await client.get("/api/skills/read-uploads")).json()
    assert "read_file" in detail["body"]


async def test_builtin_skills_are_available_without_a_personal_install(client, fake_llm):
    fake_llm.script(text("好"))
    sid = await new_session(client)

    finished_run(await _send(client, sid, {"content": "你好"}))

    system = fake_llm.requests[0].messages[0]["content"]
    assert "write-output" in system
    assert "pdf" in system


def _zip(files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode()


_DEMO_SKILL = """---
name: demo-skill
description: 演示导入。用户提到演示技能时使用。
metadata:
  title: 演示技能
---

# 演示

先做第一步。
"""


async def test_zip_import_installs_into_the_user_skill_dir(client):
    resp = await client.post(
        "/api/skills/import",
        json={"filename": "demo.zip", "data_base64": _zip({"demo-skill/SKILL.md": _DEMO_SKILL})},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "demo-skill"
    listed = {item["name"]: item for item in (await client.get("/api/skills")).json()["skills"]}
    assert listed["demo-skill"]["source"] == "user"
    assert listed["demo-skill"]["installed"] is True


async def test_zip_with_parent_path_is_rejected(client):
    payload = _zip(
        {"demo-skill/SKILL.md": _DEMO_SKILL, "demo-skill/../../outside.txt": "nope"}
    )
    resp = await client.post(
        "/api/skills/import", json={"filename": "bad.zip", "data_base64": payload}
    )
    assert resp.status_code == 422


async def test_create_skill_writes_a_user_skill(tmp_path):
    ctx = ToolContext(session_id=uuid.uuid4(), run_id=uuid.uuid4(), user_skills_dir=tmp_path)
    result = await CreateSkill().run(
        CreateSkill.Args(
            name="note-taker",
            title="记笔记",
            description="把对话整理成笔记。用户要记笔记或做成笔记时使用。",
            body="# 记笔记\n\n先写标题，再列要点。",
        ),
        ctx,
    )
    assert result["name"] == "note-taker"
    text = (tmp_path / "note-taker" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: note-taker" in text
    assert "先写标题" in text


async def test_unknown_skill_is_rejected(client):
    sid = await new_session(client)
    resp = await client.post(
        f"/api/sessions/{sid}/messages",
        json={"content": "你好", "skills": ["not-installed"]},
    )
    assert resp.status_code == 422


async def _send(client, sid: str, payload: dict):
    resp = await client.post(f"/api/sessions/{sid}/messages", json=payload)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)
