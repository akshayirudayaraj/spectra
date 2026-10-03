"""Task suite for the tree-vs-screenshot perception eval.

Every task is scored by an independent check against simulator state (defaults,
app databases, Safari's URL, or the final screen), never by the agent's own
done() claim. Tasks that create records take a fresh name on every run, so a run
can't find the previous run's record and stop early.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Callable

from evals import sim

SETTINGS = 'com.apple.Preferences'
CONTACTS = 'com.apple.MobileAddressBook'
REMINDERS = 'com.apple.reminders'
CALENDAR = 'com.apple.mobilecal'
SAFARI = 'com.apple.mobilesafari'
MAPS = 'com.apple.Maps'

A11Y = 'com.apple.Accessibility'

_FIRST = ['Ada', 'Grace', 'Alan', 'Edsger', 'Barbara', 'Donald', 'Margaret', 'Dennis',
          'Frances', 'Ken', 'Radia', 'Claude']
_LAST = ['Lovelace', 'Hopper', 'Turing', 'Dijkstra', 'Liskov', 'Knuth', 'Hamilton', 'Ritchie',
         'Allen', 'Thompson', 'Perlman', 'Shannon']
_ERRAND_VERB = ['Buy', 'Pick up', 'Return']
_ERRAND_OBJ = ['milk', 'batteries', 'stamps', 'printer paper', 'light bulbs', 'dish soap',
               'coffee beans', 'a birthday card', 'tape', 'rice', 'sunscreen', 'shoelaces']
_LIST_A = ['Garden', 'Kitchen', 'Travel', 'Office', 'Gift', 'Holiday', 'Garage', 'Study']
_LIST_B = ['Ideas', 'Tasks', 'Plans', 'Errands']
_EVENT_A = ['Dentist', 'Haircut', 'Yoga', 'Piano lesson', 'Car service', 'Vet visit',
            'Book club', 'Tennis']
_EVENT_B = ['with Sam', 'with Priya', 'with Leo', 'with Mei']
_WIKI = [('Alan Turing',), ('Grace Hopper',), ('Ada Lovelace',), ('Claude Shannon',),
         ('Edsger W. Dijkstra',), ('Margaret Hamilton',), ('Donald Knuth',), ('Barbara Liskov',),
         ('Dennis Ritchie',), ('Ken Thompson',), ('Radia Perlman',), ('Frances Allen',)]
_PLACES = ['Golden Gate Bridge', 'Coit Tower', 'Ferry Building', 'Palace of Fine Arts',
           'Oracle Park', 'Pier 39', 'Alcatraz Island', 'Lombard Street', 'Salesforce Tower',
           'Twin Peaks', 'Dolores Park', 'Union Square']


_BIGGER_THAN_LARGE = {
    'extra-large', 'extra-extra-large', 'extra-extra-extra-large',
    'accessibility-medium', 'accessibility-large', 'accessibility-extra-large',
    'accessibility-extra-extra-large', 'accessibility-extra-extra-extra-large',
}


def _person(k: int, offset: int = 0) -> tuple[str, str]:
    i = k + offset
    return _FIRST[i % len(_FIRST)], _LAST[(i * 5 + 3) % len(_LAST)]


@dataclass
class Task:
    id: str
    app: str
    prompt: str                                   # may contain {placeholders}
    check: Callable[[dict, dict], tuple[bool, str]]
    params: Callable[[int], dict] = lambda k: {}
    setup: Callable[[dict], None] = lambda p: None
    category: str = ''
    tags: list[str] = field(default_factory=list)

    def render(self, p: dict) -> str:
        return self.prompt.format(**p)


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def _defaults_is(domain: str, key: str, want: str):
    def check(p, stats):
        got = sim.defaults_read(domain, key)
        return got == want, f'{key}={got}'
    return check


def _defaults_task(id, prompt, domain, key, want_on: bool, category='settings'):
    return Task(
        id=id, app=SETTINGS, prompt=prompt, category=category,
        setup=lambda p: sim.defaults_write_bool(domain, key, not want_on),
        check=_defaults_is(domain, key, '1' if want_on else '0'),
    )


def _summary(stats: dict) -> str:
    """The agent's final done() summary, for information-lookup tasks."""
    for line in reversed(stats.get('history', [])):
        if 'DONE:' in line:
            return line.split('DONE:', 1)[1]
    return ''


def _summary_has(*needles: str):
    def check(p, stats):
        s = _summary(stats)
        return all(n.lower() in s.lower() for n in needles), f'summary={s[:120]!r}'
    return check


