# Spectra — Agent Build Guide

**Read `Spectra_PRD_Complete.md` for full specs. This file is the condensed quick-start.**

## What You're Building

An iOS mobile agent that reads accessibility trees (not screenshots) to control apps. Python, facebook-wda, Claude API.

## Architecture

```
┌─────────────────────┐         WebSocket          ┌──────────────────┐
│  Spectra iOS App     │ ◄──────────────────────►  │  Python Backend   │
│  (SwiftUI)           │    ws://localhost:8765     │  (FastAPI + WS)   │
│                      │                            │                   │
│  • Mic / text input  │   Commands ──────►         │  • TaskRouter      │
│  • Plan approval     │                            │  • PlanPreview     │
│  • Confirmations     │   ◄────── Status updates   │  • Agent Loop      │
│  • Notifications     │   ◄────── Confirm requests │  • Memory/Gates    │
│  • Results display   │                            │  • TreeReader      │
│                      │                            │  • Planner (Gemini)│
│  (runs on simulator) │                            │  • Executor (WDA)  │
└─────────────────────┘                            └──────────────────┘
```

**Three terminals needed:**
1. WDA: `xcodebuild ... test` (port 8100)
2. WebSocket server: `uvicorn server.ws_server:app --host 0.0.0.0 --port 8765`
3. iOS app: built and installed via Xcode

## Files to Build (in order)

| Priority | File | What It Does |
|----------|------|-------------|
| 1 | `core/tree_parser.py` | XML → compact `[ref] Type "label"` text + ref_map with coordinates |
| 2 | `core/tree_reader.py` | Wraps WDA + tree_parser + screenshot fallback |
| 3 | `core/planner.py` | Claude API with 12 tools, system prompt, prompt caching |
| 4 | `core/executor.py` | Tool calls → WDA HTTP commands |
| 5 | `core/stuck_detector.py` | Detects loops (3x same screen, 3x same action) |
| 6 | `core/memory.py` | Key-value store for cross-app data |
| 7 | `core/gates.py` | Pauses before "Send"/"Buy"/"Delete" actions |
| 8 | `core/takeover.py` | Pause agent, give user manual control, resume |
| 9 | `core/plan_preview.py` | Generate step plan for complex tasks, user approves |
| 10 | `core/router.py` | "order food" → opens DoorDash; "get a ride" → opens Uber |
| 11 | `core/background.py` | Run agent loop in background thread with callbacks |
| 12 | `core/agent.py` | Main orchestrator — ties everything together |
| 13 | `server/ws_server.py` | FastAPI WebSocket server bridging iOS app ↔ agent backend |
| 14 | `ios/Spectra/` | SwiftUI app: HomeView, TaskRunningView, ConfirmationSheet, ResultView |
| 15 | `ios/Spectra/Services/WebSocketService.swift` | WebSocket client connecting to ws://localhost:8765/ws |
| 16 | `ios/Spectra/Services/SpeechService.swift` | iOS SFSpeechRecognizer for voice input |
| 17 | `ios/Spectra/Services/NotificationService.swift` | UNUserNotificationCenter for background notifications |
| 18 | `recorder/recorder.py` | Append actions to .spectra JSONL |
| 19 | `recorder/replayer.py` | Replay .spectra file with element matching |
| 20 | `recorder/matcher.py` | Exact → fuzzy → position element matching |

## Critical Data Contracts

### ref_map (passed from TreeReader → Executor)

```python
ref_map: dict[int, dict] = {
    1: {
        'type': 'XCUIElementTypeCell',    # Full XCUIElementType string
        'label': 'Wi-Fi',                 # Element label/name
        'value': 'Connected',             # Element value (may be empty)
        'x': 0,                           # Position x (pixels)
        'y': 200,                         # Position y (pixels)
        'width': 390,                     # Element width (pixels)
        'height': 44,                     # Element height (pixels)
    },
    2: { ... },
}
```

### metadata (returned by TreeReader.snapshot())

