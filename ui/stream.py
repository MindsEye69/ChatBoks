from __future__ import annotations

import sys
import time
import math
import textwrap
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.rule import Rule
from rich.text import Text

from encoding_utils import configure_utf8_stdio


DEFAULT_COLORS = {
    "claude": "cyan",
    "codex": "green",
    "antigravity": "yellow",
    "you": "white bold",
    "system": "dim white",
}


class Stream:
    def __init__(self, agent_config: dict[str, Any], agents: list[str]) -> None:
        configure_utf8_stdio()
        self.console = Console()
        self.agents = agents
        self.agent_config = agent_config
        self.colors = DEFAULT_COLORS.copy()
        for name, config in agent_config.items():
            if "color" in config:
                self.colors[name] = config["color"]

    def banner(self, project: str) -> None:
        self.console.print(Rule(f"[bold]CHATBOKS - {project.upper()}[/bold]"))

    def ready(self) -> None:
        self.console.print(Rule(style="green"))

    def token_usage(
        self,
        token_counts: dict[str, int],
        session_budget: dict[str, int] | None = None,
    ) -> None:
        self.console.print(f"[dim]{self.build_token_usage_line(token_counts, session_budget)}[/dim]")

    def intro(self, project: str) -> None:
        if not self.console.is_terminal:
            self.banner(project)
            return

        frames = self.hypercube_frames()
        cycles = 4
        total = len(frames) * cycles
        with Live(
            self.render_intro_frame(frames[0], project, 0, len(frames)),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            for index, frame in enumerate(frames * cycles):
                live.update(self.render_intro_frame(frame, project, index + 1, total))
                time.sleep(0.13)
            time.sleep(0.8)

        self.banner(project)
        self.console.print("[dim green]relay bus online - shared context locked[/dim green]")

    def role_call(self, agents: list[str], standby_agents: list[str] | None = None) -> None:
        names = "  ".join(f"[{self.colors.get(agent, 'white')}]{agent.upper()}[/{self.colors.get(agent, 'white')}]" for agent in agents)
        message = f"[dim]role call:[/dim] {names}"
        if standby_agents:
            standby = "  ".join(
                f"[{self.colors.get(agent, 'white')}]{agent.upper()}[/{self.colors.get(agent, 'white')}]"
                for agent in standby_agents
            )
            message += f"  [dim](standby: {standby})[/dim]"
        self.console.print(message)

    def message(self, sender: str, text: str, timestamp: str) -> None:
        color = self.colors.get(sender.lower(), "white")
        label = f"[{color}][{sender.upper()}][/{color}]"
        self.console.print(f"{label} [dim]{timestamp}[/dim]\n{text.strip()}")

    def standby(self, agent_name: str, text: str) -> None:
        color = self.colors.get(agent_name.lower(), "white")
        label = f"[{color}][{agent_name.upper()}][/{color}]"
        self.console.print(f"{label} [dim]{text.strip()}[/dim]")

    def system(self, text: str) -> None:
        self.console.print(f"[dim white][SYSTEM] {text}[/dim white]")

    def help_box(self, commands: list[tuple[str, str]]) -> None:
        width = max(64, min(96, self.console.width - 4))
        title = " CHATBOKS COMMAND DECK "
        top = "+" + title.center(width - 2, "-") + "+"
        rule = "+" + "-" * (width - 2) + "+"
        lines = [top]
        for command, description in commands:
            prefix = f"{command:<24} "
            wrapped = textwrap.wrap(
                description,
                width=max(20, width - len(prefix) - 4),
                break_long_words=False,
            ) or [""]
            for index, chunk in enumerate(wrapped):
                left = prefix if index == 0 else " " * len(prefix)
                body = f"  {left}{chunk}"
                lines.append("|" + body.ljust(width - 2) + "|")
        lines.append(rule)
        self.console.print("\n".join(lines), style="green")

    def help_pin(self, commands: list[str]) -> None:
        command_text = "  ".join(commands)
        self.console.print(f"[dim green]commands:[/dim green] [green]{command_text}[/green]")

    def proposal(self, text: str) -> None:
        self.console.print(Rule(style="yellow"))
        self.console.print(f"[yellow]{text}[/yellow]")
        self.console.print(Rule(style="yellow"))

    def question(self, text: str) -> None:
        self.console.print(f"[bold yellow]>>> {text}[/bold yellow]")

    def escalate(self, text: str) -> None:
        self.console.print(f"[bold red]>>> {text}[/bold red]")

    def prompt(self, label: str = "You > ") -> str:
        self.console.print(f"[white bold]{label}[/white bold]", end="")
        return sys.stdin.readline().rstrip("\r\n")

    def build_token_usage_line(
        self,
        token_counts: dict[str, int],
        session_budget: dict[str, int] | None = None,
    ) -> str:
        segments = ["session tokens:"]
        for agent_name in self.token_usage_agents(token_counts):
            config = self.agent_config.get(agent_name, {})
            used = int(token_counts.get(agent_name, 0))
            limit = int(config.get("token_limit", 0) or 0)
            warning = int(config.get("token_warning", 0) or 0)
            if limit <= 0:
                segments.append(f"{agent_name.upper()} {self.format_token_count(used)}")
                continue
            segments.append(
                f"{agent_name.upper()} {self.render_token_bar(used, limit, warning)} "
                f"{self.format_token_count(used)}/{self.format_token_count(limit)}"
            )
        if session_budget and int(session_budget.get("limit", 0) or 0) > 0:
            used = int(session_budget.get("used", 0) or 0)
            warning = int(session_budget.get("warning", 0) or 0)
            limit = int(session_budget.get("limit", 0) or 0)
            segments.append(
                f"TOTAL {self.render_token_bar(used, limit, warning)} "
                f"{self.format_token_count(used)}/{self.format_token_count(limit)}"
            )
        return "  ".join(segments)

    def token_usage_agents(self, token_counts: dict[str, int]) -> list[str]:
        ordered = list(self.agents)
        for agent_name in token_counts:
            if agent_name not in ordered and agent_name in self.agent_config:
                ordered.append(agent_name)
        return ordered

    @staticmethod
    def render_token_bar(used: int, limit: int, warning: int, width: int = 10) -> str:
        if limit <= 0:
            return "[----------]"
        ratio = max(0.0, min(1.0, used / limit))
        filled = min(width, int(ratio * width))
        if used > 0 and filled == 0:
            filled = 1
        bar = "#" * filled + "-" * (width - filled)
        if used >= limit:
            color = "red"
        elif warning > 0 and used >= warning:
            color = "yellow"
        else:
            color = "green"
        return f"[{color}][{bar}][/{color}]"

    @staticmethod
    def format_token_count(value: int) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        if value >= 10_000:
            return f"{value // 1_000}k"
        if value >= 1_000:
            return f"{value / 1_000:.1f}k"
        return str(value)

    def render_intro_frame(self, frame: str, project: str, index: int, total: int) -> Text:
        title = self.center_block(self.chatboks_wordmark(), self.console.width)
        art = self.center_block(frame, self.console.width)
        status = f"{project.upper()}  relay boot {index:02d}/{total:02d}"
        centered_status = status.center(max(1, min(self.console.width, 96)))
        return Text(
            f"\n\n{title}\n\n\n{art}\n\n\n{centered_status}",
            style="green",
        )

    @staticmethod
    def hypercube_frames() -> list[str]:
        return [Stream.render_glyph_hypercube_frame(i, 16) for i in range(16)]

    @staticmethod
    def render_glyph_hypercube_frame(frame: int, total: int) -> str:
        width = 46
        height = 14
        chars = ".,;:itfLCG08@"
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        depth = [[-999.0 for _ in range(width)] for _ in range(height)]
        theta = (math.tau * frame) / total

        points = Stream.cube_surface_points()

        for x, y, z in points:
            x, y = Stream.rotate2(x, y, math.radians(45))
            y, z = Stream.rotate2(y, z, math.radians(35))
            x, z = Stream.rotate2(x, z, theta)
            y, z = Stream.rotate2(y, z, theta * 0.35)

            perspective3 = 5.4 / (5.4 - z)
            sx = int(width / 2 + x * perspective3 * 7.8)
            sy = int(height / 2 + y * perspective3 * 3.55)
            brightness = min(len(chars) - 1, max(0, int((perspective3 - 0.55) * 8.5)))
            Stream.plot_glyph(buffer, depth, sx, sy, z, chars[brightness], brightness)

        return "\n".join("".join(row).rstrip() for row in buffer).rstrip()

    @staticmethod
    def rotate2(a: float, b: float, theta: float) -> tuple[float, float]:
        c = math.cos(theta)
        s = math.sin(theta)
        return a * c - b * s, a * s + b * c

    @staticmethod
    def cube_surface_points() -> list[tuple[float, float, float]]:
        points: list[tuple[float, float, float]] = []
        extent = 1.35
        steps = 24
        values = [(-extent + 2 * extent * i / (steps - 1)) for i in range(steps)]

        for a in values:
            for b in values:
                for fixed_axis in range(3):
                    for side in (-extent, extent):
                        point = [a, b]
                        if fixed_axis == 0:
                            points.append((side, point[0], point[1]))
                        elif fixed_axis == 1:
                            points.append((point[0], side, point[1]))
                        else:
                            points.append((point[0], point[1], side))

        # Extra-bright edges help the dense face read as a cube, not a blob.
        edge_steps = 36
        edge_values = [(-extent + 2 * extent * i / (edge_steps - 1)) for i in range(edge_steps)]
        for v in edge_values:
            for a in (-extent, extent):
                for b in (-extent, extent):
                    points.extend(
                        [
                            (v, a, b),
                            (a, v, b),
                            (a, b, v),
                        ]
                    )
        return points

    @staticmethod
    def chatboks_wordmark() -> str:
        return r"""
   ██████╗██╗  ██╗ █████╗ ████████╗██████╗  ██████╗ ██╗  ██╗███████╗
  ██╔════╝██║  ██║██╔══██╗╚══██╔══╝██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝
  ██║     ███████║███████║   ██║   ██████╔╝██║   ██║█████╔╝ ███████╗
  ██║     ██╔══██║██╔══██║   ██║   ██╔══██╗██║   ██║██╔═██╗ ╚════██║
  ╚██████╗██║  ██║██║  ██║   ██║   ██████╔╝╚██████╔╝██║  ██╗███████║
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝
        """.strip("\n")

    @staticmethod
    def center_block(block: str, width: int) -> str:
        lines = block.splitlines()
        if not lines:
            return block
        content_width = max(len(line) for line in lines)
        target_width = max(content_width, width)
        return "\n".join(line.center(target_width).rstrip() for line in lines)

    @staticmethod
    def plot_glyph(
        buffer: list[list[str]],
        depth: list[list[float]],
        x: int,
        y: int,
        z: float,
        char: str,
        brightness: int,
    ) -> None:
        height = len(buffer)
        width = len(buffer[0]) if height else 0
        offsets = [(0, 0)]
        if brightness >= 7:
            offsets.extend([(-1, 0), (1, 0)])
        if brightness >= 9:
            offsets.extend([(0, -1), (0, 1)])
        for dx, dy in offsets:
            px = x + dx
            py = y + dy
            if 0 <= px < width and 0 <= py < height and z > depth[py][px]:
                depth[py][px] = z
                buffer[py][px] = char
