from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import doctor


def test_find_ollama_command_prefers_existing_explicit_path():
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "ollama.exe"
        exe.write_text("", encoding="utf-8")

        assert doctor.find_ollama_command(str(exe)) == str(exe)


def test_find_ollama_command_uses_localappdata_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        local_appdata = Path(tmp)
        exe = local_appdata / "Programs" / "Ollama" / "ollama.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}, clear=False):
            with patch("doctor.find_command", return_value=None):
                assert doctor.find_ollama_command("ollama") == str(exe)


def test_check_py_launcher_warns_when_launcher_reports_no_installs():
    completed = doctor.subprocess.CompletedProcess(["py", "-0p"], 0, "No installed Pythons found!\n", "")
    with patch("doctor.shutil.which", return_value="C:\\WINDOWS\\py.exe"):
        with patch("doctor.run_capture", return_value=completed):
            ok, message = doctor.check_py_launcher()

    assert not ok
    assert "No installed Pythons found!" in message


def test_check_py_launcher_accepts_real_listing():
    completed = doctor.subprocess.CompletedProcess(["py", "-0p"], 0, " -V:3.14 * C:\\Python314\\python.exe\n", "")
    with patch("doctor.shutil.which", return_value="C:\\WINDOWS\\py.exe"):
        with patch("doctor.run_capture", return_value=completed):
            ok, message = doctor.check_py_launcher()

    assert ok
    assert "C:\\Python314\\python.exe" in message


def test_smoke_agent_zero_includes_think_flag():
    payload = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"message":{"content":"CHATBOKS_OK"}}'

    def fake_urlopen(request, timeout):
        del timeout
        payload.update(doctor.json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    with patch("doctor.urllib.request.urlopen", side_effect=fake_urlopen):
        assert doctor.smoke_agent_zero("http://127.0.0.1:11434/api/chat", "gemma3:4b", think=False)

    assert payload["model"] == "gemma3:4b"
    assert payload["think"] is False


def test_check_project_includes_direct_agents():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".chatboks").mkdir()
        (root / ".chatboks" / "state.json").write_text("{}", encoding="utf-8")
        (root / ".git").mkdir()

        seen = []

        def fake_check_agent(project_path, agent_name, agent_config, smoke_agents):
            del project_path, agent_config, smoke_agents
            seen.append(agent_name)
            return True

        with patch("doctor.check_agent", side_effect=fake_check_agent):
            with patch("doctor.find_codegraph_db", return_value=None):
                with patch("doctor.check_project_hook", return_value=True):
                    ok = doctor.check_project(
                        "chatboks",
                        {
                            "path": str(root),
                            "agents": ["claude", "codex"],
                            "direct_agents": ["agent_zero"],
                        },
                        {"agents": {"claude": {}, "codex": {}, "agent_zero": {}}},
                        smoke_agents=False,
                    )

    assert ok
    assert seen == ["claude", "codex", "agent_zero"]


def test_parse_graphify_built_commit_reads_report():
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "GRAPH_REPORT.md"
        report.write_text("## Graph Freshness\n- Built from commit: `abc12345`\n", encoding="utf-8")

        assert doctor.parse_graphify_built_commit(report) == "abc12345"


def test_commits_match_accepts_short_or_full_prefixes():
    assert doctor.commits_match("abc12345", "abc12345deadbeef")
    assert doctor.commits_match("abc12345deadbeef", "abc12345")
    assert not doctor.commits_match("abc12345", "def67890")


def test_check_graphify_reports_stale_source_commit(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        (graph_dir / "GRAPH_REPORT.md").write_text(
            "- Built from commit: `abc12345`\n",
            encoding="utf-8",
        )

        with patch("doctor.find_command", return_value="graphify"):
            with patch("doctor.latest_source_commit", return_value="def67890"):
                with patch("doctor.source_worktree_dirty", return_value=False):
                    doctor.check_graphify(root)

    output = capsys.readouterr().out
    assert "WARN graphify freshness" in output
    assert "abc12345" in output
    assert "def67890" in output


def test_check_graphify_accepts_latest_source_commit(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        (graph_dir / "GRAPH_REPORT.md").write_text(
            "- Built from commit: `abc12345`\n",
            encoding="utf-8",
        )

        with patch("doctor.find_command", return_value="graphify"):
            with patch("doctor.latest_source_commit", return_value="abc12345deadbeef"):
                with patch("doctor.source_worktree_dirty", return_value=False):
                    doctor.check_graphify(root)

    output = capsys.readouterr().out
    assert "OK   graphify freshness" in output


def test_check_graphify_warns_when_source_worktree_dirty(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        (graph_dir / "GRAPH_REPORT.md").write_text(
            "- Built from commit: `abc12345`\n",
            encoding="utf-8",
        )

        with patch("doctor.find_command", return_value="graphify"):
            with patch("doctor.latest_source_commit", return_value="abc12345deadbeef"):
                with patch("doctor.source_worktree_dirty", return_value=True):
                    doctor.check_graphify(root)

    output = capsys.readouterr().out
    assert "uncommitted non-graphify changes" in output
