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
        height = getattr(self.console.size, "height", 30)
        leading = "\n" if height >= 28 else ""
        gap = "\n\n" if height >= 32 else "\n"
        return Text(
            f"{leading}{title}{gap}{art}{gap}{centered_status}",
            style="green",
        )

    @staticmethod
    def hypercube_frames() -> list[str]:
        return [Stream.render_glyph_hypercube_frame(i, 16) for i in range(16)]

    @staticmethod
    def render_glyph_hypercube_frame(frame: int, total: int) -> str:
        return Stream.render_ascii_cube_blob_frame(frame, total)

    @staticmethod
    def render_ascii_box_frame(frame: int, total: int) -> str:
        pulse = ".:-=+*#@"[(frame // max(1, total // 8)) % 8]
        lid = "-" if pulse in ".:-" else "="
        rows = [
            "",
            f"              +{lid * 24}+",
            f"             /{' ' * 24}/|",
            f"            /_{'_' * 23}/ |",
            "            |    CHATBOKS RELAY     | |",
            f"            |    shared context {pulse}    | |",
            "            |    agents in sync     | /",
            "            |________________________|/",
            "",
            "                 [ box mode ]",
            "",
            "",
        ]
        return "\n".join(rows)

    @staticmethod
    def render_ascii_cube_blob_frame(frame: int, total: int) -> str:
        width = 46
        height = 18
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

            perspective = 5.4 / (5.4 - z)
            sx = int(width / 2 + x * perspective * 7.4)
            sy = int(height / 2 + y * perspective * 3.0)
            brightness = min(len(chars) - 1, max(0, int((perspective - 0.55) * 8.5)))
            Stream.plot_glyph(buffer, depth, sx, sy, z, chars[brightness], brightness)

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def render_ascii_cube_blob_lit_frame(frame: int, total: int) -> str:
        width = 46
        height = 18
        chars = ".,;:itfLCG08@"
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        depth = [[-999.0 for _ in range(width)] for _ in range(height)]
        theta = (math.tau * frame) / total
        light = (0.18, 0.82, -0.54)

        for x, y, z in Stream.cube_surface_points():
            nx, ny, nz = x, y, z
            x, y = Stream.rotate2(x, y, math.radians(45))
            nx, ny = Stream.rotate2(nx, ny, math.radians(45))
            y, z = Stream.rotate2(y, z, math.radians(35))
            ny, nz = Stream.rotate2(ny, nz, math.radians(35))
            x, z = Stream.rotate2(x, z, theta)
            nx, nz = Stream.rotate2(nx, nz, theta)
            y, z = Stream.rotate2(y, z, theta * 0.35)
            ny, nz = Stream.rotate2(ny, nz, theta * 0.35)

            perspective = 5.4 / (5.4 - z)
            sx = int(width / 2 + x * perspective * 7.4)
            sy = int(height / 2 + y * perspective * 3.0)
            normal_len = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            luminance = max(0.0, (nx * light[0] + ny * light[1] + nz * light[2]) / normal_len)
            shade = luminance * 0.72 + min(0.28, max(0.0, perspective - 0.7) * 0.28)
            brightness = min(len(chars) - 1, max(0, round(shade * (len(chars) - 1))))
            Stream.plot_glyph(buffer, depth, sx, sy, z, chars[brightness], brightness)

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def render_ascii_shaded_cube_frame(frame: int, total: int) -> str:
        width = 60
        height = 18
        chars = ".,-~:;=!*#$@"
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        zbuffer = [[0.0 for _ in range(width)] for _ in range(height)]
        phase = (math.tau * frame) / total
        angle_x = 0.82 + math.sin(phase) * 0.58
        angle_y = 0.56 + math.cos(phase) * 0.46
        cos_x = math.cos(angle_x)
        sin_x = math.sin(angle_x)
        cos_y = math.cos(angle_y)
        sin_y = math.sin(angle_y)
        light_y = 1 / math.sqrt(2)
        light_z = -1 / math.sqrt(2)
        viewer_distance = 5.0
        projection = 18.0
        step = 0.045

        def plot(x: float, y: float, z: float, nx: float, ny: float, nz: float) -> None:
            y1 = y * cos_x - z * sin_x
            z1 = y * sin_x + z * cos_x
            x2 = x * cos_y + z1 * sin_y
            z2 = -x * sin_y + z1 * cos_y

            ny1 = ny * cos_x - nz * sin_x
            nz1 = ny * sin_x + nz * cos_x
            nz2 = -nx * sin_y + nz1 * cos_y

            one_over_z = 1 / (z2 + viewer_distance)
            px = int(width / 2 + 2.0 * projection * one_over_z * x2)
            py = int(height / 2 - projection * 0.72 * one_over_z * y1)
            if not (0 < px < width - 1 and 1 < py < height - 2):
                return
            if one_over_z <= zbuffer[py][px]:
                return

            zbuffer[py][px] = one_over_z
            luminance = ny1 * light_y + nz2 * light_z
            index = max(0, min(len(chars) - 1, round(max(0.0, luminance) * (len(chars) - 1))))
            buffer[py][px] = chars[index]

        u = -1.0
        while u <= 1.0001:
            v = -1.0
            while v <= 1.0001:
                for side in (-1.0, 1.0):
                    plot(side, u, v, side, 0.0, 0.0)
                    plot(u, side, v, 0.0, side, 0.0)
                    plot(u, v, side, 0.0, 0.0, side)
                v += step
            u += step

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def render_ascii_cube_frame(frame: int, total: int) -> str:
        points: list[tuple[float, float, float, float, float, float]] = []
        extent = 1.35
        steps = 44
        values = [(-extent + 2 * extent * i / (steps - 1)) for i in range(steps)]
        for v in values:
            for a in (-extent, extent):
                for b in (-extent, extent):
                    points.extend(
                        [
                            (v, a, b, v, a, b),
                            (a, v, b, a, v, b),
                            (a, b, v, a, b, v),
                        ]
                    )
        angle = (math.tau * frame) / total
        return Stream.render_ascii_points(points, angle * 0.65, angle, width=52, height=18)

    @staticmethod
    def render_projected_edges(
        projected: list[tuple[float, float, float]],
        edges: list[tuple[int, int]],
        *,
        width: int,
        height: int,
    ) -> str:
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        zbuffer = [[0.0 for _ in range(width)] for _ in range(height)]
        min_x = min(point[0] for point in projected)
        max_x = max(point[0] for point in projected)
        min_y = min(point[1] for point in projected)
        max_y = max(point[1] for point in projected)
        span_x = max(max_x - min_x, 0.01)
        span_y = max(max_y - min_y, 0.01)
        padding_x = 4
        padding_y = 1
        drawable_width = max(1, width - padding_x * 2 - 1)
        drawable_height = max(1, height - padding_y * 2 - 1)
        scale = min(drawable_width / span_x, drawable_height / span_y)
        offset_x = padding_x + (drawable_width - span_x * scale) / 2
        offset_y = padding_y + (drawable_height - span_y * scale) / 2
        screen_points: list[tuple[int, int, float]] = []

        for x, y, depth in projected:
            px = round(offset_x + (x - min_x) * scale)
            py = round(offset_y + (max_y - y) * scale)
            screen_points.append((px, py, depth))

        chars = ":-=+*#@"
        for start, end in edges:
            x0, y0, z0 = screen_points[start]
            x1, y1, z1 = screen_points[end]
            brightness = max(0, min(len(chars) - 1, int(((z0 + z1) * 0.5 - 0.12) * 55)))
            Stream.draw_depth_line(buffer, zbuffer, x0, y0, z0, x1, y1, z1, chars[brightness])

        for x, y, depth in screen_points:
            Stream.plot_vertex(buffer, zbuffer, x, y, depth, "+")

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def draw_depth_line(
        buffer: list[list[str]],
        zbuffer: list[list[float]],
        x0: int,
        y0: int,
        z0: float,
        x1: int,
        y1: int,
        z1: float,
        char: str,
    ) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            ratio = step / steps
            x = round(x0 + (x1 - x0) * ratio)
            y = round(y0 + (y1 - y0) * ratio)
            depth = z0 + (z1 - z0) * ratio
            Stream.plot_vertex(buffer, zbuffer, x, y, depth, char)

    @staticmethod
    def plot_vertex(
        buffer: list[list[str]],
        zbuffer: list[list[float]],
        x: int,
        y: int,
        depth: float,
        char: str,
    ) -> None:
        if 0 <= y < len(buffer) and 0 <= x < len(buffer[y]) and depth >= zbuffer[y][x]:
            zbuffer[y][x] = depth
            buffer[y][x] = char

    @staticmethod
    def render_ascii_torus_frame(frame: int, total: int) -> str:
        width = 72
        height = 18
        chars = ".,-~:;=!*#$@"
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        zbuffer = [[0.0 for _ in range(width)] for _ in range(height)]
        a = (math.tau * frame) / total
        b = a * 0.55
        cos_a = math.cos(a)
        sin_a = math.sin(a)
        cos_b = math.cos(b)
        sin_b = math.sin(b)
        radius_minor = 1.0
        radius_major = 2.0
        viewer_distance = 5.0
        x_scale = width * viewer_distance * 3 / (8 * (radius_major + radius_minor))
        y_scale = x_scale * 0.5

        # Torus renderer adapted from the classic donut projection: sweep the
        # tube and ring angles, then Z-buffer lit surface points into ASCII.
        theta = 0.0
        while theta < math.tau:
            cos_theta = math.cos(theta)
            sin_theta = math.sin(theta)
            phi = 0.0
            while phi < math.tau:
                cos_phi = math.cos(phi)
                sin_phi = math.sin(phi)
                circle_x = radius_major + radius_minor * cos_theta
                circle_y = radius_minor * sin_theta

                x = circle_x * (cos_b * cos_phi + sin_a * sin_b * sin_phi) - circle_y * cos_a * sin_b
                y = circle_x * (sin_b * cos_phi - sin_a * cos_b * sin_phi) + circle_y * cos_a * cos_b
                z = viewer_distance + cos_a * circle_x * sin_phi + circle_y * sin_a
                one_over_z = 1 / z

                px = int(width / 2 + x_scale * one_over_z * x)
                py = int(height / 2 - y_scale * one_over_z * y)
                luminance = (
                    cos_phi * cos_theta * sin_b
                    - cos_a * cos_theta * sin_phi
                    - sin_a * sin_theta
                    + cos_b * (cos_a * sin_theta - cos_theta * sin_a * sin_phi)
                )

                if luminance > 0 and 0 < px < width - 1 and 0 < py < height - 1 and one_over_z > zbuffer[py][px]:
                    zbuffer[py][px] = one_over_z
                    index = max(0, min(len(chars) - 1, int(luminance * 8)))
                    buffer[py][px] = chars[index]
                phi += 0.025
            theta += 0.07

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def render_ascii_points(
        points: list[tuple[float, float, float, float, float, float]],
        angle_a: float,
        angle_b: float,
        *,
        width: int,
        height: int,
    ) -> str:
        chars = ".,-~:;=!*#$@"
        buffer = [[" " for _ in range(width)] for _ in range(height)]
        zbuffer = [[0.0 for _ in range(width)] for _ in range(height)]
        distance = 5.4
        scale = min(width * 0.31, height * 0.86)
        light = (0.25, 0.82, -0.52)

        for x, y, z, nx, ny, nz in points:
            y, z = Stream.rotate2(y, z, math.radians(28))
            x, z = Stream.rotate2(x, z, angle_b)
            y, z = Stream.rotate2(y, z, angle_a)
            ny, nz = Stream.rotate2(ny, nz, math.radians(28))
            nx, nz = Stream.rotate2(nx, nz, angle_b)
            ny, nz = Stream.rotate2(ny, nz, angle_a)

            depth_z = distance + z
            if depth_z <= 0:
                continue
            one_over_z = 1 / depth_z
            px = int(width / 2 + scale * one_over_z * x)
            py = int(height / 2 - scale * 0.55 * one_over_z * y)
            if not (0 < px < width - 1 and 0 < py < height - 1):
                continue

            normal_len = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            luminance = 0.36 + max(0.0, (nx * light[0] + ny * light[1] + nz * light[2]) / normal_len) * 0.46
            depth_boost = min(0.55, one_over_z * 1.9)
            brightness = min(1.0, luminance + depth_boost)
            index = max(0, min(len(chars) - 1, int(brightness * (len(chars) - 1))))
            if one_over_z > zbuffer[py][px]:
                zbuffer[py][px] = one_over_z
                buffer[py][px] = chars[index]

        return "\n".join("".join(row).rstrip() for row in buffer)

    @staticmethod
    def rotate2(a: float, b: float, theta: float) -> tuple[float, float]:
        c = math.cos(theta)
        s = math.sin(theta)
        return a * c - b * s, a * s + b * c

    @staticmethod
    def cube_surface_points() -> list[tuple[float, float, float]]:
        points: list[tuple[float, float, float]] = []
        extent = 1.35
        steps = 42
        values = [(-extent + 2 * extent * i / (steps - 1)) for i in range(steps)]

        # Wireframe edges read more clearly in a terminal than dense shaded faces.
        for v in values:
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
