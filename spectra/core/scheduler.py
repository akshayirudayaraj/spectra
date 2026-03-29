"""TaskScheduler — time-based task scheduling for Spectra."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta

from croniter import croniter


_PERSIST_PATH = os.path.join(os.path.dirname(__file__), '..', 'flows', 'scheduled_tasks.json')


def _parse_recurrence(recurrence: str, schedule_type: str):
    """Parse natural language recurrence into (cron, interval_seconds, next_run).

    Returns a dict with keys: cron, interval_seconds, next_run (epoch float).
    """
    text = recurrence.lower().strip()
    now = datetime.now()

    # --- Interval patterns: "every N minutes/hours/seconds" ---
    m = re.match(r'every\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?', text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit in ('second', 'sec'):
            secs = amount
        elif unit in ('minute', 'min'):
            secs = amount * 60
        else:
            secs = amount * 3600
        return {
            'cron': None,
            'interval_seconds': secs,
            'next_run': time.time() + secs,
        }

    # --- Cron-mappable patterns ---
    cron_expr = None

    # "daily at HH:MM" or "every day at HH:MM"
    m = re.search(r'(?:daily|every\s*day)\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if m:
        hour, minute, ampm = _parse_time_parts(m)
        cron_expr = f'{minute} {hour} * * *'

    # "weekdays at HH:MM" or "every weekday at HH:MM"
    if not cron_expr:
        m = re.search(r'(?:weekdays?|every\s*weekday)\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if m:
            hour, minute, ampm = _parse_time_parts(m)
            cron_expr = f'{minute} {hour} * * 1-5'

    # "every monday/tuesday/... at HH:MM"
    if not cron_expr:
        days_map = {'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4,
                     'friday': 5, 'saturday': 6, 'sunday': 0,
                     'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6, 'sun': 0}
        m = re.search(
            r'every\s+(' + '|'.join(days_map.keys()) + r')\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
            text,
        )
        if m:
            day_name = m.group(1)
            day_num = days_map[day_name]
            hour = int(m.group(2))
            minute = int(m.group(3) or 0)
            ampm = m.group(4)
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            cron_expr = f'{minute} {hour} * * {day_num}'

    if cron_expr:
        cron = croniter(cron_expr, now)
        next_dt = cron.get_next(datetime)
        return {
            'cron': cron_expr,
            'interval_seconds': None,
            'next_run': next_dt.timestamp(),
        }

    # --- One-time patterns ---
    if schedule_type == 'once':
        return _parse_one_time(text, now)

    # Fallback: try to extract just a time
    m = re.search(r'(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if m:
        hour, minute, _ = _parse_time_parts(m)
        if schedule_type == 'recurring':
            cron_expr = f'{minute} {hour} * * *'
            cron = croniter(cron_expr, now)
            next_dt = cron.get_next(datetime)
            return {
                'cron': cron_expr,
                'interval_seconds': None,
                'next_run': next_dt.timestamp(),
            }
        else:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return {
                'cron': None,
                'interval_seconds': None,
                'next_run': target.timestamp(),
            }

    # Last resort: 5 minutes from now
    return {
        'cron': None,
        'interval_seconds': 300 if schedule_type == 'recurring' else None,
        'next_run': time.time() + 300,
    }


def _parse_time_parts(m):
    """Extract (hour_24, minute, ampm) from a regex match with groups (hour, min?, ampm?)."""
    # Groups are at index 1, 2, 3 relative to the match — but the caller
    # may pass different group layouts, so we read positionally from the match.
    groups = m.groups()
    # Find the first digit group
    hour = None
    minute = 0
    ampm = None
    for g in groups:
        if g is None:
            continue
        if g.isdigit() and hour is None:
            hour = int(g)
        elif g.isdigit() and hour is not None:
            minute = int(g)
        elif g in ('am', 'pm'):
            ampm = g
    if hour is None:
        hour = 0
    if ampm == 'pm' and hour < 12:
        hour += 12
    elif ampm == 'am' and hour == 12:
        hour = 0
    return hour, minute, ampm


def _parse_one_time(text, now):
    """Parse one-time schedule expressions like 'tomorrow at 3pm', 'in 10 minutes'."""
    # "in N minutes/hours/seconds"
    m = re.search(r'in\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?', text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit in ('second', 'sec'):
            delta = amount
        elif unit in ('minute', 'min'):
            delta = amount * 60
        else:
            delta = amount * 3600
        return {
            'cron': None,
            'interval_seconds': None,
            'next_run': time.time() + delta,
        }

    # "tomorrow at HH:MM am/pm"
    m = re.search(r'tomorrow\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if m:
        hour, minute, _ = _parse_time_parts(m)
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            'cron': None,
            'interval_seconds': None,
            'next_run': target.timestamp(),
        }

    # "at HH:MM am/pm" (today or tomorrow if past)
    m = re.search(r'(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if m:
        hour, minute, _ = _parse_time_parts(m)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return {
            'cron': None,
            'interval_seconds': None,
            'next_run': target.timestamp(),
        }

    # Fallback
    return {
        'cron': None,
        'interval_seconds': None,
        'next_run': time.time() + 300,
    }


class TaskScheduler:
    """Manage scheduled tasks with a background polling thread."""

    def __init__(self, run_agent_fn=None, state=None):
        self._tasks = {}
        self._thread = None
        self._stop_event = threading.Event()
        self._run_agent_fn = run_agent_fn
        self._state = state
        self._task_running = False  # guard against concurrent execution
        self._push_fn = None  # optional: callable(title, body) for native push notifications
        self._lock = threading.Lock()
        self.load()

    # -- CRUD -----------------------------------------------------------------

    def schedule(self, task: str, schedule_type: str, recurrence: str, next_run: str = None) -> dict:
        """Create a new scheduled task. Returns the task dict."""
        parsed = _parse_recurrence(recurrence, schedule_type)
        task_id = str(uuid.uuid4())[:8]
        now = time.time()

        # Allow caller to override next_run
        if next_run is not None:
            try:
                parsed['next_run'] = float(next_run)
            except (ValueError, TypeError):
                pass

        task_obj = {
            'id': task_id,
            'task': task,
            'schedule_type': schedule_type,
            'recurrence': recurrence,
            'cron': parsed.get('cron'),
            'interval_seconds': parsed.get('interval_seconds'),
            'next_run': parsed['next_run'],
            'enabled': True,
            'created_at': now,
            'fire_count': 0,
            'last_fired_at': None,
        }

        # Human-readable next run for display
        task_obj['next_run_display'] = self._format_next_run_display(parsed['next_run'])

        with self._lock:
            self._tasks[task_id] = task_obj
        self.save()

        print(f"[Scheduler] Created task {task_id}: '{task}' — {recurrence} (next: {task_obj['next_run_display']})")
        return task_obj

    def cancel(self, task_id: str) -> bool:
        """Cancel and remove a scheduled task."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self.save()
                print(f"[Scheduler] Cancelled task {task_id}")
                return True
        return False

    def list_tasks(self) -> list:
        """Return all tasks (active and paused)."""
        with self._lock:
            return list(self._tasks.values())

    def get_task(self, task_id: str) -> dict | None:
        """Return a single task by id."""
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def pause(self, task_id: str) -> bool:
        """Pause a task (keep it but stop firing)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.get('schedule_type') == 'recurring':
                task['enabled'] = False
                self.save()
                print(f"[Scheduler] Paused task {task_id}")
                return True
        return False

    def resume(self, task_id: str) -> bool:
        """Re-enable a paused task."""
        with self._lock:
            t = self._tasks.get(task_id)
            if t and t.get('schedule_type') == 'recurring':
                t['enabled'] = True
                # Recompute next_run if the prior slot already elapsed while paused.
                if not t.get('next_run') or t['next_run'] < time.time():
                    t['next_run'] = self._compute_next_run(t)
                t['next_run_display'] = self._format_next_run_display(t.get('next_run'))
                self.save()
                print(f"[Scheduler] Resumed task {task_id}")
                return True
        return False

    # -- Lifecycle ------------------------------------------------------------

    def start(self):
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print("[Scheduler] Started polling thread (30s interval)")

    def stop(self):
        """Gracefully stop the polling thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        print("[Scheduler] Stopped")

    # -- Persistence ----------------------------------------------------------

    def save(self):
        """Persist tasks to flows/scheduled_tasks.json."""
        path = os.path.abspath(_PERSIST_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(list(self._tasks.values()), f, indent=2)

    def load(self):
        """Load tasks from flows/scheduled_tasks.json."""
        path = os.path.abspath(_PERSIST_PATH)
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                tasks = json.load(f)
            for t in tasks:
                self._tasks[t['id']] = t
            print(f"[Scheduler] Loaded {len(tasks)} tasks from disk")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[Scheduler] Failed to load tasks: {e}")

    # -- Internal -------------------------------------------------------------

    def _poll_loop(self):
        """Check for due tasks every 30 seconds."""
        while not self._stop_event.is_set():
            try:
                self._check_due()
            except Exception as e:
                print(f"[Scheduler] Poll error: {e}")
            self._stop_event.wait(30)

    def _check_due(self):
        """Fire any tasks whose next_run has passed."""
        now = time.time()
        with self._lock:
            due = [t for t in self._tasks.values()
                   if t['enabled'] and t['next_run'] and t['next_run'] <= now]
        for task in due:
            self._fire(task, now)

    def _fire(self, task: dict, now: float):
        """Execute a due task."""
        task_id = task['id']
        task_desc = task['task']
        print(f"[Scheduler] Firing task {task_id}: '{task_desc}'")

        # Notify iOS client
        if self._state:
            try:
                self._state.send({
                    'type': 'schedule_fired',
                    'task_id': task_id,
                    'task': task_desc,
                    'schedule_type': task.get('schedule_type'),
                })
            except Exception:
                pass

        # Native push is only a fallback when there is no live websocket client.
        if self._state is None and self._push_fn:
            try:
                self._push_fn(
                    'Scheduled Task',
                    f'Running: {task_desc}',
                    category='SCHEDULE_CONTROL',
                    user_info={'task_id': task_id},
                )
            except TypeError:
                self._push_fn('Scheduled Task', f'Running: {task_desc}')
            except Exception:
                pass

        # Execute if possible
        if self._run_agent_fn and not self._task_running:
            self._task_running = True
            try:
                self._run_agent_fn(task_desc)
            except Exception as e:
                print(f"[Scheduler] Execution error for {task_id}: {e}")
            finally:
                self._task_running = False

        # Update state
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t['last_fired_at'] = now
                t['fire_count'] = t.get('fire_count', 0) + 1
                if task['schedule_type'] == 'once':
                    t['enabled'] = False
                    t['next_run'] = None
                    t['next_run_display'] = None
                else:
                    t['next_run'] = self._compute_next_run(t)
                    t['next_run_display'] = self._format_next_run_display(t.get('next_run'))
        self.save()

    def _compute_next_run(self, task: dict) -> float:
        """Compute the next fire time for a recurring task."""
        now = time.time()

        if task.get('interval_seconds'):
            return now + task['interval_seconds']

        if task.get('cron'):
            cron = croniter(task['cron'], datetime.now())
            next_dt = cron.get_next(datetime)
            return next_dt.timestamp()

        return now + 300  # fallback: 5 minutes

    def _format_next_run_display(self, timestamp: float | None) -> str | None:
        if not timestamp:
            return None
        next_dt = datetime.fromtimestamp(timestamp)
        return next_dt.strftime('%Y-%m-%d %I:%M %p')
