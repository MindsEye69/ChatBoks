from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from context.summarizer import Summarizer


class ContextBuilder:
    def __init__(self, project_path: Path, config: dict[str, Any]) -> None:
        self.project_path = project_path
        self.config = config
        self.context_config = config.get("context", {})
        self.summarizer = Summarizer()

    def build(self, state: dict[str, Any], chatboks_md: Path) -> str:
        return "\n\n".join(
            [
                self.load_codegraph(),
                self.load_recent_chatboks(chatboks_md),
                self.load_round_context(state),
                self.load_active_task(state),
                self.load_handoff(state),
            ]
        )

    def load_codegraph(self) -> str:
        cg_config = self.context_config.get("codegraph", {})
        if not cg_config.get("enabled", True):
            return "[CODEGRAPH] Disabled by config."

        db_path = self.find_codegraph_db(cg_config)
        if not db_path:
            return "[CODEGRAPH] Not available. Expected SQLite codegraph.db."

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                return self.format_codegraph(conn, cg_config, db_path)
        except sqlite3.Error as exc:
            return f"[CODEGRAPH] SQLite query failed for {db_path}: {exc}"

    def find_codegraph_db(self, cg_config: dict[str, Any]) -> Path | None:
        candidates = cg_config.get(
            "db_candidates",
            ["codegraph.db", ".codegraph/codegraph.db", ".codegraph/index.db"],
        )
        for candidate in candidates:
            path = (self.project_path / candidate).resolve()
            if path.exists():
                return path
        matches = list(self.project_path.glob("**/codegraph.db"))
        return matches[0] if matches else None

    def format_codegraph(
        self,
        conn: sqlite3.Connection,
        cg_config: dict[str, Any],
        db_path: Path,
    ) -> str:
        tables = self.table_names(conn)
        out = [f"[CODEGRAPH] SQLite database: {db_path}"]

        if "files" in tables:
            files = self.query_files(conn, int(cg_config.get("max_files", 200)))
            out.append(f"Files ({len(files)} shown):")
            for row in files:
                out.append(
                    f"  {row.get('path', '?')} [{row.get('language', '?')}] "
                    f"nodes:{row.get('node_count', '?')}"
                )
        else:
            out.append("Files table not found.")

        if "nodes" in tables:
            nodes = self.query_nodes(conn, int(cg_config.get("max_symbols", 250)))
            out.append(f"\nKey symbols ({len(nodes)} shown):")
            for row in nodes:
                sig = row.get("signature") or ""
                suffix = f" - {sig[:80]}" if sig else ""
                out.append(
                    f"  [{row.get('kind', '?')}] {row.get('name', '?')} "
                    f"in {row.get('file_path', row.get('path', '?'))}{suffix}"
                )
        else:
            out.append("\nNodes table not found.")

        if "edges" in tables:
            edges = self.query_edges(conn, int(cg_config.get("max_edges", 150)))
            out.append(f"\nCall/import relationships ({len(edges)} shown):")
            for row in edges:
                out.append(
                    f"  {row.get('source', '?')} --{row.get('kind', '?')}--> "
                    f"{row.get('target', '?')}"
                )
        else:
            out.append("\nEdges table not found.")

        metadata = self.query_project_metadata(conn, tables)
        if metadata:
            out.append("\nProject metadata:")
            out.extend(f"  {line}" for line in metadata)

        return "\n".join(out)

    def query_files(self, conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
        columns = self.columns(conn, "files")
        select = self.select_existing(
            columns,
            {
                "path": ["path", "file_path", "name"],
                "language": ["language", "lang"],
                "node_count": ["node_count", "nodes_count", "symbol_count"],
            },
        )
        return self.fetchall_dicts(conn, "files", select, "path", limit)

    def query_nodes(self, conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
        columns = self.columns(conn, "nodes")
        select = self.select_existing(
            columns,
            {
                "kind": ["kind", "type"],
                "name": ["name", "symbol", "qualified_name"],
                "file_path": ["file_path", "path"],
                "signature": ["signature", "docstring"],
                "start_line": ["start_line", "line"],
            },
        )
        kind_col = select.get("kind")
        where = ""
        params: tuple[Any, ...] = ()
        if kind_col:
            placeholders = ",".join("?" for _ in range(5))
            where = f"WHERE {kind_col} IN ({placeholders})"
            params = ("function", "method", "class", "interface", "type_alias")
        order = "file_path, start_line" if "file_path" in select and "start_line" in select else "name"
        return self.fetchall_dicts(conn, "nodes", select, order, limit, where, params)

    def query_edges(self, conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
        columns = self.columns(conn, "edges")
        select = self.select_existing(
            columns,
            {
                "source": ["source", "source_name", "from_symbol", "src"],
                "target": ["target", "target_name", "to_symbol", "dst"],
                "kind": ["kind", "type"],
            },
        )
        kind_col = select.get("kind")
        where = ""
        params: tuple[Any, ...] = ()
        if kind_col:
            where = f"WHERE {kind_col} IN (?, ?)"
            params = ("calls", "imports")
        return self.fetchall_dicts(conn, "edges", select, "source", limit, where, params)

    def query_project_metadata(self, conn: sqlite3.Connection, tables: set[str]) -> list[str]:
        if "project_metadata" not in tables:
            return []
        columns = self.columns(conn, "project_metadata")
        if not columns:
            return []
        cursor = conn.execute("SELECT * FROM project_metadata LIMIT 20")
        rows = cursor.fetchall()
        lines = []
        for row in rows:
            pairs = [f"{key}={row[key]}" for key in row.keys()]
            lines.append(", ".join(pairs))
        return lines

    def load_recent_chatboks(self, path: Path) -> str:
        lines = int(self.context_config.get("recent_chatboks_lines", 120))
        if not path.exists():
            return "[CHATBOKS] No history yet."
        all_lines = path.read_text(encoding="utf-8").splitlines()
        checkpoint_index = self.last_summary_checkpoint(all_lines)
        if checkpoint_index is not None:
            checkpoint_block = all_lines[checkpoint_index:]
            if len(checkpoint_block) <= lines:
                recent = checkpoint_block
            else:
                recent = [all_lines[checkpoint_index], *all_lines[-lines:]]
        else:
            recent = all_lines[-lines:]
        return "[CHATBOKS RECENT]\n" + "\n".join(recent)

    def load_active_task(self, state: dict[str, Any]) -> str:
        task = state.get("active_task")
        proposal = state.get("proposal")
        if proposal:
            return f"[ACTIVE PROPOSAL]\n{json.dumps(proposal, indent=2)}"
        if task:
            return f"[ACTIVE TASK]\n{task}"
        return "[STATUS] No active task. Awaiting instruction."

    def load_handoff(self, state: dict[str, Any]) -> str:
        if state.get("status") != "handoff":
            return "[HANDOFF] None."
        return "\n".join(
            [
                "[HANDOFF]",
                f"To: {state.get('handoff_to')}",
                f"Reason: {state.get('handoff_reason')}",
                f"Context: {state.get('handoff_context')}",
            ]
        )

    def load_round_context(self, state: dict[str, Any]) -> str:
        return "\n".join(
            [
                "[ROUND CONTEXT]",
                f"Intent: {state.get('round_intent', 'respond')}",
                f"Expected agents: {', '.join(state.get('expected_agents') or []) or 'unknown'}",
                f"Completed agents: {', '.join(state.get('completed_agents') or []) or 'none'}",
                f"Next agent: {state.get('next_agent') or 'unknown'}",
            ]
        )

    def summarize(self, chatboks_md: Path) -> str:
        return self.summarizer.summarize(chatboks_md)

    @staticmethod
    def last_summary_checkpoint(lines: list[str]) -> int | None:
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip().startswith(">>> SUMMARY_CHECKPOINT"):
                return index
        return None

    @staticmethod
    def table_names(conn: sqlite3.Connection) -> set[str]:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def columns(conn: sqlite3.Connection, table: str) -> set[str]:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}

    @staticmethod
    def select_existing(columns: set[str], candidates: dict[str, list[str]]) -> dict[str, str]:
        selected = {}
        for alias, names in candidates.items():
            for name in names:
                if name in columns:
                    selected[alias] = name
                    break
        return selected

    @staticmethod
    def fetchall_dicts(
        conn: sqlite3.Connection,
        table: str,
        select: dict[str, str],
        order_alias: str,
        limit: int,
        where: str = "",
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if not select:
            return []
        projection = ", ".join(f"{column} AS {alias}" for alias, column in select.items())
        order_col = select.get(order_alias) or next(iter(select.values()))
        query = f"SELECT {projection} FROM {table} {where} ORDER BY {order_col} LIMIT ?"
        cursor = conn.execute(query, (*params, limit))
        return [dict(row) for row in cursor.fetchall()]
