"""Tests for terminal intro rendering."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.stream import Stream


def test_hypercube_frames_keep_vertical_padding():
    frames = Stream.hypercube_frames()

    assert len(frames) == 16
    for frame in frames:
        lines = frame.split("\n")
        assert len(lines) == 18
        assert all(len(line) <= 46 for line in lines)
        assert not lines[0].strip()
        assert not lines[-1].strip()
        assert any(line.strip() for line in lines[1:-1])
    print("PASS: intro cube frames keep vertical padding")


def test_torus_frame_keeps_vertical_padding():
    frame = Stream.render_ascii_torus_frame(3, 16)
    lines = frame.split("\n")

    assert len(lines) == 18
    assert all(len(line) <= 72 for line in lines)
    assert not lines[0].strip()
    assert not lines[-1].strip()
    assert any(line.strip() for line in lines[1:-1])
    print("PASS: intro torus frame keeps vertical padding")


def test_agent_output_uses_visible_answer_rules():
    buffer = io.StringIO()
    stream = Stream({"codex": {"color": "green"}}, ["codex"])
    stream.console = Console(file=buffer, force_terminal=False, width=80)

    stream.agent_output_start("codex", "respond")
    stream.agent_output_delta("codex", "hello")
    stream.agent_output_finish("codex")

    output = buffer.getvalue()
    assert "CODEX respond answer" in output
    assert "hello" in output
    print("PASS: streamed agent output has visible answer rules")


def test_token_usage_waits_until_streamed_answer_finishes():
    buffer = io.StringIO()
    stream = Stream({"claude": {"color": "cyan"}}, ["claude"])
    stream.console = Console(file=buffer, force_terminal=False, width=120)

    stream.agent_output_start("claude", "respond")
    stream.agent_output_delta("claude", "alpha ")
    stream.token_usage({"claude": 12}, {"used": 12, "warning": 100, "limit": 200, "agent_count": 1})
    stream.agent_output_delta("claude", "omega")
    mid_output = buffer.getvalue()
    stream.agent_output_finish("claude")

    final_output = buffer.getvalue()
    assert "session tokens:" not in mid_output
    assert "alpha omega" in final_output
    assert final_output.rfind("session tokens:") > final_output.rfind("alpha omega")


if __name__ == "__main__":
    test_hypercube_frames_keep_vertical_padding()
    test_torus_frame_keeps_vertical_padding()
    test_agent_output_uses_visible_answer_rules()
    test_token_usage_waits_until_streamed_answer_finishes()
