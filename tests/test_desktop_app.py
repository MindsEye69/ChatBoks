import sys
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


if __name__ == "__main__":
    test_desktop_bridge_bootstraps_a_loopback_client_session()
    test_default_config_path_points_to_the_project_config()
    test_gui_stdio_replaces_missing_console_streams()