```python
metadata: dict = {
    'app_name': 'Settings',              # Current foreground app
    'keyboard_visible': False,           # XCUIElementTypeKeyboard present
    'alert_present': False,              # XCUIElementTypeAlert present
    'perception_mode': 'tree',           # 'tree' or 'screenshot'
    'screenshot_b64': None,              # Base64 PNG if fallback triggered
}
```

### Planner action (returned by Planner.next_action())

```python
action: dict = {
    'name': 'tap',                       # Tool name
    'input': {                           # Tool parameters (schema varies by tool)
        'ref': 4,
        'reasoning': 'Tapping Wi-Fi to open settings'
    }
}
```

## How Tapping Works

1. WDA XML includes `x`, `y`, `width`, `height` on EVERY element — always present, always accurate
2. `tree_parser.py` stores these in `ref_map` keyed by ref number
3. Claude only sees `[4] Cell "Wi-Fi"` — never sees coordinates
4. Claude returns `{tool: "tap", ref: 4}`
5. Executor looks up ref 4 → taps center point: `(x + width/2, y + height/2)`

**Edge cases:**
- Off-screen elements DON'T EXIST in the tree (cell recycling) — must scroll first
- Elements behind alerts have stale coordinates — handle alerts first
- Zero-size elements (`width=0` or `height=0`) must be filtered out — not tappable

## Tree Parser Filtering Rules

**Skip:** StatusBar, ScrollBar, Key, Keyboard, PageIndicator, invisible (`visible="false"`), zero-size (`width=0` or `height=0`), unlabeled Other/Group containers (but recurse into children)

**Keep interactive:** Button, TextField, SecureTextField, SearchField, TextArea, Switch, Slider, Link, Cell, Tab, SegmentedControl

**Keep structural:** NavigationBar, TabBar, Alert, Sheet

**Output format:**
```
[1] NavBar "Settings"
[2] Cell "Wi-Fi" → "Connected"
[3] Cell "Bluetooth" → "On"
[4] Switch "Airplane Mode" → "0" [disabled]
```

## All 12 LLM Tools (for planner.py)

| Tool | Key Params | When Used |
|------|-----------|-----------|
| `tap` | ref | Tap element by ref number (primary mode) |
| `tap_xy` | x, y | Tap coordinates (screenshot fallback only) |
| `type_text` | ref, text | Type into text field |
| `scroll` | direction (up/down) | Reveal off-screen content |
| `go_back` | — | Navigate back |
| `go_home` | — | Press home button |
| `wait` | seconds (1-5) | Wait for loading |
| `remember` | key, value | Store value in cross-app memory |
| `handoff` | reason | Pause for user (passwords, payment) |
| `plan` | steps[] | Generate action plan for complex tasks |
| `done` | summary | Task complete |
| `stuck` | reason | Cannot proceed |

Full JSON schemas are in `Spectra_PRD_Complete.md` Section 5.3.

## System Prompt Key Sections

The system prompt (in `planner.py`) must teach Claude:

1. **How to read the tree** — refs regenerate every turn, never reuse old ones
2. **iOS patterns** — nav bars, tab bars, alerts are modal, keyboard behavior, scrollable containers
3. **Memory** — use `remember` to store values across app switches, memory appears in MEMORY section
4. **Safety** — NEVER enter passwords (use `handoff`), before tapping "Send"/"Buy"/"Delete" explain reasoning
5. **Planning** — use `plan` tool first for complex multi-app tasks
6. **Rules** — one action per turn, scroll before giving up, handle alerts first, verify before `done`

## Confirmation Gate Trigger Labels

These element labels (case-insensitive substring match) trigger a user confirmation prompt before execution:

```python
SENSITIVE_LABELS = [
    'send', 'submit', 'place order', 'confirm order', 'pay',
    'purchase', 'buy now', 'delete', 'remove', 'book ride',
    'confirm booking', 'checkout',
]
```

Also trigger on: SecureTextField elements (password fields), any element where planner reasoning mentions "send", "purchase", "confirm", "pay".

## Task Router App Registry

