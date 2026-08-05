"""Tests for the request-scoped execution registry foundation."""

from __future__ import annotations

import sqlite3

import pytest

from integration_executions import (
    IntegrationExecutionError,
    IntegrationExecutionRegistry,
    default_execution_registry_path,
)


def test_execution_registry_reserves_one_durable_identity_per_request(tmp_path):
    database = default_execution_registry_path(tmp_path)
    registry = IntegrationExecutionRegistry(database)

    reserved = registry.reserve("request-execution-001")

    assert reserved.execution_id.startswith("execution-")
    assert reserved.request_id == "request-execution-001"
    assert reserved.status == "waiting_for_runner"
    assert registry.reserve("request-execution-001") == reserved
    assert registry.get_for_request("request-execution-001") == reserved

    reopened = IntegrationExecutionRegistry(database)
    assert reopened.get(reserved.execution_id) == reserved
    assert [event.event_type for event in reopened.events(reserved.execution_id)] == ["execution_reserved"]


def test_execution_registry_enforces_isolated_runner_state_transitions(tmp_path):
    registry = IntegrationExecutionRegistry(tmp_path / "integration-executions.sqlite3")
    reserved = registry.reserve("request-execution-002")
    attached = registry.attach_runner(reserved.execution_id, 4242)

    with pytest.raises(IntegrationExecutionError, match="state transition"):
        registry.pause(reserved.execution_id)

    started = registry.start(reserved.execution_id, "session-isolated-002")
    paused = registry.pause(started.execution_id)
    resumed = registry.resume(paused.execution_id)
    cancellation_requested = registry.request_cancellation(resumed.execution_id)
    cancelled = registry.finish(cancellation_requested.execution_id, "cancelled")

    assert started.status == "running"
    assert attached.runner_pid == 4242
    assert started.runner_pid == 4242
    assert started.session_id == "session-isolated-002"
    assert paused.status == "paused"
    assert resumed.status == "running"
    assert cancellation_requested.status == "cancellation_requested"
    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None
    assert [event.event_type for event in registry.events(cancelled.execution_id)] == [
        "execution_reserved",
        "runner_attached",
        "execution_started",
        "execution_paused",
        "execution_resumed",
        "execution_cancellation_requested",
        "execution_cancelled",
    ]


def test_execution_registry_records_worker_launch_failure_without_starting(tmp_path):
    registry = IntegrationExecutionRegistry(tmp_path / "integration-executions.sqlite3")
    reserved = registry.reserve("request-execution-launch-failure")

    failed = registry.mark_runner_failed_to_start(reserved.execution_id, "runner_launch_failed")

    assert failed.status == "failed"
    assert failed.started_at is None
    assert failed.error_code == "runner_launch_failed"
    assert [event.event_type for event in registry.events(failed.execution_id)] == [
        "execution_reserved",
        "runner_failed_to_start",
    ]


def test_execution_registry_migrates_v1_database_with_runner_pid(tmp_path):
    database = tmp_path / "integration-executions.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE integration_executions (
                execution_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                session_id TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_code TEXT
            );
            CREATE TABLE integration_execution_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL
            );
            PRAGMA user_version = 1;
            """
        )

    registry = IntegrationExecutionRegistry(database)

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(integration_executions)")}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    assert "runner_pid" in columns
    assert registry.reserve("request-execution-migration-001").runner_pid is None


def test_execution_registry_marks_interrupted_work_terminal_until_explicit_recovery(tmp_path):
    registry = IntegrationExecutionRegistry(tmp_path / "integration-executions.sqlite3")
    execution = registry.start(registry.reserve("request-execution-003").execution_id, "session-isolated-003")

    interrupted = registry.mark_interrupted(execution.execution_id)

    assert interrupted.status == "interrupted"
    assert interrupted.completed_at is not None
    with pytest.raises(IntegrationExecutionError, match="state transition"):
        registry.resume(interrupted.execution_id)


def test_execution_registry_cancels_unstarted_work_without_starting_a_runner(tmp_path):
    registry = IntegrationExecutionRegistry(tmp_path / "integration-executions.sqlite3")
    reserved = registry.reserve("request-execution-004")

    cancelled = registry.request_cancellation(reserved.execution_id)

    assert cancelled.status == "cancelled"
    assert cancelled.started_at is None
    assert [event.event_type for event in registry.events(cancelled.execution_id)] == [
        "execution_reserved",
        "execution_cancelled_before_start",
    ]
