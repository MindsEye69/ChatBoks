"""Tests for the native Android shell entry point."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_android_shell_starts_the_responsive_workbench() -> None:
    config = json.loads((ROOT / "mobile_remote" / "capacitor.config.json").read_text(encoding="utf-8"))

    assert config["server"]["appStartPath"] == "/workbench.html"
    assert (ROOT / "mobile_remote" / "www" / "workbench.html").is_file()


def test_compact_workbench_overlays_are_dismissible_and_full_width() -> None:
    www = ROOT / "mobile_remote" / "www"
    html = (www / "workbench.html").read_text(encoding="utf-8")
    script = (www / "workbench.js").read_text(encoding="utf-8")
    styles = (www / "workbench.css").read_text(encoding="utf-8")

    assert 'id="connectionCloseButton"' in html
    assert 'els.connectionCloseButton.addEventListener("click", () => setConnectionPanel(false));' in script
    compact_drawer = styles.split(
        ":root.lumen-workbench body.is-compact-workbench .system-drawer:not(.hidden)", 1
    )[1].split("}", 1)[0]
    assert "width: auto;" in compact_drawer
    assert "max-width: none;" in compact_drawer
    assert ":root.lumen-workbench body.is-compact-workbench .connection-card:not(.hidden)" in styles
    compact_topbar = styles.split(
        ":root.lumen-workbench body.is-compact-workbench .workspace-topbar", 1
    )[1].split("}", 1)[0]
    assert "flex-direction: row;" in compact_topbar


def test_successful_mobile_connection_closes_the_connection_panel() -> None:
    script = (ROOT / "mobile_remote" / "www" / "workbench.js").read_text(encoding="utf-8")

    assert 'showError("Paired and connected.' not in script
    assert 'showError("Connected to the bridge.' not in script
    assert script.count('showError("");\n      setConnectionPanel(false);') == 2


def test_android_build_embeds_its_own_visible_version() -> None:
    mobile = ROOT / "mobile_remote"
    html = (mobile / "www" / "workbench.html").read_text(encoding="utf-8")
    script = (mobile / "www" / "workbench.js").read_text(encoding="utf-8")

    assert html.index("./mobile-version.js") < html.index("./workbench.js")
    assert "PACKAGED_APP_VERSION || data.version" in script
    for build_script in ("build-debug.ps1", "build-release.ps1"):
        build = (mobile / build_script).read_text(encoding="utf-8")
        assert 'CHATBOKS_PACKAGED_VERSION = `"v$($appVersion.Name)`"' in build
