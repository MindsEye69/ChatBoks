"""Manual OpenAI-compatible runner for optional ChatBoks lane-agent bakeoffs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "lane_bakeoff"
DEFAULT_RESULTS_DIR = ROOT / ".chatboks" / "evals" / "lane-bakeoff"
DEFAULT_MODEL = "glm-5.2"
DEFAULT_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_API_KEY_ENV = "ZAI_API_KEY"
SYSTEM_PROMPT = (
    "You are an optional ChatBoks collaborator lane agent. You are not the Coordinator "
    "and you are not the sole owner of the task. Provide an independent, repo-grounded "
    "view that can help another lane implement, review, or decide. Do not claim to run "
    "tools, edit files, inspect hidden state, browse, commit, or call other agents. "
    "Respect trust boundaries and call out missing evidence. Prefer concise, actionable "
    "analysis over broad commentary. End with exactly one ChatBoks signal: "
    ">>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
)


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
        "[CHATBOKS LANE BAKEOFF]\n"
        f"Fixture: {fixture['id']}\n\n"
        "[TASK]\n"
        f"{fixture['task']}\n\n"
        "[CONTEXT]\n"
        f"{fixture['context']}\n\n"
        "[RESPONSE REQUIREMENTS]\n"
        "- Answer as an optional collaborator lane, not as Coordinator.\n"
        "- Ground the response only in the provided context.\n"
        "- Give concrete risks, decisions, or next actions when useful.\n"
        "- Do not mention this bakeoff fixture or evaluation run.\n"
        "- End with exactly one ChatBoks signal."
    )


def model_slug(model: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", model.strip())
    return slug.strip("-") or "model"


def result_path(output_dir: Path, model: str, now: dt.datetime | None = None) -> Path:
    timestamp = (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / f"{timestamp}-{model_slug(model)}.jsonl"


def chat_completions_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    return f"{stripped}/chat/completions"


def request_payload(
    fixture: dict[str, Any],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None,
) -> tuple[dict[str, Any], str]:
    prompt = build_prompt(fixture)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    return payload, prompt


def extract_chat_output(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts)
    text = first.get("text")
    return text if isinstance(text, str) else ""


def run_fixture(
    fixture: dict[str, Any],
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None,
    timeout: float,
) -> dict[str, Any]:
    payload, prompt = request_payload(
        fixture,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    request = urllib.request.Request(
        chat_completions_url(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    error = ""
    output = ""
    raw = ""
    usage: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        output = extract_chat_output(data)
        usage_value = data.get("usage")
        if isinstance(usage_value, dict):
            usage = usage_value
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        error = f"HTTP {exc.code} {detail[:1000]}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        error = str(exc)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    return {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "fixture_id": fixture["id"],
        "model": model,
        "provider": "openai_compat",
        "base_url": base_url,
        "prompt_chars": len(prompt),
        "output_chars": len(output),
        "elapsed_ms": elapsed_ms,
        "truncated": False,
        "error": error,
        "output": output.strip(),
        "raw_response": raw,
        "usage": usage,
        "expected": expected,
        "notes": "",
    }


def append_result(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run optional lane-agent bakeoff fixtures.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.environ.get("ZAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--fixture", action="append", default=[], help="Fixture id to run. Repeat for multiple ids.")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default=None)
    parser.add_argument("--run", action="store_true", help="Actually call the configured API. Without this, dry run only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_ids = set(args.fixture) if args.fixture else None
    fixtures = load_fixtures(args.fixtures, selected_ids)

    if selected_ids:
        found = {str(fixture["id"]) for fixture in fixtures}
        missing = sorted(selected_ids - found)
        if missing:
            print(f"Missing fixture ids: {', '.join(missing)}")
            return 2
    if not fixtures:
        print(f"No lane bakeoff fixtures found under {args.fixtures}")
        return 2

    print(f"Lane bakeoff model: {args.model}")
    print(f"Base URL: {args.base_url}")
    print(f"API key env: {args.api_key_env}")
    print(f"Fixtures: {len(fixtures)}")
    for fixture in fixtures:
        print(f"- {fixture['id']}: {len(build_prompt(fixture))} prompt chars")

    if not args.run:
        print("Dry run only. Add --run to call the configured API and write JSONL results.")
        return 0

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        print(f"Missing API key environment variable: {args.api_key_env}")
        return 2

    path = result_path(args.output_dir, args.model)
    if path.exists():
        path.unlink()
    records: list[dict[str, Any]] = []
    for index, fixture in enumerate(fixtures, start=1):
        print(f"Running {index}/{len(fixtures)}: {fixture['id']}", flush=True)
        record = run_fixture(
            fixture,
            model=args.model,
            base_url=args.base_url,
            api_key=api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
            timeout=args.timeout,
        )
        records.append(record)
        append_result(path, record)
        status = "error" if record["error"] else "ok"
        print(f"Finished {fixture['id']}: {status}, {record['elapsed_ms']} ms", flush=True)
    failures = [record for record in records if record["error"]]
    print(f"Wrote {len(records)} records to {path}")
    if failures:
        print(f"{len(failures)} fixture call(s) reported errors.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
