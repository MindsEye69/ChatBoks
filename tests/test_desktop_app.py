import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import desktop_app


class FakeSession:
    def __init__(self, project: str, config_path=None, command_source: str = "remote") -> None:
        self.project = project
        self.config_path = config_path
        self.command_source = command_source

    def close(self) -> None:
        pass


def test_desktop_bridge_bootstraps_a_loopback_client_session():
    original_session = desktop_app.RemoteSession
    desktop_app.RemoteSession = FakeSession
    bridge = None
    try:
        bridge = desktop_app.DesktopBridge("chatboks")
        bootstrap = bridge.bootstrap()
        assert bootstrap["bridgeUrl"].startswith("http://127.0.0.1:")
        assert bootstrap["sessionToken"]
        assert bridge.auth.authorize(bootstrap["sessionToken"])
        assert bridge.session.command_source == "desktop"
        print("PASS: desktop bridge creates a loopback Workbench session")
    finally:
        if bridge is not None:
            bridge.close()
        desktop_app.RemoteSession = original_session


def test_default_config_path_points_to_the_project_config():
    config_path = desktop_app.default_config_path()
    assert config_path.name == "config.yaml"
    assert config_path.exists()
    print("PASS: desktop launcher finds the project config")


def test_default_project_name_uses_renamed_chatboks_entry(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("projects:\n  chatboks-3:\n    path: C:/work\n  another:\n    path: C:/other\n", encoding="utf-8")

    assert desktop_app.default_project_name(config_path) == "chatboks-3"
    print("PASS: desktop launcher resolves a renamed ChatBoks project")


def test_gui_stdio_replaces_missing_console_streams():
    original_stdout = desktop_app.sys.stdout
    original_stderr = desktop_app.sys.stderr
    try:
        desktop_app.sys.stdout = None
        desktop_app.sys.stderr = None
        desktop_app.ensure_gui_stdio()
        assert desktop_app.sys.stdout.isatty() is False
        assert desktop_app.sys.stderr.isatty() is False
    finally:
        desktop_app.sys.stdout = original_stdout
        desktop_app.sys.stderr = original_stderr
    print("PASS: desktop launcher supplies safe GUI output streams")


def test_desktop_main_routes_integration_worker_before_desktop_argparse(monkeypatch):
    calls: list[list[str]] = []

    def fail_parse_args(_argv=None):
        raise AssertionError("desktop argparse should not run for integration workers")

    def fake_worker_main(argv):
        calls.append(argv)
        return 17

    monkeypatch.setattr(desktop_app, "parse_args", fail_parse_args)
    monkeypatch.setattr("integration_execution_runner.main", fake_worker_main)

    result = desktop_app.main(
        [
            desktop_app.INTEGRATION_WORKER_FLAG,
            "--project",
            "chatboks",
            "--execution-id",
            "execution-11111111-2222-3333-4444-555555555555",
        ]
    )

    assert result == 17
    assert calls == [
        [
            "--project",
            "chatboks",
            "--execution-id",
            "execution-11111111-2222-3333-4444-555555555555",
        ]
    ]
    print("PASS: desktop launcher routes integration worker mode")


def test_embedded_workbench_bootstrap_keeps_token_out_of_request_url(tmp_path: Path):
    bootstrap_path = tmp_path / "bootstrap.json"

    desktop_app.write_embedded_bootstrap(
        bootstrap_path,
        "http://127.0.0.1:43123",
        "secret/session token",
    )

    payload = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["url"].startswith("http://127.0.0.1:43123/workbench?embedded=1#")
    assert "secret/session token" not in payload["url"].split("#", 1)[0]
    assert "sessionToken=secret%2Fsession%20token" in payload["url"].split("#", 1)[1]


def test_embedded_workbench_url_rejects_non_loopback_bridge():
    for unsafe in [
        "https://example.com:443",
        "http://localhost",
        "http://user@localhost:43123",
        "http://localhost:43123/other",
        "http://localhost:43123?token=leak",
    ]:
        try:
            desktop_app.embedded_workbench_url(unsafe, "token")
        except ValueError as exc:
            assert "loopback" in str(exc).lower()
        else:
            raise AssertionError(f"unsafe bridge should not be accepted: {unsafe}")


def test_embedded_wait_returns_when_lumen_requests_stop(tmp_path: Path):
    stop_path = tmp_path / "stop"
    stop_path.touch()

    assert desktop_app.wait_for_embed_stop(stop_path, parent_pid=None, poll_seconds=0.001) == "stop"


def test_desktop_cli_accepts_lumen_embed_contract(tmp_path: Path):
    args = desktop_app.parse_args([
        "--embed-bootstrap", str(tmp_path / "bootstrap.json"),
        "--embed-stop", str(tmp_path / "stop"),
        "--parent-pid", "123",
    ])

    assert args.embed_bootstrap == tmp_path / "bootstrap.json"
    assert args.embed_stop == tmp_path / "stop"
    assert args.parent_pid == 123


if __name__ == "__main__":
    test_desktop_bridge_bootstraps_a_loopback_client_session()
    test_default_config_path_points_to_the_project_config()
    test_gui_stdio_replaces_missing_console_streams()