```python
APP_REGISTRY = {
    'rideshare': [
        {'name': 'Uber', 'bundle_id': 'com.ubercab.UberClient'},
        {'name': 'Lyft', 'bundle_id': 'com.zimride.instant'},
    ],
    'food_delivery': [
        {'name': 'DoorDash', 'bundle_id': 'com.doordash.DriverApp'},
        {'name': 'Uber Eats', 'bundle_id': 'com.ubercab.UberEats'},
    ],
    'grocery': [
        {'name': 'Instacart', 'bundle_id': 'com.instacart.client'},
    ],
    'messaging': [
        {'name': 'Messages', 'bundle_id': 'com.apple.MobileSMS'},
    ],
    'settings': [
        {'name': 'Settings', 'bundle_id': 'com.apple.Preferences'},
    ],
}
```

Open apps via: `xcrun simctl launch booted {bundle_id}`

## WDA Connection

```python
import wda
client = wda.Client('http://localhost:8100')

# Get accessibility tree
xml = client.source()            # Raw XML string

# Actions
client.tap(x, y)                 # Tap coordinates
client.send_keys('text')         # Type text
client.swipe_up()                # Scroll down (counterintuitive)
client.swipe_down()              # Scroll up
client.swipe(0.05, 0.5, 0.8, 0.5, duration=0.3)  # Left-edge swipe (go back)
client.home()                    # Home button
client.screenshot()              # Returns PNG bytes
```

## WebSocket Protocol (server ↔ iOS app)

**iOS app → Python server:**
```json
{"type": "command", "task": "Turn on Dark Mode"}
{"type": "command_voice", "audio_b64": "..."}
{"type": "confirm", "approved": true}
{"type": "plan_approve", "approved": true}
{"type": "takeover_done"}
{"type": "stop"}
```

**Python server → iOS app:**
```json
{"type": "status", "step": 3, "total": 15, "action": "tap", "detail": "Tapped 'Wi-Fi'", "app": "Settings"}
{"type": "memory_update", "key": "uber_price", "value": "$18.50"}
{"type": "plan_preview", "steps": ["Open Uber", "Find price", "..."], "task": "Compare rides"}
{"type": "confirm_request", "action": "tap", "label": "Book ride", "app": "Lyft", "detail": "Lyft ride $15.00"}
{"type": "handoff_request", "reason": "Password entry required"}
{"type": "done", "success": true, "summary": "Booked Lyft for $15.00", "steps": 8, "duration": 12.3}
{"type": "stuck", "reason": "Cannot find checkout button"}
{"type": "error", "message": "WDA connection lost"}
```

## Testing Checklist

After building each module, verify:

- [ ] `tree_parser.py`: Settings screen produces 20-40 refs, < 500 tokens, no zero-size elements
- [ ] `tree_reader.py`: Returns `perception_mode: 'tree'`, correct `keyboard_visible` and `alert_present`
- [ ] `planner.py`: Given a tree + task, returns a valid tool call (not chatty text)
- [ ] `executor.py`: `tap` hits correct coordinates, `type_text` focuses field first, `scroll` works in correct direction
- [ ] `stuck_detector.py`: Triggers after 3 identical tree hashes
- [ ] `memory.py`: Store and recall works, `format_for_prompt()` produces readable text
- [ ] `gates.py`: Triggers on "Send" button, doesn't trigger on "Wi-Fi" cell
- [ ] `agent.py`: "Turn on Dark Mode" completes in < 5 steps on Settings app
- [ ] `ws_server.py`: Accepts WebSocket connection, receives command, sends status updates
- [ ] iOS app: Connects to WebSocket, sends command, displays status updates and confirmations

## iOS App Design Reference

**Brand colors:**
- Primary purple: `#534AB7` (mic button, accents, progress)
- Purple tint: `#EEEDFE` (memory pills, highlights)
- Success green: `#1D9E75` (completed steps, done)
- Warning amber: `#BA7517` badge text, `#FAEEDA` badge bg
- Danger red: `#E24B4A` (stop button, errors)

**Screens:**
1. **HomeView** — chat-style task history, large purple mic button (56pt circle), text input bar at bottom
2. **TaskRunningView** — plan checklist (green check / amber current / gray upcoming), memory pills (purple tint), live action feed, stop button
3. **ConfirmationSheet** — bottom sheet with action details, Cancel (outline) + Confirm (purple fill) buttons
4. **ResultView** — green checkmark, summary, stats pills, "New task" button

