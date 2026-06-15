#!/usr/bin/env python3
"""Manual local-model runner for the Coordinator bakeoff fixtures."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from agents.coordinator import CoordinatorAgent


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "coordinator_bakeoff"
DEFAULT_RESULTS_DIR = ROOT / ".chatboks" / "evals" / "coordinator-bakeoff"
DEFAULT_CONFIG = ROOT / "config.yaml"
SYSTEM_PROMPT = (
    "You are Coordinator in ChatBoks. You are local, tool-less, and low-authority. "
    "Answer in concise plain text. Recommend one concrete next action when possible. "
    "Do not claim to run tools, edit files, commit, browse, or inspect hidden state. "
    "Respect privacy and trust boundaries. End with exactly one signal: "
    ">>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def coordinator_config(config: dict[str, Any]) -> dict[str, Any]:
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return {}
    coordinator = agents.get("coordinator")
    return coordinator if isinstance(coordinator, dict) else {}


def load_fixtures(path: Path = DEFAULT_FIXTURE_DIR, selected_ids: set[str] | None = None) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for fixture_path in sorted(path.glob("*.json")):
        if selected_ids and fixture_path.stem not in selected_ids:
            continue
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["_path"] = str(fixture_path)
        fixtures.append(fixture)
    return fixtures


def build_prompt(fixture: dict[str, Any]) -> str:
    return (
        "[COORDINATOR BAKEOFF]\n"
        f"Fixture: {fixture['id']}\n\n"
        "[TASK]\n"
        f"{fixture['task']}\n\n"
        "[CONTEXT]\n"
        f"{fixture['context']}\n\n"
        "[RESPONSE REQUIREMENTS]\n"
        "- Give the best Coordinator response for this situation.\n"
        "- Keep it brief and grounded only in the provided context.\n"
        "- Do not mention this bakeoff fixture or evaluation run.\n"
        "- End with exactly one ChatBoks signal."
    )


def model_slug(model: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", model.strip())
    return slug.strip("-") or "model"


def result_path(output_dir: Path, model: str, now: dt.datetime | None = None) -> Path:
    timestamp = (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / f"{timestamp}-{model_slug(model)}.jsonl"


def ollama_payload(
    fixture: dict[str, Any],
    *,
    model: str,
    temperature: float,
    num_predict: int,
    think: bool,
) -> tuple[dict[str, Any], str]:
    prompt = build_prompt(fixture)
    payload = {
        "model": model,
        "think": think,
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    return payload, prompt


def read_ollama_stream(response: Any) -> tuple[str, str]:
    raw_parts: list[str] = []
    content_parts: list[str] = []
    while True:
        raw_line = response.readline()
        if not raw_line:
            break
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        raw_parts.append(line)
        item = json.loads(line)
        delta = str((item.get("message") or {}).get("content") or item.get("response") or "")
        if delta:
            content_parts.append(delta)
    return "".join(content_parts), "\n".join(raw_parts)


def run_fixture(
    fixture: dict[str, Any],
    *,
    model: str,
    endpoint: str,
    temperature: float,
    num_predict: int,
    think: bool,
    timeout: float,
) -> dict[str, Any]:
    payload, prompt = ollama_payload(
        fixture,
        model=model,
        temperature=temperature,
        num_predict=num_predict,
        think=think,
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    error = ""
    output = ""
    raw = ""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            output, raw = read_ollama_stream(response)
    except urllib.error.HTTPError as exc:
        error = f"HTTP {exc.code} {exc.read().decode('utf-8', errors='replace')}"
    except (urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
        error = str(exc)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    return {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "fixture_id": fixture["id"],
        "model": model,
        "endpoint": endpoint,
        "prompt_chars": len(prompt),
        "output_chars": len(output),
        "elapsed_ms": elapsed_ms,
        "truncated": False,
        "error": error,
        "output": output.strip(),
        "raw_response": raw,
        "expected": expected,
        "notes": "",
    }


def write_results(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Coordinator bakeoff fixtures against an Ollama model.")
    parser.add_argument("--model", help="Ollama model to evaluate. Defaults to config.yaml coordinator model.")
    parser.add_argument("--endpoint", help="Ollama chat endpoint. Defaults to config.yaml coordinator endpoint.")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--fixture", action="append", default=[], help="Fixture id to run. Repeat for multiple ids.")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, help="Override configured Coordinator temperature.")
    parser.add_argument("--num-predict", type=int, help="Override configured Coordinator num_predict.")
    parser.add_argument("--think", action="store_true", help="Request Ollama thinking mode if the model supports it.")
    parser.add_argument("--run", action="store_true", help="Actually call local Ollama. Without this, only prints a dry run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = coordinator_config(load_config())
    model = args.model or str(config.get("model") or "gemma3:4b")
    endpoint = args.endpoint or str(config.get("endpoint") or "http://127.0.0.1:11434/api/chat")
    temperature = args.temperature if args.temperature is not None else float(config.get("temperature", 0.1))
    num_predict = args.num_predict if args.num_predict is not None else int(config.get("num_predict", 512))
    selected_ids = set(args.fixture) if args.fixture else None
    fixtures = load_fixtures(args.fixtures, selected_ids)

    if selected_ids:
        found = {str(fixture["id"]) for fixture in fixtures}
        missing = sorted(selected_ids - found)
        if missing:
            print(f"Missing fixture ids: {', '.join(missing)}")
            return 2
    if not fixtures:
        print(f"No bakeoff fixtures found under {args.fixtures}")
        return 2

    print(f"Coordinator bakeoff model: {model}")
    print(f"Endpoint: {endpoint}")
    print(f"Fixtures: {len(fixtures)}")
    for fixture in fixtures:
        print(f"- {fixture['id']}: {len(build_prompt(fixture))} prompt chars")

    if not args.run:
        print("Dry run only. Add --run to call local Ollama and write JSONL results.")
        return 0
    if not CoordinatorAgent._is_loopback_endpoint(endpoint):
        print(f"Refusing non-loopback endpoint: {endpoint}")
        return 2

    records = [
        run_fixture(
            fixture,
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            num_predict=num_predict,
            think=bool(args.think or config.get("think", False)),
            timeout=args.timeout,
        )
        for fixture in fixtures
    ]
    path = result_path(args.output_dir, model)
    write_results(path, records)
    failures = [record for record in records if record["error"]]
    print(f"Wrote {len(records)} records to {path}")
    if failures:
        print(f"{len(failures)} fixture call(s) reported errors.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
