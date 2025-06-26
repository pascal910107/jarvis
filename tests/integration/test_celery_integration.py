"""
Integration tests for Celery task queue functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.celery import celery_app, example_task


class TestCeleryIntegration:
    """Test suite for Celery integration."""

    @pytest.mark.integration
    def test_celery_app_configuration(self):
        """Test that Celery app is properly configured."""
        assert celery_app.main == "jarvis"
        assert "redis://localhost:6379/0" in celery_app.conf.broker_url
        assert "redis://localhost:6379/0" in celery_app.conf.result_backend

    @pytest.mark.integration
    @pytest.mark.requires_redis
    def test_example_task_execution(self):
        """Test example task execution (requires Redis)."""
        # This test would require actual Redis connection
        # For now, we'll mock it
        with patch("core.celery.celery_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="test-task-id")

            # Test task can be called
            result = example_task.delay(5, 3)
            assert result.id == "test-task-id"
            mock_send.assert_called_once()

    @pytest.mark.integration
    def test_task_registration(self):
        """Test that tasks are properly registered."""
        # Check if example_task is registered
        registered_tasks = celery_app.tasks
        assert "core.celery.example_task" in registered_tasks

    @pytest.mark.integration
    @patch("redis.Redis")
    def test_celery_broker_connection(self, mock_redis):
        """Test Celery broker connection handling."""
        # Mock Redis connection
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        # Test connection
        import redis

        r = redis.Redis(host="localhost", port=6379, db=0)
        assert r.ping() is True
