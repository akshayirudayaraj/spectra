"""Baseline: Google's screenshot-only Computer Use model driving the simulator.

Follows the reference agent loop: send the task and a screenshot, execute the
function calls the model makes (coordinates on a 0-999 grid), answer each with a
fresh screenshot, and stop when the model replies without a function call. Only
the most recent screenshots stay in the history, as in Google's sample agent.
"""
from __future__ import annotations

import io
import os
import subprocess
import time

import wda
from google import genai
from google.genai import types
from PIL import Image

MODEL = os.environ.get('SPECTRA_CU_MODEL', 'gemini-2.5-computer-use-preview-10-2025')
_KEEP_SCREENSHOTS = 3
_SETTLE_S = 1.0

_SYSTEM = (
    'You are operating an iPhone (iOS simulator) to complete the user\'s task. '
    'Each turn you get a screenshot. When the task is fully done, reply with a short text summary '
    'of what you did (and any information the user asked for) instead of calling a function. '
    'Use open_app with an app name to launch an app and go_home for the home screen.'
)

_APPS = {
    'settings': 'com.apple.Preferences', 'contacts': 'com.apple.MobileAddressBook',
    'reminders': 'com.apple.reminders', 'calendar': 'com.apple.mobilecal',
    'safari': 'com.apple.mobilesafari', 'maps': 'com.apple.Maps',
}

_CUSTOM_FUNCTIONS = [
    types.FunctionDeclaration(
        name='open_app', description='Launch an installed app by name (e.g. Settings, Contacts, Reminders).',
        parameters_json_schema={'type': 'object', 'properties': {'app_name': {'type': 'string'}}, 'required': ['app_name']}),
    types.FunctionDeclaration(
        name='go_home', description='Go to the home screen.',
        parameters_json_schema={'type': 'object', 'properties': {}}),
]