def _contact_with_value(prop: int, field_: str):
    def check(p, stats):
        ids = sim.contacts_named(p['first'], p['last'])
        if not ids:
            return False, 'no contact'
        want = p[field_].lower()
        if prop == 3:
            want = ''.join(ch for ch in want if ch.isdigit())
        for pid in ids:
            vals = sim.contact_values(pid, prop)
            norm = [''.join(ch for ch in v if ch.isdigit()) if prop == 3 else v.lower() for v in vals]
            if any(want in v for v in norm):
                return True, f'contact {pid} has {p[field_]}'
        return False, f'contact exists, values={vals}'
    return check


def _check_event(p, stats):
    events = sim.events_titled(p['title'])
    if not events:
        return False, 'no event'
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    for e in events:
        start = dt.datetime.fromtimestamp(e['start'])
        if start.date() == tomorrow and start.hour == 15 and not e['all_day']:
            return True, f'event at {start}'
    return False, f'event(s) at {[str(dt.datetime.fromtimestamp(e["start"])) for e in events]}'


def _check_wiki(p, stats):
    # Safari's address bar only shows the domain and page JS isn't always reachable,
    # so match the document title WebKit exposes in the tree.
    xml = sim.screen_text()
    ok = f'{p["topic"]} - Wikipedia' in xml
    return ok, 'article open' if ok else 'article title not on screen'


def _check_place(p, stats):
    xml = sim.screen_text()
    ok = p['place'].lower() in xml.lower() and 'Directions' in xml
    return ok, 'place card open' if ok else 'no place card with Directions button'


def _check_about(p, stats):
    xml = sim.screen_text()
    ok = 'name="About"' in xml and 'Serial Number' in xml
    return ok, 'About page open' if ok else 'not on About'


def _ensure_contact(p):
    if not sim.contacts_named(p['first'], p['last']):
        sim.import_contact(p['first'], p['last'])


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

