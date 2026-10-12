import uuid

from agent_api.agent.guardrails import Guardrails
from agent_api.tools.base import ToolContext
from agent_api.tools.files import ReadFile, WriteFile
from agent_api.tools.live import WebSearch
from agent_api.workspace import Workspace


def test_secret_file_is_blocked_and_network_asks(tmp_path):
    session_id = uuid.uuid4()
    workspace = Workspace.open(tmp_path, session_id)
    guard = Guardrails(["read_file", "write_file", "web_search"], mode="ask")
    ctx = ToolContext(session_id=session_id, run_id=session_id, workspace=workspace)

    blocked = guard.before_tool_call(WriteFile(), WriteFile.Args(path=".env", content="x"), ctx)
    assert blocked.action == "block"

    asked = guard.before_tool_call(WebSearch(), WebSearch.Args(query="新闻"), ctx)
    assert asked.action == "confirm"
    assert asked.action_class == "network"

    guard.grants.add("network")
    allowed = guard.before_tool_call(WebSearch(), WebSearch.Args(query="新闻"), ctx)
    assert allowed.action == "allow"


def test_assist_allows_network_and_full_allows_outside_files(tmp_path):
    session_id = uuid.uuid4()
    workspace = Workspace.open(tmp_path, session_id)
    ctx = ToolContext(session_id=session_id, run_id=session_id, workspace=workspace)
    assist = Guardrails(["web_search", "read_file"])
    assert assist.before_tool_call(WebSearch(), WebSearch.Args(query="新闻"), ctx).action == "allow"

    full = Guardrails(["read_file", "write_file"], mode="full")
    outside = full.before_tool_call(ReadFile(), ReadFile.Args(path="/etc/passwd"), ctx)
    assert outside.action == "allow"
    assert outside.outside
    secret = full.before_tool_call(WriteFile(), WriteFile.Args(path=".env", content="x"), ctx)
    assert secret.action == "block"


def test_project_file_is_allowed_and_outside_file_asks(tmp_path):
    session_id = uuid.uuid4()
    workspace = Workspace.open(tmp_path, session_id)
    guard = Guardrails(["read_file", "write_file"])
    ctx = ToolContext(session_id=session_id, run_id=session_id, workspace=workspace)

    inside = guard.before_tool_call(WriteFile(), WriteFile.Args(path="notes.md", content="hi"), ctx)
    assert inside.action == "allow"

    outside = guard.before_tool_call(ReadFile(), ReadFile.Args(path="/etc/passwd"), ctx)
    assert outside.action == "confirm"
    assert outside.action_class == "read"
    assert outside.outside