class _Device:
    def __init__(self, wda_url: str):
        self.c = wda.Client(wda_url)
        size = self.c.window_size()
        self.w, self.h = size.width, size.height

    def pt(self, x, y) -> tuple[int, int]:
        return int(float(x) / 1000 * self.w), int(float(y) / 1000 * self.h)

    def screenshot(self) -> bytes:
        time.sleep(_SETTLE_S)
        png = self.c.screenshot(format='raw')
        # Downscale like the reference agents do; the model works on a 0-999 grid anyway.
        img = Image.open(io.BytesIO(png))
        img = img.resize((img.width // 3, img.height // 3))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    def run(self, name: str, a: dict) -> str:
        if name in ('click_at', 'tap_at', 'tap'):
            x, y = self.pt(a['x'], a['y']); self.c.tap(x, y); return f'tapped {x},{y}'
        if name in ('long_press_at', 'long_press'):
            x, y = self.pt(a['x'], a['y']); self.c.tap_hold(x, y, 1.0); return f'long-pressed {x},{y}'
        if name == 'type_text_at':
            if 'x' in a and 'y' in a:
                x, y = self.pt(a['x'], a['y']); self.c.tap(x, y); time.sleep(0.3)
            if a.get('clear_before_typing'):
                try:
                    self.c.send_keys('\b' * 40)
                except Exception:
                    pass
            text = a.get('text', '')
            self.c.send_keys(text + ('\n' if a.get('press_enter') else ''))
            return f'typed {text!r}'
        if name in ('type_text', 'type'):
            self.c.send_keys(a.get('text', '')); return 'typed'
        if name in ('scroll_document', 'scroll_at', 'scroll', 'swipe'):
            direction = a.get('direction', 'down')
            cx, cy = self.pt(a.get('x', 500), a.get('y', 500))
            d = int(self.h * 0.3)
            dy = {'down': -d, 'up': d}.get(direction, 0)
            dx = {'right': -d, 'left': d}.get(direction, 0)
            self.c.swipe(cx, cy, cx + dx, cy + dy, 0.3)
            return f'scrolled {direction}'
        if name == 'drag_and_drop':
            x, y = self.pt(a['x'], a['y']); x2, y2 = self.pt(a['destination_x'], a['destination_y'])
            self.c.swipe(x, y, x2, y2, 0.5); return 'dragged'
        if name in ('go_back', 'navigate_back'):
            self.c.swipe(2, int(self.h / 2), int(self.w * 0.7), int(self.h / 2), 0.2); return 'swiped back'
        if name == 'go_home':
            self.c.home(); return 'home'
        if name in ('wait_5_seconds', 'wait'):
            time.sleep(5); return 'waited'
        if name == 'open_app':
            app = str(a.get('app_name', a.get('name', ''))).strip().lower()
            bundle = _APPS.get(app, app)
            udid = os.environ.get('SPECTRA_SIM_UDID', 'booted')
            subprocess.run(['xcrun', 'simctl', 'launch', udid, bundle], capture_output=True)
            time.sleep(1.5); return f'opened {bundle}'
        if name == 'key_combination':
            keys = str(a.get('keys', '')).lower()
            if 'enter' in keys or 'return' in keys:
                self.c.send_keys('\n'); return 'pressed enter'
            return f'unsupported keys {keys}'
        return f'unsupported action {name}'


def _response_part(name: str, result: str, png: bytes, extra: dict | None = None) -> types.Part:
    return types.Part(function_response=types.FunctionResponse(
        name=name, response={'result': result, **(extra or {})},
        parts=[types.FunctionResponsePart(inline_data=types.FunctionResponseBlob(mime_type='image/png', data=png))],
    ))


def _trim_screenshots(contents: list[types.Content]) -> None:
    """Drop images from all but the last few function-response turns."""
    seen = 0
    for content in reversed(contents):
        parts = [p for p in content.parts or [] if p.function_response]
        if not parts:
            continue
        seen += 1
        if seen > _KEEP_SCREENSHOTS:
            for p in parts:
                p.function_response.parts = None


def run_computer_use(task: str, max_steps: int = 20, stats: dict | None = None,
                     wda_url: str = 'http://localhost:8100', verbose: bool = True) -> bool:
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    dev = _Device(wda_url)
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM,
        tools=[types.Tool(computer_use=types.ComputerUse(environment=types.Environment.ENVIRONMENT_MOBILE)),
               types.Tool(function_declarations=_CUSTOM_FUNCTIONS)],
    )
    contents = [types.Content(role='user', parts=[
        types.Part(text=task), types.Part(inline_data=types.Blob(mime_type='image/png', data=dev.screenshot()))])]
    usage = {'calls': 0, 'prompt_tokens': 0, 'output_tokens': 0}
    history: list[str] = []
    t0 = time.monotonic()

    def finish(outcome: str, steps: int) -> None:
        if stats is not None:
            stats.update(outcome=outcome, steps=steps, elapsed_s=round(time.monotonic() - t0, 1),
                         history=history, **usage)

    for step in range(1, max_steps + 1):
        response = None
        for attempt in range(6):
            try:
                response = client.models.generate_content(model=MODEL, contents=contents, config=config)
                break
            except Exception as e:
                msg = str(e)
                if ('503' in msg or 'UNAVAILABLE' in msg or '500' in msg) and attempt < 5:
                    time.sleep(min(2 ** (attempt + 1), 30)); continue
                raise
        usage['calls'] += 1
        meta = response.usage_metadata
        if meta:
            usage['prompt_tokens'] += meta.prompt_token_count or 0
            usage['output_tokens'] += meta.candidates_token_count or 0
        cand = response.candidates[0]
        contents.append(cand.content)
        calls = [p.function_call for p in cand.content.parts or [] if p.function_call]
        if not calls:
            text = ''.join(p.text or '' for p in cand.content.parts or [])
            history.append(f'Step {step}: done → DONE: {text.strip()}')
            if verbose:
                print(f'  Step {step}: done — {text.strip()[:200]}', flush=True)
            finish('done', step)
            return True
        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            extra = {}
            decision = args.pop('safety_decision', None)
            if decision:
                extra['safety_acknowledgement'] = 'true'  # eval tasks are user-requested
            try:
                result = dev.run(fc.name, args)
            except Exception as e:
                result = f'error: {e}'
            history.append(f'Step {step}: {fc.name} {args} → {result}')
            if verbose:
                print(f'  Step {step}: {fc.name} {args} → {result}', flush=True)
            parts.append((fc.name, result, extra))
        png = dev.screenshot()
        contents.append(types.Content(role='user', parts=[_response_part(n, r, png, e) for n, r, e in parts]))
        _trim_screenshots(contents)

    finish('timeout', max_steps)
    return False
