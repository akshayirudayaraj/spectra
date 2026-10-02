"""Simulator helpers for the perception eval: reset state, read app databases, read UI."""
from __future__ import annotations

import glob
import os
import re
import sqlite3
import subprocess
import tempfile
import time

import wda

UDID = os.environ.get('SPECTRA_SIM_UDID', 'booted')
WDA_URL = os.environ.get('SPECTRA_WDA_URL', 'http://localhost:8100')

_client: wda.Client | None = None


def client() -> wda.Client:
    global _client
    if _client is None:
        _client = wda.Client(WDA_URL)
    return _client


def data_dir() -> str:
    if UDID == 'booted':
        raise RuntimeError('Set SPECTRA_SIM_UDID so the eval can read the simulator data directory')
    return os.path.expanduser(f'~/Library/Developer/CoreSimulator/Devices/{UDID}/data')


def simctl(*args: str) -> str:
    out = subprocess.run(['xcrun', 'simctl', *args], capture_output=True, text=True)
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Defaults / appearance
# ---------------------------------------------------------------------------

def defaults_read(domain: str, key: str) -> str | None:
    out = subprocess.run(['xcrun', 'simctl', 'spawn', UDID, 'defaults', 'read', domain, key],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def defaults_write_bool(domain: str, key: str, value: bool) -> None:
    simctl('spawn', UDID, 'defaults', 'write', domain, key, '-bool', 'true' if value else 'false')


def appearance() -> str:
    return simctl('ui', UDID, 'appearance')


def content_size() -> str:
    return simctl('ui', UDID, 'content_size')


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

_ALERT_BUTTONS = ('Allow While Using App', 'Allow', 'Not Now', 'OK', 'Continue', 'Don’t Allow')


def dismiss_alerts(max_alerts: int = 3) -> None:
    """Clear stray system alerts so they don't land in one run and not another."""
    c = client()
    for _ in range(max_alerts):
        try:
            if not c.alert.exists:
                return
            buttons = c.alert.buttons()
            choice = next((b for b in _ALERT_BUTTONS if b in buttons), buttons[-1] if buttons else None)
            if choice is None:
                return
            c.alert.click(choice)
            time.sleep(1)
        except Exception:
            return


def reset_to_app(bundle_id: str, also_terminate: tuple[str, ...] = ()) -> None:
    """Cold-start the target app from the home screen, like the router would."""
    for b in (bundle_id, *also_terminate):
        simctl('terminate', UDID, b)
    try:
        client().home()
    except Exception:
        pass
    time.sleep(1)
    dismiss_alerts()
    simctl('launch', UDID, bundle_id)
    time.sleep(3)
    dismiss_alerts()


def go_home() -> None:
    try:
        client().home()
    except Exception:
        pass


def screen_text() -> str:
    """Raw accessibility XML of the current screen, for checks on the final UI state."""
    try:
        return client().source()
    except Exception:
        return ''


def safari_url() -> str:
    try:
        url = client().execute_script('return window.location.href')
        if isinstance(url, str):
            return url
    except Exception:
        pass
    m = re.search(r'name="Address"[^>]*value="([^"]+)"', screen_text())
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# Databases (read-only)
# ---------------------------------------------------------------------------

def _query(path: str, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _addressbook() -> str:
    return os.path.join(data_dir(), 'Library/AddressBook/AddressBook.sqlitedb')


def contacts_named(first: str, last: str) -> list[int]:
    return [r[0] for r in _query(_addressbook(),
            'SELECT ROWID FROM ABPerson WHERE First = ? AND Last = ?', (first, last))]


def contact_values(person_id: int, prop: int) -> list[str]:
    """prop 3 = phone, 4 = email."""
    return [r[0] or '' for r in _query(_addressbook(),
            'SELECT value FROM ABMultiValue WHERE record_id = ? AND property = ?', (person_id, prop))]


def import_contact(first: str, last: str) -> None:
    vcf = f'BEGIN:VCARD\nVERSION:3.0\nN:{last};{first};;;\nFN:{first} {last}\nEND:VCARD\n'
    with tempfile.NamedTemporaryFile('w', suffix='.vcf', delete=False) as f:
        f.write(vcf)
    simctl('addmedia', UDID, f.name)
    os.unlink(f.name)
    time.sleep(2)


def _reminder_stores() -> list[str]:
    return glob.glob(os.path.join(data_dir(), 'Containers/Shared/AppGroup/*/Container_v1/Stores/Data-*.sqlite'))


def reminders_titled(title: str) -> list[dict]:
    rows = []
    for store in _reminder_stores():
        try:
            for title_, prio, flagged in _query(store,
                    'SELECT ZTITLE, ZPRIORITY, ZFLAGGED FROM ZREMCDREMINDER '
                    'WHERE ZTITLE = ? AND ZMARKEDFORDELETION = 0', (title,)):
                rows.append({'title': title_, 'priority': prio, 'flagged': flagged})
        except sqlite3.OperationalError:
            continue
    return rows


def reminder_lists_named(name: str) -> int:
    n = 0
    for store in _reminder_stores():
        try:
            n += _query(store, 'SELECT COUNT(*) FROM ZREMCDBASELIST '
                               'WHERE ZNAME = ? AND ZMARKEDFORDELETION = 0', (name,))[0][0]
        except sqlite3.OperationalError:
            continue
    return n


_CORE_DATA_EPOCH = 978307200  # 2001-01-01 in unix time


def events_titled(title: str) -> list[dict]:
    path = os.path.join(data_dir(), 'Library/Calendar/Calendar.sqlitedb')
    return [{'start': (start or 0) + _CORE_DATA_EPOCH, 'all_day': all_day}
            for start, all_day in _query(path,
                'SELECT start_date, all_day FROM CalendarItem WHERE summary = ?', (title,))]