TASKS: list[Task] = [
    # --- Settings: toggles, verified through defaults ---
    _defaults_task('bold_text', 'Turn on Bold Text', A11Y, 'EnhancedTextLegibilityEnabled', True),
    _defaults_task('increase_contrast', 'Turn on Increase Contrast', A11Y, 'DarkenSystemColors', True),
    _defaults_task('button_borders', 'Turn on button borders in the accessibility settings',
                   A11Y, 'ButtonShapesEnabled', True),
    _defaults_task('reduce_motion', 'Turn on Reduce Motion', A11Y, 'ReduceMotionEnabled', True),
    # Keyboard settings aren't here: writing their defaults doesn't change what Settings shows,
    # so they can't be reset between runs.
    _defaults_task('reduce_transparency', 'Turn on Reduce Transparency', A11Y, 'EnhancedBackgroundContrastEnabled', True),
    _defaults_task('speak_selection', 'Turn on Speak Selection in the Spoken Content settings', A11Y, 'QuickSpeak', True),
    Task(
        # The simulator's Settings has no Display & Brightness page; Dark Mode lives under Developer.
        id='dark_mode', app=SETTINGS, prompt='Turn on Dark Appearance in the Developer settings', category='settings',
        setup=lambda p: sim.simctl('ui', sim.UDID, 'appearance', 'light'),
        check=lambda p, s: (sim.appearance() == 'dark', f'appearance={sim.appearance()}'),
    ),
    Task(
        id='text_size_up', app=SETTINGS, category='settings',
        prompt='Make the system text size larger using the Larger Text accessibility setting',
        setup=lambda p: sim.simctl('ui', sim.UDID, 'content_size', 'large'),
        check=lambda p, s: (sim.content_size() in _BIGGER_THAN_LARGE, f'content_size={sim.content_size()}'),
    ),
    # --- Information lookup, verified against known values ---
    Task(id='ios_version', app=SETTINGS, category='lookup',
         prompt='Find out which iOS version this phone is running and report it',
         check=_summary_has('26.5')),
    Task(id='kate_email', app=CONTACTS, category='lookup',
         prompt="Look up Kate Bell's email address and report it",
         check=_summary_has('kate-bell@mac.com')),
    # --- Contacts ---
    Task(
        id='contact_phone', app=CONTACTS, category='create',
        prompt='Create a new contact named {first} {last} with phone number {phone}',
        params=lambda k: dict(zip(('first', 'last'), _person(k)), phone=f'555{(2_345_678 + k * 7_919) % 10_000_000:07d}'),
        check=_contact_with_value(3, 'phone'),
    ),
    Task(
        id='contact_email', app=CONTACTS, category='create',
        prompt='Create a new contact named {first} {last} with email {email}',
        params=lambda k: (lambda f, l: dict(first=f, last=l, email=f'{f}.{l}{k}@example.com'.lower()))(*_person(k, 50)),
        check=_contact_with_value(4, 'email'),
    ),
    Task(
        id='contact_delete', app=CONTACTS, category='delete',
        prompt='Delete the contact named {first} {last}',
        params=lambda k: dict(first=_FIRST[(k + 7) % 12], last=f'Tester{k}'),
        setup=_ensure_contact,
        check=lambda p, s: (not sim.contacts_named(p['first'], p['last']),
                            f'{len(sim.contacts_named(p["first"], p["last"]))} left'),
    ),
    # --- Reminders ---
    Task(
        id='reminder_new', app=REMINDERS, category='create',
        prompt='Create a reminder called "{title}"',
        params=lambda k: dict(title=f'{_ERRAND_VERB[k % 3]} {_ERRAND_OBJ[(k // 3 + k) % 12]} #{k}'),
        check=lambda p, s: (bool(sim.reminders_titled(p['title'])), f'{len(sim.reminders_titled(p["title"]))} found'),
    ),
    Task(
        id='reminder_priority', app=REMINDERS, category='create',
        prompt='Create a reminder called "{title}" with high priority',
        params=lambda k: dict(title=f'{_ERRAND_VERB[(k + 1) % 3]} {_ERRAND_OBJ[(k * 5) % 12]} @{k}'),
        check=lambda p, s: (any(1 <= r['priority'] <= 4 for r in sim.reminders_titled(p['title'])),
                            f'reminders={sim.reminders_titled(p["title"])}'),
    ),
    Task(
        id='reminder_list', app=REMINDERS, category='create',
        prompt='Create a new reminders list called "{name}"',
        params=lambda k: dict(name=f'{_LIST_A[k % 8]} {_LIST_B[(k // 8) % 4]} {k}'),
        check=lambda p, s: (sim.reminder_lists_named(p['name']) > 0, f'{sim.reminder_lists_named(p["name"])} found'),
    ),
    # --- Calendar ---
    Task(
        id='calendar_event', app=CALENDAR, category='create',
        prompt='Create a calendar event called "{title}" tomorrow at 3 PM',
        params=lambda k: dict(title=f'{_EVENT_A[k % 8]} {_EVENT_B[(k // 8) % 4]} {k}'),
        check=_check_event,
    ),
    # --- Safari / Maps ---
    Task(
        id='wiki_article', app=SAFARI, category='web',
        prompt='In Safari, open the Wikipedia article about {topic}',
        params=lambda k: dict(topic=_WIKI[k % 12][0]),
        # Safari reopens its last page, so park it on a neutral one first.
        setup=lambda p: (sim.simctl('openurl', sim.UDID, 'https://example.com'), time.sleep(3)),
        check=_check_wiki,
    ),
    Task(
        id='maps_place', app=MAPS, category='maps',
        prompt='Search for {place} in Maps and open its place card',
        params=lambda k: dict(place=_PLACES[k % 12]),
        check=_check_place,
    ),
    Task(
        id='settings_about', app=SETTINGS, category='navigation',
        prompt='Open the page in Settings that shows the phone model name and serial number',
        check=_check_about,
    ),
]

TASKS_BY_ID = {t.id: t for t in TASKS}


# ---------------------------------------------------------------------------
# Hard suite: multi-step and multi-field tasks. Fixed before any runs on it.
# ---------------------------------------------------------------------------

_COMPANIES = ['Acme Robotics', 'Blue Harbor Labs', 'Cedar Analytics', 'Delta Foundry', 'Evergreen Systems',
              'Firefly Studio', 'Granite Works', 'Helios Energy', 'Indigo Health', 'Juniper Logistics',
              'Kestrel Aero', 'Lumen Optics']
_NOTES = ['bring the receipt', 'ask about the warranty', 'use the side entrance', 'call ahead first',
          'pay with the gift card', 'check the expiry date']
_A11Y_RESET = ('EnhancedTextLegibilityEnabled', 'ReduceMotionEnabled', 'DarkenSystemColors', 'QuickSpeak')


