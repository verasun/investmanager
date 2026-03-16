"""Tests for Task API endpoints."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.main import app
from src.orchestrator import Task, TaskType, TaskStatus, TaskPriority
from src.orchestrator.queue import TaskQueue


# Test fixtures
@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_tasks.db"
    yield db_path
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_queue(temp_db):
    """Create a mock task queue with temporary database."""
    queue = TaskQueue(temp_db)
    return queue


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_task_data():
    """Sample task creation data."""
    return {
        "type": "data_fetch",
        "input": {
            "symbols": ["AAPL", "MSFT"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "name": "test_data_fetch",
        "description": "Test task for data fetching",
        "priority": 5,
        "max_retries": 3,
        "tags": ["test", "data"],
    }


class TestTaskAPI:
    """Test cases for Task API endpoints."""

    def test_create_task_success(self, client, sample_task_data):
        """Test successful task creation."""
        response = client.post("/api/v1/tasks/tasks", json=sample_task_data)

        assert response.status_code == 200
        data = response.json()

        assert "id" in data
        assert data["type"] == "data_fetch"
        assert data["name"] == "test_data_fetch"
        assert data["status"] == "pending"
        assert data["priority"] == 5
        assert data["input"]["symbols"] == ["AAPL", "MSFT"]

    def test_create_task_invalid_type(self, client):
        """Test task creation with invalid type."""
        invalid_data = {
            "type": "invalid_type",
            "input": {"test": "data"},
        }

        response = client.post("/api/v1/tasks/tasks", json=invalid_data)

        assert response.status_code == 400
        assert "Invalid task type" in response.json()["detail"]

    def test_create_task_missing_required_fields(self, client):
        """Test task creation with missing required fields."""
        incomplete_data = {
            "name": "incomplete_task",
        }

        response = client.post("/api/v1/tasks/tasks", json=incomplete_data)

        assert response.status_code == 422  # Validation error

    def test_create_task_invalid_priority(self, client):
        """Test task creation with invalid priority value."""
        invalid_priority_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "priority": 100,  # Invalid: should be 1-20
        }

        response = client.post("/api/v1/tasks/tasks", json=invalid_priority_data)

        assert response.status_code == 422  # Validation error

    def test_get_task_success(self, client, sample_task_data):
        """Test getting a task by ID."""
        # First create a task
        create_response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Then get the task
        get_response = client.get(f"/api/v1/tasks/tasks/{task_id}")

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["id"] == task_id
        assert data["type"] == "data_fetch"

    def test_get_task_not_found(self, client):
        """Test getting a non-existent task."""
        response = client.get("/api/v1/tasks/tasks/nonexistent_task_id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_list_tasks_no_filter(self, client, sample_task_data):
        """Test listing all tasks without filter."""
        # Create a few tasks
        for i in range(3):
            task_data = sample_task_data.copy()
            task_data["name"] = f"test_task_{i}"
            client.post("/api/v1/tasks/tasks", json=task_data)

        response = client.get("/api/v1/tasks/tasks")

        assert response.status_code == 200
        data = response.json()

        assert "tasks" in data
        assert "total" in data
        assert "status_counts" in data
        assert len(data["tasks"]) >= 3

    def test_list_tasks_with_status_filter(self, client, sample_task_data):
        """Test listing tasks filtered by status."""
        # Create tasks
        client.post("/api/v1/tasks/tasks", json=sample_task_data)

        response = client.get("/api/v1/tasks/tasks?status=pending")

        assert response.status_code == 200
        data = response.json()

        assert all(task["status"] == "pending" for task in data["tasks"])

    def test_list_tasks_invalid_status(self, client):
        """Test listing tasks with invalid status filter."""
        response = client.get("/api/v1/tasks/tasks?status=invalid_status")

        assert response.status_code == 400

    def test_list_tasks_pagination(self, client, sample_task_data):
        """Test task list pagination."""
        # Create multiple tasks
        for i in range(10):
            task_data = sample_task_data.copy()
            task_data["name"] = f"task_{i}"
            client.post("/api/v1/tasks/tasks", json=task_data)

        # Test limit
        response = client.get("/api/v1/tasks/tasks?limit=5")
        assert response.status_code == 200

        # Test offset
        response = client.get("/api/v1/tasks/tasks?limit=5&offset=5")
        assert response.status_code == 200

    def test_cancel_task_success(self, client, sample_task_data):
        """Test cancelling a pending task."""
        # Create a task
        create_response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Cancel the task
        cancel_response = client.post(f"/api/v1/tasks/tasks/{task_id}/cancel")

        assert cancel_response.status_code == 200
        assert "cancelled" in cancel_response.json()["message"].lower()

    def test_cancel_task_not_found(self, client):
        """Test cancelling a non-existent task."""
        response = client.post("/api/v1/tasks/tasks/nonexistent/cancel")

        assert response.status_code == 400

    def test_retry_task_success(self, client, sample_task_data):
        """Test retrying a failed task."""
        # Create a task
        create_response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Manually mark as failed for testing
        # Note: In real scenario, the task would fail after execution
        # For this test, we'll directly modify the task status
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()
        orchestrator.task_queue.mark_failed(task_id, "Test failure", retry=False)

        # Retry the task
        retry_response = client.post(f"/api/v1/tasks/tasks/{task_id}/retry")

        assert retry_response.status_code == 200
        assert "retry" in retry_response.json()["message"].lower()

    def test_retry_task_not_failed(self, client, sample_task_data):
        """Test retrying a task that is not in failed status."""
        # Create a task (it will be in pending status)
        create_response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Try to retry a pending task (should fail)
        retry_response = client.post(f"/api/v1/tasks/tasks/{task_id}/retry")

        assert retry_response.status_code == 400

    def test_create_pipeline_success(self, client):
        """Test creating a complete analysis pipeline."""
        pipeline_data = {
            "symbols": ["AAPL", "MSFT", "GOOGL"],
            "strategies": ["momentum", "mean_reversion"],
            "email_recipients": ["test@example.com"],
            "priority": 10,
        }

        response = client.post("/api/v1/tasks/tasks/pipeline", json=pipeline_data)

        assert response.status_code == 200
        data = response.json()

        assert "task_ids" in data
        assert len(data["task_ids"]) >= 3  # At least data_fetch, analysis, report
        assert "message" in data

    def test_create_pipeline_minimal(self, client):
        """Test creating a minimal pipeline (no strategies, no email)."""
        pipeline_data = {
            "symbols": ["AAPL"],
        }

        response = client.post("/api/v1/tasks/tasks/pipeline", json=pipeline_data)

        assert response.status_code == 200
        data = response.json()

        # Should have data_fetch, analysis, report (no backtest, no email)
        assert len(data["task_ids"]) >= 3

    def test_create_pipeline_empty_symbols(self, client):
        """Test creating pipeline with empty symbols."""
        pipeline_data = {
            "symbols": [],
        }

        response = client.post("/api/v1/tasks/tasks/pipeline", json=pipeline_data)

        # Should either fail validation or handle gracefully
        # The current implementation doesn't validate empty symbols
        # So it will create tasks but they may fail later
        assert response.status_code in [200, 422]

    def test_get_orchestrator_status(self, client):
        """Test getting orchestrator status."""
        response = client.get("/api/v1/tasks/status")

        assert response.status_code == 200
        data = response.json()

        assert "running" in data
        assert "queue_size" in data
        assert isinstance(data["queue_size"], dict)

    def test_cleanup_tasks(self, client):
        """Test cleaning up old completed tasks."""
        response = client.post("/api/v1/tasks/cleanup?days=7")

        assert response.status_code == 200
        data = response.json()

        assert "deleted_count" in data
        assert isinstance(data["deleted_count"], int)

    def test_task_priority_validation(self, client):
        """Test task priority is within valid range."""
        # Test minimum priority
        min_priority_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "priority": 1,
        }
        response = client.post("/api/v1/tasks/tasks", json=min_priority_data)
        assert response.status_code == 200
        assert response.json()["priority"] == 1

        # Test maximum priority
        max_priority_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "priority": 20,
        }
        response = client.post("/api/v1/tasks/tasks", json=max_priority_data)
        assert response.status_code == 200
        assert response.json()["priority"] == 20

        # Test below minimum
        below_min_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "priority": 0,
        }
        response = client.post("/api/v1/tasks/tasks", json=below_min_data)
        assert response.status_code == 422

        # Test above maximum
        above_max_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "priority": 21,
        }
        response = client.post("/api/v1/tasks/tasks", json=above_max_data)
        assert response.status_code == 422

    def test_task_max_retries_validation(self, client):
        """Test max_retries is within valid range."""
        # Test valid values
        for retries in [0, 5, 10]:
            task_data = {
                "type": "data_fetch",
                "input": {"symbols": ["AAPL"]},
                "max_retries": retries,
            }
            response = client.post("/api/v1/tasks/tasks", json=task_data)
            assert response.status_code == 200

        # Test invalid values
        for retries in [-1, 11]:
            task_data = {
                "type": "data_fetch",
                "input": {"symbols": ["AAPL"]},
                "max_retries": retries,
            }
            response = client.post("/api/v1/tasks/tasks", json=task_data)
            assert response.status_code == 422

    def test_all_task_types(self, client):
        """Test creating tasks of all valid types."""
        task_types = ["data_fetch", "analysis", "backtest", "report", "email"]

        for task_type in task_types:
            task_data = {
                "type": task_type,
                "input": {"test": "data"},
            }
            response = client.post("/api/v1/tasks/tasks", json=task_data)
            assert response.status_code == 200, f"Failed for type: {task_type}"
            assert response.json()["type"] == task_type

    def test_task_with_dependencies(self, client):
        """Test creating a task with dependencies."""
        # Create first task
        first_task_data = {
            "type": "data_fetch",
            "input": {"symbols": ["AAPL"]},
            "name": "first_task",
        }
        first_response = client.post("/api/v1/tasks/tasks", json=first_task_data)
        first_task_id = first_response.json()["id"]

        # Create second task with dependency on first
        second_task_data = {
            "type": "analysis",
            "input": {"data_path": f"task://{first_task_id}/output"},
            "dependencies": [first_task_id],
            "name": "second_task",
        }
        second_response = client.post("/api/v1/tasks/tasks", json=second_task_data)

        assert second_response.status_code == 200
        assert first_task_id in second_response.json()["dependencies"]

    def test_status_counts_accuracy(self, client, sample_task_data):
        """Test that status counts are accurate."""
        # Clear any existing tasks first (by using fresh database)
        # Then create tasks
        num_tasks = 5
        for i in range(num_tasks):
            task_data = sample_task_data.copy()
            task_data["name"] = f"task_{i}"
            client.post("/api/v1/tasks/tasks", json=task_data)

        response = client.get("/api/v1/tasks/tasks")
        data = response.json()

        # Check that total matches sum of status counts
        assert data["total"] == sum(data["status_counts"].values())
        # Check pending count is at least num_tasks
        assert data["status_counts"]["pending"] >= num_tasks


class TestTaskQueueIntegration:
    """Integration tests for TaskQueue."""

    def test_queue_enqueue_dequeue(self, temp_db):
        """Test basic queue operations."""
        queue = TaskQueue(temp_db)

        task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["AAPL"]},
        )

        task_id = queue.enqueue(task)
        assert task_id == task.id

        # Get next task
        next_task = queue.get_next()
        assert next_task is not None
        assert next_task.id == task_id

    def test_queue_priority_ordering(self, temp_db):
        """Test that higher priority tasks are returned first."""
        queue = TaskQueue(temp_db)

        # Create tasks with different priorities
        low_task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["LOW"]},
            priority=TaskPriority.LOW,
            name="low_priority",
        )
        high_task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["HIGH"]},
            priority=TaskPriority.HIGH,
            name="high_priority",
        )

        # Enqueue in reverse order
        queue.enqueue(low_task)
        queue.enqueue(high_task)

        # Higher priority should be returned first
        next_task = queue.get_next()
        assert next_task.name == "high_priority"

    def test_queue_status_transitions(self, temp_db):
        """Test task status transitions."""
        queue = TaskQueue(temp_db)

        task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["AAPL"]},
        )
        task_id = queue.enqueue(task)

        # Initial status
        task = queue.get_by_id(task_id)
        assert task.status == TaskStatus.PENDING

        # Mark running
        queue.mark_running(task_id)
        task = queue.get_by_id(task_id)
        assert task.status == TaskStatus.RUNNING

        # Mark completed
        queue.mark_completed(task_id, {"result": "success"})
        task = queue.get_by_id(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.output == {"result": "success"}

    def test_queue_retry_logic(self, temp_db):
        """Test task retry logic."""
        queue = TaskQueue(temp_db)

        task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["AAPL"]},
            max_retries=2,
        )
        task_id = queue.enqueue(task)

        # Mark as running
        queue.mark_running(task_id)

        # Mark as failed with retry
        queue.mark_failed(task_id, "Test error", retry=True)
        task = queue.get_by_id(task_id)
        assert task.status == TaskStatus.RETRYING
        assert task.retry_count == 1

        # Manual retry
        queue.retry(task_id)
        task = queue.get_by_id(task_id)
        assert task.retry_count == 2

    def test_queue_dependencies(self, temp_db):
        """Test task dependency handling."""
        queue = TaskQueue(temp_db)

        # Create parent task
        parent_task = Task(
            type=TaskType.DATA_FETCH,
            input={"symbols": ["AAPL"]},
            name="parent",
        )
        parent_id = queue.enqueue(parent_task)

        # Create dependent task
        child_task = Task(
            type=TaskType.ANALYSIS,
            input={"data_path": f"task://{parent_id}/output"},
            dependencies=[parent_id],
            name="child",
        )
        child_id = queue.enqueue(child_task)

        # Child should not be returned while parent is pending
        next_task = queue.get_next()
        assert next_task.id == parent_id

        # Complete parent
        queue.mark_running(parent_id)
        queue.mark_completed(parent_id, {"data_path": "/tmp/data.parquet"})

        # Now child should be returned
        next_task = queue.get_next()
        assert next_task.id == child_id


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_concurrent_task_creation(self, client, sample_task_data):
        """Test creating multiple tasks concurrently (simulated)."""
        import concurrent.futures

        def create_task(i):
            task_data = sample_task_data.copy()
            task_data["name"] = f"concurrent_task_{i}"
            return client.post("/api/v1/tasks/tasks", json=task_data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_task, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(r.status_code == 200 for r in results)

    def test_task_id_format(self, client, sample_task_data):
        """Test that task IDs have expected format."""
        response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        task_id = response.json()["id"]

        # Task ID should be a short string
        assert isinstance(task_id, str)
        assert len(task_id) > 0
        assert len(task_id) <= 20  # Reasonable length

    def test_timestamp_format(self, client, sample_task_data):
        """Test that timestamps are in ISO format."""
        response = client.post("/api/v1/tasks/tasks", json=sample_task_data)
        data = response.json()

        # created_at should be ISO format
        created_at = data["created_at"]
        assert "T" in created_at or "-" in created_at

        # Should be parseable
        from datetime import datetime
        datetime.fromisoformat(created_at)

    def test_special_characters_in_input(self, client):
        """Test handling special characters in task input."""
        task_data = {
            "type": "data_fetch",
            "input": {
                "symbols": ["AAPL"],
                "description": "Test with special chars: <>&\"'",
            },
        }

        response = client.post("/api/v1/tasks/tasks", json=task_data)

        assert response.status_code == 200


def run_tests():
    """Run all tests."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    return result.returncode


if __name__ == "__main__":
    run_tests()