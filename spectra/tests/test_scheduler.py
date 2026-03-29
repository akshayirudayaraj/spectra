"""Tests for core/scheduler.py — TaskScheduler."""
import json
import os
import time
import tempfile
import threading

import pytest

from core.scheduler import TaskScheduler, _parse_recurrence


# Use a temp file for persistence so tests don't pollute real data
@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    persist_path = str(tmp_path / 'scheduled_tasks.json')
    monkeypatch.setattr('core.scheduler._PERSIST_PATH', persist_path)
    s = TaskScheduler()
    yield s
    s.stop()


class TestParseRecurrence:
    def test_every_n_minutes(self):
        result = _parse_recurrence('every 5 minutes', 'recurring')
        assert result['interval_seconds'] == 300
        assert result['cron'] is None
        assert result['next_run'] > time.time() - 1

    def test_every_n_seconds(self):
        result = _parse_recurrence('every 10 seconds', 'recurring')
        assert result['interval_seconds'] == 10

    def test_every_n_hours(self):
        result = _parse_recurrence('every 2 hours', 'recurring')
        assert result['interval_seconds'] == 7200

    def test_daily_at_time(self):
        result = _parse_recurrence('daily at 8am', 'recurring')
        assert result['cron'] == '0 8 * * *'
        assert result['interval_seconds'] is None

    def test_weekdays_at_time(self):
        result = _parse_recurrence('weekdays at 9am', 'recurring')
        assert result['cron'] == '0 9 * * 1-5'

    def test_in_n_minutes_once(self):
        result = _parse_recurrence('in 10 minutes', 'once')
        assert result['interval_seconds'] is None
        assert result['next_run'] == pytest.approx(time.time() + 600, abs=2)

    def test_tomorrow_at_time(self):
        result = _parse_recurrence('tomorrow at 3pm', 'once')
        assert result['next_run'] > time.time()
        assert result['cron'] is None


class TestSchedulerCRUD:
    def test_create_one_time_task(self, scheduler):
        task = scheduler.schedule('check email', 'once', 'in 10 seconds')
        assert task['id']
        assert task['task'] == 'check email'
        assert task['schedule_type'] == 'once'
        assert task['enabled'] is True
        assert task['next_run'] > time.time() - 1

    def test_create_recurring_task(self, scheduler):
        task = scheduler.schedule('check headlines', 'recurring', 'every 2 seconds')
        assert task['schedule_type'] == 'recurring'
        assert task['recurrence'] == 'every 2 seconds'

    def test_cancel_task(self, scheduler):
        task = scheduler.schedule('test', 'once', 'in 1 minute')
        assert len(scheduler.list_tasks()) == 1
        assert scheduler.cancel(task['id'])
        assert len(scheduler.list_tasks()) == 0

    def test_cancel_nonexistent(self, scheduler):
        assert scheduler.cancel('nonexistent') is False

    def test_pause_keeps_recurring_task_visible(self, scheduler):
        task = scheduler.schedule('test', 'recurring', 'every 5 minutes')
        assert scheduler.pause(task['id'])
        tasks = scheduler.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]['id'] == task['id']
        assert tasks[0]['enabled'] is False

    def test_resume_recomputes_next_run_after_pause(self, scheduler):
        task = scheduler.schedule('test', 'recurring', 'every 5 minutes')
        scheduler.pause(task['id'])
        scheduler._tasks[task['id']]['next_run'] = time.time() - 30
        scheduler._tasks[task['id']]['next_run_display'] = 'stale'

        assert scheduler.resume(task['id'])
        resumed = scheduler.get_task(task['id'])
        assert resumed is not None
        assert resumed['enabled'] is True
        assert resumed['next_run'] > time.time()
        assert resumed['next_run_display'] != 'stale'

    def test_pause_rejects_one_time_task(self, scheduler):
        task = scheduler.schedule('test', 'once', 'in 5 minutes')
        assert scheduler.pause(task['id']) is False


class TestSchedulerFiring:
    def test_task_fires_at_right_time(self, scheduler):
        fired = []
        scheduler._run_agent_fn = lambda t: fired.append(t)

        # Schedule with 1-second interval, next_run = now
        task = scheduler.schedule('do thing', 'recurring', 'every 1 seconds')
        # Force next_run to now so it fires immediately
        scheduler._tasks[task['id']]['next_run'] = time.time() - 1

        scheduler.start()
        time.sleep(3)
        scheduler.stop()

        assert len(fired) >= 1
        assert fired[0] == 'do thing'

    def test_one_time_disables_after_fire(self, scheduler):
        fired = []
        scheduler._run_agent_fn = lambda t: fired.append(t)

        task = scheduler.schedule('once thing', 'once', 'in 1 seconds')
        scheduler._tasks[task['id']]['next_run'] = time.time() - 1

        scheduler.start()
        time.sleep(3)
        scheduler.stop()

        assert len(fired) >= 1
        t = scheduler._tasks[task['id']]
        assert t['enabled'] is False
        assert t['fire_count'] >= 1

    def test_fire_sends_websocket_and_skips_push_when_state_present(self, scheduler):
        sent = []
        pushed = []

        class DummyState:
            def send(self, msg):
                sent.append(msg)

        scheduler._state = DummyState()
        scheduler._push_fn = lambda *args, **kwargs: pushed.append((args, kwargs))

        task = scheduler.schedule('do thing', 'recurring', 'every 5 minutes')
        scheduler._fire(task, time.time())

        assert sent == [{
            'type': 'schedule_fired',
            'task_id': task['id'],
            'task': 'do thing',
            'schedule_type': 'recurring',
        }]
        assert pushed == []

    def test_fire_uses_push_fallback_when_no_state(self, scheduler):
        pushed = []
        scheduler._state = None
        scheduler._push_fn = lambda *args, **kwargs: pushed.append((args, kwargs))

        task = scheduler.schedule('do thing', 'recurring', 'every 5 minutes')
        scheduler._fire(task, time.time())

        assert pushed == [(
            ('Scheduled Task', 'Running: do thing'),
            {'category': 'SCHEDULE_CONTROL', 'user_info': {'task_id': task['id']}},
        )]


class TestPersistence:
    def test_save_load(self, scheduler, tmp_path, monkeypatch):
        scheduler.schedule('task A', 'recurring', 'every 5 minutes')
        scheduler.schedule('task B', 'once', 'in 10 minutes')
        scheduler.save()

        # Create a new scheduler instance — should load from disk
        persist_path = str(tmp_path / 'scheduled_tasks.json')
        monkeypatch.setattr('core.scheduler._PERSIST_PATH', persist_path)
        s2 = TaskScheduler()
        tasks = s2.list_tasks()
        assert len(tasks) == 2
        descriptions = {t['task'] for t in tasks}
        assert 'task A' in descriptions
        assert 'task B' in descriptions