**Notifications (UNUserNotificationCenter):**
- Progress: silent, "Step 3/8: Tapped 'Display & Brightness'"
- Memory: silent, "Remembered: uber_price = $18.50"
- Confirmation: with sound, "Approval needed: Book Lyft ride for $15.00?" — deep-links to app
- Completion: with sound, green icon, "Done! Booked Lyft for $15.00"

**SF Symbols used:** mic.fill, arrow.up, chevron.left, checkmark, exclamationmark.triangle, xmark, stop.fill
- [ ] `ws_server.py`: Accepts WebSocket connection, receives command, streams status updates
- [ ] iOS app: Connects to ws://localhost:8765/ws, sends command, receives status updates

---

## iOS App + WebSocket Architecture

The frontend is a native SwiftUI app on the simulator. It talks to the Python backend over WebSocket.

```
┌─────────────────────┐         WebSocket          ┌──────────────────┐
│  Spectra iOS App     │ ◄──────────────────────►  │  Python Backend   │
│  (SwiftUI)           │    ws://localhost:8765     │  (FastAPI + WS)   │
│                      │                            │                   │
│  • Mic input         │   Commands ──────►         │  • TaskRouter      │
│  • Chat UI           │                            │  • PlanPreview     │
│  • Plan approval     │   ◄────── Status updates   │  • Agent Loop      │
│  • Confirmation UI   │   ◄────── Confirmations    │  • Memory/Gates    │
│  • Notifications     │                            │  • TreeReader      │
│  • Results display   │                            │  • Planner (Gemini)│
│                      │                            │  • Executor (WDA)  │
└─────────────────────┘                            └──────────────────┘
```

### WebSocket Messages (FROM iOS app → Python)

```json
{"type": "command", "task": "Turn on Dark Mode"}
{"type": "command_voice", "audio_b64": "..."}
{"type": "confirm", "approved": true}
{"type": "stop"}
{"type": "plan_approve", "approved": true}
{"type": "takeover_done"}
```

### WebSocket Messages (FROM Python → iOS app)

```json
{"type": "status", "step": 3, "total": 15, "action": "tap", "detail": "Tapped 'Wi-Fi'", "app": "Settings"}
{"type": "memory_update", "key": "uber_price", "value": "$18.50"}
{"type": "plan_preview", "steps": ["Open Uber", "Find price", ...]}
{"type": "confirm_request", "action": "tap", "label": "Book ride", "detail": "Lyft for $15.00"}
{"type": "handoff_request", "reason": "Password entry required"}
{"type": "done", "success": true, "summary": "Booked Lyft for $15.00", "steps": 8, "duration": 12.3}
{"type": "error", "message": "WDA connection lost"}
```

### iOS App Screens

| Screen | File | Triggered By |
|--------|------|-------------|
| Home | HomeView.swift | App launch, "New task" button |
| Task Running | TaskRunningView.swift | Command sent to backend |
| Confirmation | ConfirmationSheet.swift | `confirm_request` or `handoff_request` from backend |
| Result | ResultView.swift | `done` message from backend |

### Notification Types

| Type | Sound | Deep-links? | Purpose |
|------|-------|------------|---------|
| Progress | Silent | No | "Step 3/8: Tapped Display & Brightness" |
| Memory | Silent | No | "Remembered: uber_price = $18.50" |
| Confirmation | Default | Yes → Spectra app | "Approval needed: Book Lyft for $15.00?" |
| Handoff | Default | Yes → Spectra app | "Your turn: enter password" |
| Completion | Default | Yes → Spectra app | "Done! Booked Lyft for $15.00" |
| Error | Default | Yes → Spectra app | "Stuck: cannot find checkout" |

### Running the Full Stack

Terminal 1: WDA
Terminal 2: `uvicorn server.ws_server:app --host 0.0.0.0 --port 8765`
Terminal 3: Open Xcode → Run Spectra app on simulator (Cmd+R)
