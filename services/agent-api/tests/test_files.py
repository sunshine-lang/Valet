import base64
import uuid

from conftest import call, finished_run, new_session, parse_sse, run_steps, text

from agent_api.workspace import Workspace, WorkspaceError

PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
)


def test_workspace_marks_escape_as_outside(tmp_path):
    workspace = Workspace.open(tmp_path, uuid.uuid4())
    located = workspace.locate("/uploads/../../../../../../../../etc/passwd")
    assert located.outside
    try:
        workspace.read_text("/etc/passwd")
    except WorkspaceError as error:
        assert "项目目录之外" in str(error)
    else:
        raise AssertionError("未授权不能读项目外文件")


def test_write_requires_read_and_stays_in_zone(tmp_path):
    workspace = Workspace.open(tmp_path, uuid.uuid4())
    (workspace.outputs / "note.md").write_text("hello", encoding="utf-8")
    try:
        workspace.write_text("/outputs/note.md", "again")
    except WorkspaceError as e:
        assert "read_file" in str(e)
    else:
        raise AssertionError("未读不能覆盖")
    created = workspace.write_text("/outputs/fresh.md", "hello")
    assert created["path"] == "/outputs/fresh.md"
    try:
        workspace.write_text("/uploads/nope.txt", "x")
    except WorkspaceError as e:
        assert "只读" in str(e)
    else:
        raise AssertionError("不能写上传目录")
    try:
        workspace.write_text(".env", "KEY=1")
    except WorkspaceError as e:
        assert "不能读写" in str(e)
    else:
        raise AssertionError("不能写密钥文件")
    created_root = workspace.write_text("notes.md", "项目里的文件")
    assert created_root["path"] == "/notes.md"
    workspace.read_text("/outputs/note.md")
    replaced = workspace.replace_text("/outputs/note.md", "hello", "world")
    assert replaced["path"] == "/outputs/note.md"
    assert workspace.read_text("/outputs/note.md")["content"] == "world"


async def test_uploaded_text_is_read_with_tool(client, fake_llm):
    sid = await new_session(client)
    payload = base64.b64encode("你好，文件".encode()).decode()

    def first(request):
        user = request.messages[-1]["content"]
        assert "/uploads/note.txt" in user
        assert "你好，文件" not in user
        return call("read_file", {"path": "/uploads/note.txt"})

    fake_llm.script(first, text("读到了"))
    resp = await client.post(
        f"/api/sessions/{sid}/messages",
        json={
            "content": "看看这个文件",
            "attachments": [
                {"name": "note.txt", "media_type": "text/plain", "data_base64": payload}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    run = finished_run(parse_sse(resp.text))
    steps = await run_steps(client, run["id"])
    tool = next(step for step in steps if step["type"] == "tool_call")
    assert tool["output"]["content"] == "你好，文件"
    listed = (await client.get(f"/api/sessions/{sid}/files")).json()["files"]
    assert any(item["path"] == "/uploads/note.txt" for item in listed)
    downloaded = await client.get(
        f"/api/sessions/{sid}/files/content", params={"path": "/uploads/note.txt"}
    )
    assert downloaded.status_code == 200
    assert downloaded.content == "你好，文件".encode()


async def test_image_requires_image_input(client):
    sid = await new_session(client)
    resp = await client.post(
        f"/api/sessions/{sid}/messages",
        json={
            "content": "看图",
            "attachments": [{"name": "dot.png", "media_type": "image/png", "data_base64": PNG}],
        },
    )
    assert resp.status_code == 422
    assert "图片输入" in resp.json()["detail"]


async def test_image_is_sent_when_enabled(client, fake_llm):
    config = (await client.get("/api/agent-config")).json()["config"]
    config["model"] = "qwen3.8-max-0902"
    saved = await client.put("/api/agent-config", json=config)
    assert saved.status_code == 200
    assert saved.json()["config"]["image_input"] is True
    sid = await new_session(client)
    fake_llm.script(text("看到一张图"))
    resp = await client.post(
        f"/api/sessions/{sid}/messages",
        json={
            "content": "这是什么",
            "attachments": [{"name": "dot.png", "media_type": "image/png", "data_base64": PNG}],
        },
    )
    assert resp.status_code == 200, resp.text
    user = fake_llm.requests[0].messages[-1]["content"]
    assert isinstance(user, list)
    assert user[-1]["type"] == "image_url"
    assert user[-1]["image_url"]["url"].startswith("data:image/png;base64,")
    run = finished_run(parse_sse(resp.text))
    steps = await run_steps(client, run["id"])
    recorded = str(steps[0]["input"])
    assert "[image]" in recorded
    assert "iVBORw0KGgo" not in recorded