def _reset_a11y(p):
    for key in _A11Y_RESET:
        sim.defaults_write_bool(A11Y, key, False)
    sim.simctl('ui', sim.UDID, 'appearance', 'light')


def _all_keys_on(*keys, dark=False):
    def check(p, stats):
        got = {k: sim.defaults_read(A11Y, k) for k in keys}
        ok = all(v == '1' for v in got.values())
        if dark:
            got['appearance'] = sim.appearance()
            ok = ok and got['appearance'] == 'dark'
        return ok, str(got)
    return check


def _digits(v: str) -> str:
    return ''.join(ch for ch in v if ch.isdigit())


def _check_contact_full(p, stats):
    for pid in sim.contacts_named(p['first'], p['last']):
        phones = [_digits(v) for v in sim.contact_values(pid, 3)]
        emails = [v.lower() for v in sim.contact_values(pid, 4)]
        org = sim.contact_organization(pid)
        if _digits(p['phone']) in phones and p['email'] in emails and org == p['company']:
            return True, f'contact {pid} complete'
        detail = f'phones={phones} emails={emails} org={org!r}'
    return False, detail if sim.contacts_named(p['first'], p['last']) else 'no contact'


def _check_two_phones(p, stats):
    for pid in sim.contacts_named(p['first'], p['last']):
        phones = [_digits(v) for v in sim.contact_values(pid, 3)]
        if _digits(p['mobile']) in phones and _digits(p['work']) in phones:
            return True, f'contact {pid} has both numbers'
    return False, 'missing contact or number'


def _check_added_email(p, stats):
    ids = sim.contacts_named(p['first'], p['last'])
    ok = any(p['email'] in [v.lower() for v in sim.contact_values(pid, 4)] for pid in ids)
    return ok, f'{len(ids)} contact(s), email {"found" if ok else "missing"}'


def _check_company(p, stats):
    orgs = [sim.contact_organization(pid) for pid in sim.contacts_named(p['first'], p['last'])]
    return p['company'] in orgs, f'orgs={orgs}'


def _ensure_contacts(*pairs_keys):
    def setup(p):
        for fk, lk in pairs_keys:
            if not sim.contacts_named(p[fk], p[lk]):
                sim.import_contact(p[fk], p[lk], p.get('old_company'))
    return setup


def _check_reminder(pred, desc):
    def check(p, stats):
        rows = sim.reminders_titled(p['title'])
        return any(pred(r, p) for r in rows), f'{desc}: {rows}'
    return check


def _check_allday(p, stats):
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    events = sim.events_titled(p['title'])
    # All-day events are stored at UTC midnight, so compare dates in UTC.
    ok = any(e['all_day'] and dt.datetime.fromtimestamp(e['start'], dt.timezone.utc).date() == tomorrow for e in events)
    return ok, f'events={events}'


HARD_TASKS: list[Task] = [
    Task(id='h_contact_full', app=CONTACTS, category='hard-form',
         prompt='Create a new contact named {first} {last} with phone number {phone}, email {email}, and company {company}',
         params=lambda k: (lambda f, l: dict(first=f, last=l, phone=f'555{(3_141_592 + k * 6_151) % 10_000_000:07d}',
                                             email=f'{f}.{l}.{k}@example.org'.lower(), company=_COMPANIES[k % 12]))(*_person(k, 20)),
         check=_check_contact_full),
    Task(id='h_contact_two_phones', app=CONTACTS, category='hard-form',
         prompt='Create a new contact named {first} {last} with mobile number {mobile} and work number {work}',
         params=lambda k: (lambda f, l: dict(first=f, last=l, mobile=f'555{(1_618_033 + k * 4_099) % 10_000_000:07d}',
                                             work=f'415{(2_718_281 + k * 3_571) % 10_000_000:07d}'))(*_person(k, 30)),
         check=_check_two_phones),
    Task(id='h_contact_add_email', app=CONTACTS, category='hard-edit',
         prompt="Add the email address {email} to {first} {last}'s existing contact",
         params=lambda k: dict(first=_FIRST[(k + 3) % 12], last=f'Editor{k}', email=f'editor{k}@example.net'),
         setup=_ensure_contacts(('first', 'last')),
         check=_check_added_email),
    Task(id='h_contact_company', app=CONTACTS, category='hard-edit',
         prompt="Change the company on {first} {last}'s contact to {company}",
         params=lambda k: dict(first=_FIRST[(k + 5) % 12], last=f'Mover{k}', old_company='Placeholder Inc',
                               company=_COMPANIES[(k + 4) % 12]),
         setup=_ensure_contacts(('first', 'last')),
         check=_check_company),
    Task(id='h_contact_delete_two', app=CONTACTS, category='hard-delete',
         prompt='Delete the contacts {first} {last} and {first2} {last2}',
         params=lambda k: dict(first=_FIRST[(k + 1) % 12], last=f'Gone{k}', first2=_FIRST[(k + 8) % 12], last2=f'Gone{k}b'),
         setup=_ensure_contacts(('first', 'last'), ('first2', 'last2')),
         check=lambda p, s: (not sim.contacts_named(p['first'], p['last']) and not sim.contacts_named(p['first2'], p['last2']),
                             f"{len(sim.contacts_named(p['first'], p['last']))}+{len(sim.contacts_named(p['first2'], p['last2']))} left")),
    Task(id='h_reminder_in_list', app=REMINDERS, category='hard-multi',
         prompt='Create a new reminders list called "{name}" and add a reminder "{title}" to it',
         params=lambda k: dict(name=f'{_LIST_A[(k + 3) % 8]} {_LIST_B[(k + 1) % 4]} L{k}',
                               title=f'{_ERRAND_VERB[k % 3]} {_ERRAND_OBJ[(k + 7) % 12]} in-list {k}'),
         check=_check_reminder(lambda r, p: r['list'] == p['name'], 'reminders')),
    Task(id='h_reminder_two', app=REMINDERS, category='hard-multi',
         prompt='Create two reminders: "{title}" and "{title2}"',
         params=lambda k: dict(title=f'{_ERRAND_VERB[(k + 2) % 3]} {_ERRAND_OBJ[(k + 3) % 12]} first {k}',
                               title2=f'{_ERRAND_VERB[k % 3]} {_ERRAND_OBJ[(k + 9) % 12]} second {k}'),
         check=lambda p, s: (bool(sim.reminders_titled(p['title'])) and bool(sim.reminders_titled(p['title2'])),
                             f"{len(sim.reminders_titled(p['title']))}+{len(sim.reminders_titled(p['title2']))} found")),
    Task(id='h_reminder_flagged', app=REMINDERS, category='hard-form',
         prompt='Create a reminder called "{title}" and flag it',
         params=lambda k: dict(title=f'{_ERRAND_VERB[(k + 1) % 3]} {_ERRAND_OBJ[(k + 5) % 12]} flag {k}'),
         check=_check_reminder(lambda r, p: r['flagged'] == 1, 'reminders')),
    Task(id='h_reminder_note', app=REMINDERS, category='hard-form',
         prompt='Create a reminder called "{title}" with the note "{note}"',
         params=lambda k: dict(title=f'{_ERRAND_VERB[k % 3]} {_ERRAND_OBJ[(k + 2) % 12]} note {k}', note=_NOTES[k % 6]),
         check=_check_reminder(lambda r, p: p['note'].lower() in r['notes'].lower(), 'reminders')),
    Task(id='h_settings_two_pages', app=SETTINGS, category='hard-multi',
         prompt='Turn on Bold Text and Reduce Motion',
         setup=_reset_a11y, check=_all_keys_on('EnhancedTextLegibilityEnabled', 'ReduceMotionEnabled')),
    Task(id='h_settings_three_pages', app=SETTINGS, category='hard-multi',
         prompt='Turn on Increase Contrast, turn on Speak Selection, and turn on Dark Appearance in the Developer settings',
         setup=_reset_a11y, check=_all_keys_on('DarkenSystemColors', 'QuickSpeak', dark=True)),
    Task(id='h_calendar_allday', app=CALENDAR, category='hard-form',
         prompt='Create an all-day calendar event called "{title}" for tomorrow',
         params=lambda k: dict(title=f'{_EVENT_A[(k + 2) % 8]} day {_EVENT_B[k % 4]} {k}'),
         check=_check_allday),
    Task(id='h_daniel_phones', app=CONTACTS, category='hard-lookup',
         prompt='How many phone numbers does Daniel Higgins have? Report the count.',
         check=lambda p, s: ((lambda t: ('3' in t or 'three' in t.lower()))(_summary(s)), f'summary={_summary(s)[:100]!r}')),
]

TASKS_BY_ID.update({t.id: t for t in HARD_TASKS})
SUITES = {'base': TASKS, 'hard': HARD_TASKS, 'all': TASKS + HARD_TASKS}
