# Spectra — iOS Mobile Agent

## Product Requirements Document & System Architecture

**Author:** Krish Maheshwari
**Version:** 1.0
**Team:** 4 engineers
**Format:** 36-hour hackathon + 8 hours pre-work
**Stack:** Python 3.11+, facebook-wda, Claude API, iOS Simulator

---

## 1. Executive Summary

### 1.1 What Is Spectra?

Spectra is an AI agent that controls iOS apps by reading the accessibility tree — the same structured data screen readers use — instead of taking screenshots. You tell it what to do in plain English (or by voice), and it navigates apps on your iPhone autonomously.

Every iOS app exposes a structured, semantic map of its UI through the accessibility tree. Buttons have names, text fields have labels, switches have states. This is the data VoiceOver uses to help blind users. Today's AI agents (Anthropic Computer Use, OpenAI CUA) ignore this data and instead screenshot the screen, send the image to a vision model at roughly 3,000–5,000 tokens per frame, and guess where to click by pixel coordinates. That approach is slow, expensive, and breaks when a button moves 20 pixels.

Spectra reads the accessibility tree instead. It gets a structured list of every interactive element — name, type, position, state — in roughly 200–500 tokens. It sends this to Claude, which decides what to tap, type, or scroll, and executes the action. Same result, 10x cheaper, 5x faster, and it does not break on UI changes because it targets elements by name, not coordinates. When the tree is unavailable or too sparse (fewer than 3 interactive elements), Spectra automatically falls back to screenshot-based perception using Claude's vision capabilities, so it can still operate on canvas views, games, or apps with poor accessibility support.

### 1.2 Three Demo Modes

- **Text command:** User types "turn on Dark Mode" and watches the agent navigate Settings autonomously.
- **Voice command:** Same loop but triggered by speaking a natural language instruction.
- **Record and replay:** The agent records what it did as a script file, then replays it deterministically without any LLM calls.

### 1.3 Why This Matters

| Metric | Screenshot Agents | Spectra |
|--------|-------------------|---------|
| Tokens per step | 3,000–5,000 | 200–500 |
| Speed per action | 2–5 seconds | 0.3–0.8 seconds |
| Resilience to UI changes | Breaks on pixel shifts | Targets elements by name |
| Cost per 100-action session | $5–10 | $1–2 |

---

## 2. Problem Statement

### 2.1 The User Problem

People spend 4+ hours daily on their phones doing repetitive tasks: ordering food, scheduling appointments, filling forms, managing messages, organizing photos. Every one of these tasks involves the same pattern: open an app, navigate to the right screen, tap the right elements, type the right text, confirm. It is tedious, predictable, and automatable.

### 2.2 Why Current Solutions Fail

**Screenshot-based agents (Anthropic Computer Use, OpenAI CUA)** are slow, expensive at 3,000+ tokens per screenshot, and brittle to UI changes. They send full screenshots to vision models and guess coordinates — if a button moves 20 pixels, the agent breaks.

**Developer testing tools (Appium, XCUITest)** require a Mac, Xcode, provisioning profiles, and are designed for QA engineers, not end users. The setup friction alone eliminates consumer use cases.

**Platform-native automation** is limited. Google is building Gemini-powered UI automation into Android 17, but nothing equivalent exists for iOS. Apple Intelligence and App Intents only work within Apple's own narrow scope — you cannot automate third-party app flows.

### 2.3 The Core Insight

Every iOS app already exposes a structured, semantic representation of its UI through the accessibility tree. This is the same data VoiceOver uses to help blind users navigate apps. An agent that reads accessibility trees instead of screenshots can: identify elements by role and name rather than pixel coordinates; interact deterministically using stable references; consume 10–50x fewer tokens than vision-based approaches; and operate faster and more reliably. No one has built a consumer-facing iOS agent around this.

---

## 3. Solution Overview

### 3.1 How Spectra Works

Spectra operates in a continuous observe-think-act loop:

- **Observe:** The Tree Reader pulls the accessibility tree XML from WebDriverAgent, filters roughly 2,000 raw elements down to roughly 30 interactive ones, and assigns stable reference numbers: [1], [2], [3]. Output is roughly 200–500 tokens of compact text. If the tree extraction fails or returns fewer than 3 interactive elements, the reader automatically captures a screenshot as fallback.
- **Think:** The LLM Planner sends the compact tree, the user's task, and recent action history to Claude via tool_use. Claude returns a structured action like {tool: "tap", ref: 4}. In screenshot fallback mode, Claude uses vision to return coordinate-based actions instead.
- **Act:** The Action Executor translates the tool call into a WDA REST command — tap by coordinates from the ref_map, type text, scroll, or handle alerts. It then waits 800ms for the UI to settle.
- **Loop:** Re-snap the tree and repeat until the task is complete or the agent gets stuck. Maximum 15 steps per task.

### 3.2 Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| iOS automation layer | WDA + facebook-wda (no Appium) | Direct HTTP to WDA, no middleware overhead, Python-native |
| LLM | Claude Sonnet via tool_use | Structured JSON output with zero parse errors, fast enough for real-time |
| Perception | Accessibility tree (primary), screenshot fallback | 10x fewer tokens via tree; screenshot fallback when tree extraction fails or returns < 3 interactive elements |
| Simulator vs. device | Simulator only | No code signing, no provisioning profiles, zero setup friction |
| Language | Python 3.11+ | facebook-wda is Python-only, fastest prototyping speed |

### 3.3 Competitive Landscape

| Company | Approach | iOS Support | Differentiation from Spectra |
|---------|----------|-------------|------------------------------|
| Anthropic Computer Use | Screenshots + vision | Desktop only | Spectra uses accessibility tree, 10x cheaper |
| OpenAI CUA | Screenshots + vision | Desktop only | Same fundamental limitation as Anthropic |
| Droidrun | Accessibility tree, structured text | Bolt-on (ios-portal) | Android-first; Spectra is iOS-native |
| Minitap/mobile-use | Multi-agent decomposition | Via platform adapter | Spectra is simpler, single-agent loop |
| Callstack agent-device | Snapshot + refs CLI | Experimental | Spectra adds voice, recording, replay |
| Google (Android 17) | Gemini UI automation | None | Platform-locked to Android |

---

## 4. System Architecture

### 4.1 Architecture Diagram

The system follows a layered pipeline architecture with four primary modules and three auxiliary modules:

```
User command (text or voice)
        │
        v
┌──────────────────┐
│   Task Router     │  Classifies intent → picks target app(s)
│                   │  Detects multi-app / comparison tasks
└────────┬─────────┘
         │
         v
┌──────────────────┐
│   Plan Preview    │  For complex tasks: generates step plan
│                   │  User approves / edits before execution
└────────┬─────────┘
         │
         v
┌──────────────────┐
│   Tree Reader     │  Pulls accessibility tree XML from WDA
│                   │  Filters ~2,000 elements → ~30 interactive
│                   │  Assigns stable refs: [1], [2], [3]...
│                   │  Output: ~200-500 tokens of compact text
│                   │
│   FALLBACK:       │  If WDA fails or tree has < 3 elements:
│   Screenshot      │  Takes screenshot via WDA, sends to Claude
│                   │  Vision model identifies elements + coords
└────────┬─────────┘
         │
         v
┌──────────────────┐
│   LLM Planner    │  Claude API with tool_use (12 tools)
│                   │  Receives: tree + task + history + memory
│                   │  Returns: structured action
└────────┬─────────┘
         │
         v
┌──────────────────┐
│  Safety Layer     │  Confirmation gates (send/buy/delete)
│                   │  User takeover for passwords/payment
└────────┬─────────┘
         │
         v
┌──────────────────┐
│  Action Executor  │  Translates tool call → WDA REST command
│                   │  Tap, type, scroll, handle alerts
│                   │  Updates cross-app memory
│                   │  Waits for UI to settle
└────────┬─────────┘
         │
         v
    Re-snap tree → loop until task complete or stuck
    (runs in background thread with live progress feed)
```

### 4.2 Module Dependency Graph

```
WDA on Simulator ──→ Tree Reader ──→ Agent Loop (orchestrator)
                          │                    │
                          v                    v
                    Tree Parser          Action Executor
                          │                    │
                          v                    v
                    LLM Planner ──→ End-to-end demo
                          │                │
                     ┌────┼────┐           v
                     v    v    v    Recording / Replay
                  Memory Gates Takeover
                          │
                          v
                    Task Router ──→ Plan Preview
```

Sprints 1–5 are sequential (each depends on the previous). Sprints 6–8 are parallel and can be worked on simultaneously once Sprint 5 is complete.

---

## 5. Module Specifications

This section defines each module's purpose, public API, data contracts, and integration points. Use this as the authoritative reference when implementing or when feeding context to an AI coding agent.

### Quick Reference: Module Map

| Module | File | Depends On | Called By |
|--------|------|-----------|-----------|
| Tree Parser | core/tree_parser.py | (none — pure function) | Tree Reader |
| Tree Reader | core/tree_reader.py | Tree Parser, facebook-wda | Agent Loop |
| LLM Planner | core/planner.py | anthropic SDK | Agent Loop |
| Action Executor | core/executor.py | facebook-wda | Agent Loop |
| Stuck Detector | core/stuck_detector.py | (none — pure logic) | Agent Loop |
| Cross-App Memory | core/memory.py | (none — dict wrapper) | Agent Loop, LLM Planner (via prompt) |
| Plan Preview | core/plan_preview.py | LLM Planner | Agent Loop (before main loop) |
| Confirmation Gates | core/gates.py | (none — pattern matcher) | Agent Loop (between plan and execute) |
| User Takeover | core/takeover.py | (none — input/output) | Agent Loop (on handoff action) |
| Background Runner | core/background.py | Agent Loop, threading | UI / main entry point |
| Task Router | core/router.py | LLM Planner or keyword matching | Agent Loop (before main loop) |
| Voice Input | voice/listener.py | speech_recognition, pyaudio | Main entry point |
| Recorder | recorder/recorder.py | (none — file I/O) | Agent Loop |
| Replayer | recorder/replayer.py | Matcher, Executor | Main entry point |
| Matcher | recorder/matcher.py | (none — pure logic) | Replayer |
| Terminal UI | ui/terminal.py | rich | Agent Loop (via callback) |

### Data Flow: Single-App Task

```
User: "Turn on Dark Mode"
  → TaskRouter.route() → {category: 'settings', apps: [{name: 'Settings'}], multi_app: false}
  → (skip plan preview — simple task)
  → Agent Loop:
      → TreeReader.snapshot() → (compact_tree, ref_map, metadata)
      → Planner.next_action(tree, task, history, metadata, memory) → {name: 'tap', input: {ref: 4}}
      → ConfirmationGate.check(action, ref_map) → false (not sensitive)
      → Executor.run('tap', {ref: 4}, ref_map) → "Tapped [4] 'Display & Brightness'"
      → StuckDetector.record(tree, 'tap', 4)
      → (repeat until done)
```

### Data Flow: Cross-App Comparison Task

```
User: "Compare Uber and Lyft prices to the airport, book the cheapest"
  → TaskRouter.route() → {category: 'rideshare', apps: [Uber, Lyft], multi_app: true, comparison: true}
  → PlanPreview.generate_plan() → ["Open Uber", "Search airport", "Store price", "Open Lyft", "Search airport", "Compare", "Book cheaper"]
  → PlanPreview.present_and_confirm(plan) → (user approves)
  → Executor.open_app('com.ubercab.UberClient')
  → Agent Loop (Uber):
      → ... navigate to price ...
      → Planner returns {name: 'remember', input: {key: 'uber_price', value: '$18.50'}}
      → AgentMemory.store('uber_price', '$18.50')
      → Planner returns {name: 'go_home'}
  → Executor.open_app('com.zimride.instant')
  → Agent Loop (Lyft):
      → ... navigate to price ...
      → Planner sees MEMORY: uber_price=$18.50, compares with Lyft price
      → Planner returns {name: 'tap', input: {ref: 7}} (book button)
      → ConfirmationGate.check() → true! Label matches "Book ride"
      → ConfirmationGate.request_confirmation() → user approves
      → Executor.run('tap', {ref: 7}, ref_map) → "Tapped [7] 'Book ride'"
      → Planner returns {name: 'done', input: {summary: 'Booked Lyft for $15.00 (cheaper than Uber $18.50)'}}
```

### 5.1 Tree Parser (core/tree_parser.py)

#### Purpose

Convert raw WDA accessibility tree XML (roughly 38,000 characters, roughly 2,000 elements) into a compact, ref-tagged format (roughly 300 tokens, roughly 30 elements) that an LLM can consume efficiently.

#### Public API

```python
def parse_tree(xml_string: str) -> tuple[str, dict]:
    """
    Args:
        xml_string: Raw XML from WDA c.source()
    Returns:
        compact_text: Human-readable ref-tagged text
        ref_map: dict mapping ref_number -> {
            type: str,      # e.g. 'XCUIElementTypeButton'
            label: str,     # Element label/name
            value: str,     # Element value (if any)
            x: int,         # Position x
            y: int,         # Position y
            width: int,     # Element width
            height: int     # Element height
        }
    """
```

#### Output Format

```
[1] NavBar "Settings"
[2] Cell "Wi-Fi" → "Connected"
[3] Cell "Bluetooth" → "On"
[4] Cell "General"
[5] Switch "Airplane Mode" → "0" [disabled]
```

#### Filtering Rules

The filter must walk the XML tree recursively and apply these rules:

- **Skip entirely:** StatusBar, ScrollBar, Key, Keyboard, PageIndicator
- **Skip invisible:** Any element where `visible="false"`
- **Skip zero-size:** Any element where `width="0"` or `height="0"` — these are non-visual logical containers that cannot be tapped
- **Skip unlabeled containers:** Type=Other or Group with no label or name attribute — but still recurse into their children
- **Keep interactive:** Button, TextField, SecureTextField, SearchField, TextArea, Switch, Slider, Link, Cell, Tab, SegmentedControl
- **Keep structural (for context):** NavigationBar, TabBar, Alert, Sheet
- **Assign refs:** Sequential [1], [2], [3] numbers to every kept element
- **Short-name types:** XCUIElementTypeButton → Button, XCUIElementTypeCell → Cell, etc.
- **Include state:** Selected, disabled flags and value (if different from label)
- **Indent children:** Show minimal hierarchy for elements inside nav bars, tab bars, alerts

#### Type Short Names

```python
{
    'XCUIElementTypeButton': 'Button',
    'XCUIElementTypeStaticText': 'Text',
    'XCUIElementTypeTextField': 'TextField',
    'XCUIElementTypeSecureTextField': 'SecureField',
    'XCUIElementTypeTable': 'Table',
    'XCUIElementTypeCell': 'Cell',
    'XCUIElementTypeNavigationBar': 'NavBar',
    'XCUIElementTypeTabBar': 'TabBar',
    'XCUIElementTypeSwitch': 'Switch',
    'XCUIElementTypeSlider': 'Slider',
    'XCUIElementTypeAlert': 'Alert',
    'XCUIElementTypeSheet': 'Sheet',
    'XCUIElementTypeSearchField': 'SearchField',
    'XCUIElementTypeImage': 'Image',
    'XCUIElementTypeLink': 'Link',
    'XCUIElementTypeScrollView': 'ScrollView',
}
```

#### Acceptance Criteria

- `parse_tree(xml_string)` returns `(compact_text, ref_map)`
- `compact_text` contains only interactive/meaningful elements with [ref] numbers
- `ref_map` is a dict mapping ref → {type, label, value, x, y, width, height}
- Settings top-level screen produces fewer than 500 tokens
- Tested on at least 3 different app screens (Settings, Messages, Calendar)

---

### 5.2 Tree Reader (core/tree_reader.py)

#### Purpose

Wraps WDA connection, tree extraction, alert detection, keyboard state detection, and screenshot fallback into a single call. This is the interface the agent loop uses to observe the screen. When the accessibility tree is unavailable or too sparse, it automatically falls back to a screenshot-based perception mode.

#### Public API

```python
class TreeReader:
    def __init__(self, wda_url: str = 'http://localhost:8100'):
        """Initialize with WDA server URL."""

    def snapshot(self) -> tuple[str, dict, dict]:
        """
        Returns:
            compact_tree: str   # From parse_tree(), OR screenshot description
            ref_map: dict       # From parse_tree(), OR empty dict in fallback mode
            metadata: {
                'app_name': str,             # Current app name
                'keyboard_visible': bool,     # Keyboard on screen
                'alert_present': bool,        # Alert/sheet visible
                'perception_mode': str,       # 'tree' or 'screenshot'
                'screenshot_b64': str | None, # Base64 PNG if fallback triggered
            }
        """
```

#### Screenshot Fallback Logic

The fallback triggers in two cases:

- **WDA failure:** If `c.source()` throws a connection error or timeout, the reader catches the exception and falls back to `c.screenshot()` instead. The screenshot is captured as a base64-encoded PNG.
- **Sparse tree:** If `parse_tree()` returns a `ref_map` with fewer than 3 interactive elements, the tree is considered too sparse to be useful (likely a canvas view, game, or broken accessibility). The reader captures a screenshot alongside the sparse tree.

When fallback is triggered, the metadata includes `perception_mode: "screenshot"` and `screenshot_b64` with the base64 PNG data. The Planner module uses this to switch from ref-based actions to coordinate-based actions via Claude's vision capabilities.

#### Fallback Pseudocode

```python
def snapshot(self):
    try:
        raw = self.client.source()
        compact, ref_map = parse_tree(raw)
        
        if len(ref_map) < 3:  # Sparse tree fallback
            screenshot_b64 = self._take_screenshot()
            metadata = {
                'perception_mode': 'screenshot',
                'screenshot_b64': screenshot_b64,
                'sparse_tree': compact,  # Include what we got
                ...  # other metadata
            }
            return compact, ref_map, metadata
        
        metadata = {'perception_mode': 'tree', ...}
        return compact, ref_map, metadata
    
    except Exception:  # WDA failure fallback
        screenshot_b64 = self._take_screenshot()
        metadata = {
            'perception_mode': 'screenshot',
            'screenshot_b64': screenshot_b64,
            ...  # other metadata
        }
        return '[screenshot mode - tree unavailable]', {}, metadata

def _take_screenshot(self) -> str:
    import base64
    png_data = self.client.screenshot()
    return base64.b64encode(png_data).decode('utf-8')
```

#### Behavior

- Calls WDA `c.source()` to get raw XML
- Passes raw XML to `parse_tree()` from tree_parser.py
- Checks ref_map size: if fewer than 3 elements, triggers screenshot fallback
- Detects keyboard by checking for `XCUIElementTypeKeyboard` in raw XML
- Detects alerts by checking for `XCUIElementTypeAlert` in raw XML
- Extracts app name from the root `XCUIElementTypeApplication` element
- Handles WDA connection errors gracefully by falling back to screenshot mode
- Sets `perception_mode` in metadata so downstream modules know which mode is active

---

### 5.3 LLM Planner (core/planner.py)

#### Purpose

Send the compact tree, user goal, and action history to Claude and get back a structured action via native tool_use. No text parsing is needed — Claude returns schema-validated JSON.

#### Public API

```python
class Planner:
    def __init__(self, model: str = 'claude-sonnet-4-20250514'):
        """Initialize Claude client with prompt caching."""

    def next_action(
        self,
        tree: str,
        task: str,
        history: list[str],
        metadata: dict,
        warning: str | None = None
    ) -> dict:
        """
        Tree mode (primary). Returns: {
            'name': str,     # Tool name (tap, type_text, etc.)
            'input': dict,   # Tool parameters
        }
        """

    def next_action_vision(
        self,
        screenshot_b64: str,
        tree: str,
        task: str,
        history: list[str],
        metadata: dict,
        warning: str | None = None
    ) -> dict:
        """
        Screenshot fallback mode. Same return format.
        Sends screenshot as image to Claude vision.
        Uses tap_xy tool instead of ref-based tap.
        """
```

#### Tool Definitions

The planner exposes twelve tools to Claude. Each call must use `tool_choice={"type": "any"}` to force action selection and prevent chatty non-action responses.

| Tool | Parameters | Description |
|------|-----------|-------------|
| tap | ref: int, reasoning: str | Tap a UI element by its [ref] number |
| tap_xy | x: int, y: int, reasoning: str | Tap screen coordinates (screenshot fallback mode only) |
| type_text | ref: int, text: str, reasoning: str | Type text into a focused text field |
| scroll | direction: up\|down, reasoning: str | Scroll the screen to reveal content |
| go_back | reasoning: str | Navigate back (back button or left-edge swipe) |
| go_home | reasoning: str | Press home button |
| wait | seconds: 1–5, reasoning: str | Wait for content to load |
| remember | key: str, value: str, reasoning: str | Store a value in memory for later use across app switches |
| handoff | reason: str, resume_hint: str | Pause and hand control to user for sensitive input |
| plan | steps: list[str], reasoning: str | Generate a step-by-step plan for complex tasks |
| done | summary: str | Task is complete |
| stuck | reason: str | Cannot make progress |

#### Complete Tool JSON Schemas

For AI coding agents implementing `core/planner.py` — use these exact schemas:

```python
TOOLS = [
    {
        "name": "tap",
        "description": "Tap a UI element by its ref number from the accessibility tree",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "integer", "description": "Element [ref] number"},
                "reasoning": {"type": "string", "description": "Why this action"}
            },
            "required": ["ref", "reasoning"]
        }
    },
    {
        "name": "tap_xy",
        "description": "Tap screen coordinates directly. Only use in screenshot fallback mode when no ref_map is available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "reasoning": {"type": "string"}
            },
            "required": ["x", "y", "reasoning"]
        }
    },
    {
        "name": "type_text",
        "description": "Type text into a text field. The field will be tapped first to focus it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "integer", "description": "Text field [ref] number"},
                "text": {"type": "string", "description": "Text to type"},
                "reasoning": {"type": "string"}
            },
            "required": ["ref", "text", "reasoning"]
        }
    },
    {
        "name": "scroll",
        "description": "Scroll the screen to reveal more content",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "reasoning": {"type": "string"}
            },
            "required": ["direction", "reasoning"]
        }
    },
    {
        "name": "go_back",
        "description": "Navigate back (tap the back button or left-edge swipe)",
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"}
            },
            "required": ["reasoning"]
        }
    },
    {
        "name": "go_home",
        "description": "Press the home button to return to the home screen",
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"}
            },
            "required": ["reasoning"]
        }
    },
    {
        "name": "wait",
        "description": "Wait for content to load",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 1, "maximum": 5},
                "reasoning": {"type": "string"}
            },
            "required": ["seconds", "reasoning"]
        }
    },
    {
        "name": "remember",
        "description": "Store a value from the current screen for later use. Use when comparing info across apps or remembering something for a future step.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "What this value represents (e.g. 'uber_price')"},
                "value": {"type": "string", "description": "The value to remember (e.g. '$12.50')"},
                "reasoning": {"type": "string"}
            },
            "required": ["key", "value", "reasoning"]
        }
    },
    {
        "name": "handoff",
        "description": "Pause execution and hand control to the user for sensitive input like passwords, payment details, or personal information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "What the user needs to do manually"},
                "resume_hint": {"type": "string", "description": "What to look for when resuming"}
            },
            "required": ["reason"]
        }
    },
    {
        "name": "plan",
        "description": "Generate a step-by-step plan for completing the task. Use FIRST for complex tasks involving multiple apps or more than 5 steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of high-level steps"
                },
                "reasoning": {"type": "string"}
            },
            "required": ["steps", "reasoning"]
        }
    },
    {
        "name": "done",
        "description": "The task is complete. Verify the screen shows the expected result before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "stuck",
        "description": "Cannot make progress on the task",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the agent is stuck"}
            },
            "required": ["reason"]
        }
    }
]
```

#### System Prompt

```python
SYSTEM_PROMPT = """You are Spectra, an iOS mobile agent. You control an iPhone by reading the accessibility tree and performing actions.

CAPABILITIES:
You receive the current screen as a compact accessibility tree. Each interactive element has a [ref] number. Use these refs to specify action targets. Refs change every turn — never reuse old refs.

iOS NAVIGATION:
- Navigation bars at top have back buttons (chevron icon or parent screen name)
- Tab bars at bottom switch between app sections
- Alerts and sheets are modal — handle them before doing anything else
- When a text field is focused, the keyboard appears
- [scrollable] containers have content below the fold — scroll to find more
- "Loading..." or spinners mean wait before acting

MEMORY:
- Use the `remember` tool to store values you'll need later (prices, names, addresses, etc.)
- Stored values appear in the MEMORY section of each turn
- Use memory when comparing information across different apps
- Memory persists across app switches within a single task

SAFETY:
- NEVER enter passwords, payment details, or personal information. Use `handoff` to give control to the user for sensitive input.
- If you see a SecureTextField (password field), ALWAYS use `handoff`.
- Before tapping buttons labeled "Send", "Submit", "Place Order", "Pay", "Purchase", "Delete", or "Book" — pause and explain what you're about to do in your reasoning. The system may ask the user for confirmation.

PLANNING:
- For complex tasks involving multiple apps or more than 5 steps, use the `plan` tool first to outline your approach.
- For simple tasks (single app, < 3 steps), skip planning and act directly.
- You are not rigidly bound to a plan — adapt if the app state differs from expectations.

RULES:
1. Examine the tree carefully before acting. Identify what screen you're on.
2. Choose exactly ONE action per turn.
3. If the target isn't visible, scroll before giving up.
4. If you've repeated the same action 3+ times without progress, try something different.
5. Handle alerts and permission dialogs immediately.
6. Before calling done(), verify the screen shows the expected result.
7. Keep reasoning concise — one sentence."""
```

#### Per-Turn Message Construction

Each turn, the planner constructs a user message. The format adapts based on `perception_mode`:

**Tree mode (default):** The planner sends the compact text tree and ref numbers. Claude returns ref-based actions (tap ref 4).

**Screenshot mode (fallback):** The planner sends the screenshot as a base64 image alongside any sparse tree data available. Claude uses vision to identify elements and returns coordinate-based actions (tap at x=195, y=340). The planner also adds the `tap_xy` tool in this mode.

```
TASK: {user's natural language instruction}

[PLAN: {approved plan steps, if generated}]

[MEMORY:
  uber_price: "$12.50"
  uber_eta: "8 minutes"
]

[Alert warning if alert_present]
[Keyboard warning if keyboard_visible]

SCREEN ({app_name}):
{compact_tree from TreeReader}

RECENT ACTIONS:
  Step 1: tap [4] → Tapped "Wi-Fi"
  Step 2: scroll down → Scrolled down
  ...(last 5 actions only)

[WARNING if stuck detector triggered]
```

#### build_message Implementation

```python
def build_message(
    task: str,
    tree: str,
    history: list[str],
    metadata: dict,
    warning: str | None = None,
    memory: str | None = None,
    plan: list[str] | None = None
) -> str:
    """Construct the per-turn user message for Claude."""
    parts = [f"TASK: {task}"]
    
    if plan:
        plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan))
        parts.append(f"PLAN:\n{plan_text}")
    
    if memory:
        parts.append(f"MEMORY:\n{memory}")
    
    if metadata.get('alert_present'):
        parts.append("⚠️ ALERT is present on screen — handle it first.")
    if metadata.get('keyboard_visible'):
        parts.append("⌨️ Keyboard is visible.")
    
    parts.append(f"SCREEN ({metadata.get('app_name', 'unknown')}):")
    parts.append(tree)
    
    if history:
        parts.append("RECENT ACTIONS:")
        for h in history[-5:]:
            parts.append(f"  {h}")
    
    if warning:
        parts.append(f"WARNING: {warning}")
    
    return "\n\n".join(parts)
```

#### Claude API Call Pattern

```python
from anthropic import Anthropic

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    system=[{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}  # Cache system prompt
    }],
    messages=[{"role": "user", "content": message}],
    tools=TOOLS,
    tool_choice={"type": "any"},  # Force tool selection
    max_tokens=1024
)

# Extract tool call
tool_block = next(b for b in response.content if b.type == "tool_use")
return {"name": tool_block.name, "input": tool_block.input}
```

#### Token Budget Per Turn
|-----------|--------|----------|
| System prompt | ~800 | Cached with prompt caching (pay once) |
| Accessibility tree | 300–2,500 | Interactive-only filtering |
| Action history (last 5) | 200–500 | Compact one-line-per-step format |
| Task + metadata | 100–200 | Fixed overhead |
| Output (reasoning + tool) | 200–400 | Constrained by tool schema |
| Total per turn (tree mode) | ~1,600–4,400 | Well within rate limits |
| Total per turn (screenshot fallback) | ~4,600–7,400 | Higher due to vision tokens (~3,000–5,000 for image) |

---

### 5.4 Action Executor (core/executor.py)

#### Purpose

Translate tool calls from the LLM Planner into WDA REST commands that control the iOS simulator.

#### Public API

```python
class Executor:
    def __init__(self, wda_url: str = 'http://localhost:8100'):
        """Initialize with WDA client."""

    def run(self, action: str, params: dict, ref_map: dict) -> str:
        """
        Args:
            action: Tool name from planner (tap, type_text, etc.)
            params: Tool parameters from planner
            ref_map: Current ref_map from TreeReader
        Returns:
            result: Human-readable result string for history
        """
```

#### Action Implementations

| Action | WDA Command | Details |
|--------|-------------|---------|
| tap | client.tap(x, y) | Look up ref in ref_map, tap center point (x + width/2, y + height/2) |
| tap_xy | client.tap(x, y) | Tap raw screen coordinates directly (screenshot fallback mode) |
| type_text | tap field + client.send_keys(text) | Tap field first to focus, wait 300ms, then send keystrokes |
| scroll down | client.swipe_up() | Swipe up = content scrolls down (counterintuitive) |
| scroll up | client.swipe_down() | Swipe down = content scrolls up |
| go_back | client.swipe(0.05, 0.5, 0.8, 0.5) | Left-edge swipe gesture, or find back button in nav bar |
| go_home | client.home() | Press home button via WDA |
| wait | time.sleep(N) | Wait 1–5 seconds for content to load |
| done | Return summary | Terminal state: task complete |
| stuck | Return reason | Terminal state: cannot proceed |

After every action (except done/stuck), the executor waits 800ms for the UI to settle before the next tree snapshot.

#### Implementation

```python
import time
import wda

class Executor:
    def __init__(self, wda_url: str = 'http://localhost:8100'):
        self.client = wda.Client(wda_url)
    
    def run(self, action: str, params: dict, ref_map: dict) -> str:
        if action == "tap":
            return self._tap(params["ref"], ref_map)
        elif action == "tap_xy":
            return self._tap_xy(params["x"], params["y"])
        elif action == "type_text":
            return self._type(params["ref"], params["text"], ref_map)
        elif action == "scroll":
            return self._scroll(params["direction"])
        elif action == "go_back":
            return self._go_back()
        elif action == "go_home":
            return self._go_home()
        elif action == "wait":
            time.sleep(params.get("seconds", 2))
            return f"Waited {params.get('seconds', 2)}s"
        elif action == "done":
            return f"DONE: {params['summary']}"
        elif action == "stuck":
            return f"STUCK: {params['reason']}"
        elif action == "remember":
            return f"REMEMBER: handled by agent loop"
        elif action == "handoff":
            return f"HANDOFF: handled by agent loop"
        elif action == "plan":
            return f"PLAN: handled by agent loop"
        return f"Unknown action: {action}"
    
    def _tap(self, ref: int, ref_map: dict) -> str:
        el = ref_map.get(ref)
        if not el:
            return f"Error: ref [{ref}] not found"
        x = el['x'] + el['width'] // 2
        y = el['y'] + el['height'] // 2
        self.client.tap(x, y)
        return f"Tapped [{ref}] '{el.get('label', '')}' at ({x},{y})"
    
    def _tap_xy(self, x: int, y: int) -> str:
        self.client.tap(x, y)
        return f"Tapped coordinates ({x},{y})"
    
    def _type(self, ref: int, text: str, ref_map: dict) -> str:
        result = self._tap(ref, ref_map)
        time.sleep(0.3)
        self.client.send_keys(text)
        return f"Typed '{text}' into [{ref}]"
    
    def _scroll(self, direction: str) -> str:
        if direction == "down":
            self.client.swipe_up()   # Swipe up = content scrolls down
        else:
            self.client.swipe_down() # Swipe down = content scrolls up
        return f"Scrolled {direction}"
    
    def _go_back(self) -> str:
        self.client.swipe(0.05, 0.5, 0.8, 0.5, duration=0.3)
        return "Navigated back"
    
    def _go_home(self) -> str:
        self.client.home()
        return "Pressed home"
    
    def open_app(self, bundle_id: str) -> str:
        """Launch an app on the simulator by bundle ID."""
        import subprocess
        subprocess.run(['xcrun', 'simctl', 'launch', 'booted', bundle_id])
        time.sleep(2)
        return f"Opened {bundle_id}"
```

---

### 5.5 Agent Loop (core/agent.py)

#### Purpose

Orchestrate the full observe → think → act cycle. This is the main entry point that ties all modules together.

#### Public API

```python
def run_agent(task: str, max_steps: int = 15) -> bool:
    """
    Execute a natural language task on the iOS simulator.
    Args:
        task: Natural language instruction (e.g. "Turn on Dark Mode")
        max_steps: Maximum actions before timeout (default 15)
    Returns:
        True if task completed (done), False if stuck or timed out
    """
```

#### Loop Pseudocode

```python
def run_task(user_input: str, max_steps: int = 25):
    # 0. Route task to correct app
    route = router.route(user_input)
    
    # 1. Generate and preview plan for complex tasks
    if route['multi_app'] or route['comparison']:
        plan = preview.generate_plan(route['refined_task'])
        approved, plan = preview.present_and_confirm(plan)
        if not approved:
            return False
    
    # 2. Open target app
    if route['apps']:
        executor.open_app(route['apps'][0]['bundle_id'])
    
    # 3. Run agent loop (potentially across multiple apps)
    for step in range(max_steps):
        tree, ref_map, metadata = reader.snapshot()    # Observe
        warning = detector.check()                     # Check stuck
        
        # Think (adapts to perception mode)
        if metadata['perception_mode'] == 'screenshot':
            action = planner.next_action_vision(
                metadata['screenshot_b64'],
                tree, task, history, metadata, warning,
                memory=memory.format_for_prompt()      # Include memory
            )
        else:
            action = planner.next_action(
                tree, task, history, metadata, warning,
                memory=memory.format_for_prompt()      # Include memory
            )
        
        # Handle special actions
        if action['name'] == 'remember':
            memory.store(action['input']['key'], action['input']['value'])
            history.append(f"Stored: {action['input']['key']}={action['input']['value']}")
            continue
        
        if action['name'] == 'handoff':
            takeover.pause(action['input']['reason'])
            takeover.wait_for_resume()
            continue
        
        if action['name'] == 'plan':
            # Mid-task replanning
            continue
        
        # Confirmation gate check
        if gate.check(action, ref_map):
            if not gate.request_confirmation(action, ref_map):
                history.append(f"Step {step}: REJECTED by user")
                continue
        
        # Execute
        result = executor.run(action['name'], action['input'], ref_map)
        history.append(f"Step {step}: {action['name']} → {result}")
        detector.record(tree, action['name'], action['input'].get('ref'))
        
        if action['name'] in ('done', 'stuck'):
            break
        
        time.sleep(0.8)
    
    # 4. If comparison task, switch to next app and repeat
    if route['comparison'] and len(route['apps']) > 1:
        for app in route['apps'][1:]:
            executor.open_app(app['bundle_id'])
            # Continue agent loop for next app...
    
    memory.clear()
```

---

### 5.6 Stuck Detector (core/stuck_detector.py)

#### Purpose

Deterministic loop and stuck detection running outside the LLM. When triggered, it injects a warning into the next prompt to force the agent to change strategy.

#### Public API

```python
class StuckDetector:
    def record(self, tree_text: str, action: str, ref: int = None):
        """Record a step for analysis."""

    def check(self) -> str | None:
        """Returns warning string if stuck, None otherwise."""
```

#### Detection Rules

- **Same screen 3x:** If the MD5 hash of the last 3 tree snapshots are identical, return: "Screen unchanged for 3 actions. Try scrolling or a different element."
- **Same action repeated 3x:** If the last 3 (action, ref) pairs are identical, return: "Same action repeated 3 times. Try a completely different approach."
- **Navigation spam:** If the last 4 actions are all scroll/swipe/wait with no taps, return: "4 consecutive navigation actions without tapping. Interact with a specific element."

#### Implementation

```python
import hashlib

class StuckDetector:
    def __init__(self):
        self.tree_hashes = []
        self.action_history = []
    
    def record(self, tree_text: str, action: str, ref: int = None):
        h = hashlib.md5(tree_text.encode()).hexdigest()[:8]
        self.tree_hashes.append(h)
        self.action_history.append((action, ref))
    
    def check(self) -> str | None:
        # Same screen 3x
        if len(self.tree_hashes) >= 3:
            if len(set(self.tree_hashes[-3:])) == 1:
                return "Screen unchanged for 3 actions. Try scrolling or a different element."
        
        # Same action+ref 3x
        if len(self.action_history) >= 3:
            if len(set(self.action_history[-3:])) == 1:
                return "Same action repeated 3 times. Try a completely different approach."
        
        # Navigation spam — 4 consecutive non-tap actions
        nav_actions = {'scroll', 'swipe', 'wait', 'go_back'}
        if len(self.action_history) >= 4:
            if all(a[0] in nav_actions for a in self.action_history[-4:]):
                return "4 consecutive navigation actions without tapping. Interact with a specific element."
        
        return None
```

---

### 5.7 Voice Input (voice/listener.py)

#### Purpose

Accept voice commands via microphone and feed transcribed text into the agent loop.

#### Public API

```python
def listen() -> str:
    """
    Block until user speaks, then return transcribed text.
    Returns empty string if nothing recognized.
    Uses speech_recognition library with Google STT backend.
    """
```

#### Behavior

- Pressing Enter (or a hotkey) starts listening
- Silence detection (5 second timeout) stops recording
- Transcribed text feeds directly into `run_agent(task)`
- Fallback: if voice fails or user prefers, they can type a command instead

#### Dependencies

`pip install SpeechRecognition pyaudio` — If pyaudio install fails on macOS, use: `brew install portaudio && pip install pyaudio`

---

### 5.8 Recording and Replay (recorder/)

#### Purpose

Record agent flows to .spectra JSONL files and replay them deterministically without LLM calls. This demonstrates that accessibility-tree-based automation can be both intelligent (LLM-driven) and deterministic (scripted).

#### Recording Format (.spectra JSONL)

Each line is a self-contained JSON object:

```json
{
  "step": 1,
  "action": "tap",
  "params": { "ref": 5 },
  "target": {
    "label": "Display & Brightness",
    "type": "XCUIElementTypeCell",
    "x": 201, "y": 385,
    "width": 402, "height": 44
  },
  "tree_hash": "a3f8c921",
  "timestamp": 1711500000.0
}
```

#### Replay Element Matching

During replay, element positions may have shifted. The matcher uses a three-tier strategy:

| Priority | Match Type | Criteria | Confidence |
|----------|-----------|----------|------------|
| 1 | Exact | Same label AND same type | High |
| 2 | Fuzzy | Similar label (substring) AND same type | Medium |
| 3 | Position | Same type within 50px of original position | Low |

If no match meets the minimum threshold, the step is reported as failed. The replay engine produces a final summary: X steps passed, Y fuzzy-matched, Z failed.

#### Files

| File | Purpose |
|------|---------|
| recorder/recorder.py | Append each action to a .spectra JSONL file during agent execution |
| recorder/replayer.py | Load a .spectra file and execute each step sequentially |
| recorder/matcher.py | Weighted multi-signal element matching (exact → fuzzy → position) |

---

### 5.9 Cross-App Memory (core/memory.py)

#### Purpose

Persistent key-value store that the agent uses to remember values across app switches within a single task session. This enables workflows like "compare Uber and Lyft prices and book the cheaper one" — the agent stores the Uber price, switches to Lyft, retrieves the stored price, compares, and acts.

#### Public API

```python
class AgentMemory:
    def __init__(self):
        """Initialize empty memory store."""
    
    def store(self, key: str, value: str) -> str:
        """Store a value. Returns confirmation string."""
    
    def recall(self, key: str) -> str | None:
        """Retrieve a stored value. Returns None if key doesn't exist."""
    
    def recall_all(self) -> dict[str, str]:
        """Return all stored key-value pairs."""
    
    def clear(self) -> None:
        """Clear all memory (called at end of task)."""
    
    def format_for_prompt(self) -> str:
        """Format all stored values as text for injection into the LLM prompt."""
```

#### LLM Tool Definition

Add a `remember` tool to the planner's tool set:

```python
{
    "name": "remember",
    "description": "Store a value from the current screen for later use. Use this when you need to compare information across apps or remember something for a future step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "What this value represents (e.g. 'uber_price', 'lyft_eta')"},
            "value": {"type": "string", "description": "The value to remember (e.g. '$12.50', '8 minutes')"},
            "reasoning": {"type": "string"}
        },
        "required": ["key", "value", "reasoning"]
    }
}
```

#### Integration with Agent Loop

- The agent loop passes `memory.format_for_prompt()` into every planner call
- When the planner returns a `remember` action, the agent loop stores the value and continues (no WDA action needed)
- Memory is injected into the per-turn message under a `MEMORY:` section:

```
MEMORY:
  uber_price: "$12.50"
  uber_eta: "8 minutes"

TASK: Compare Uber and Lyft prices and book the cheaper one
```

- Memory persists for the duration of one task session and is cleared when the task completes or the user starts a new task

#### Implementation

```python
class AgentMemory:
    def __init__(self):
        self._store: dict[str, str] = {}
    
    def store(self, key: str, value: str) -> str:
        self._store[key] = value
        return f"Stored {key}={value}"
    
    def recall(self, key: str) -> str | None:
        return self._store.get(key)
    
    def recall_all(self) -> dict[str, str]:
        return dict(self._store)
    
    def clear(self) -> None:
        self._store.clear()
    
    def format_for_prompt(self) -> str:
        if not self._store:
            return ""
        lines = [f"  {k}: \"{v}\"" for k, v in self._store.items()]
        return "MEMORY:\n" + "\n".join(lines)
```

---

### 5.10 Action Plan Preview (core/plan_preview.py)

#### Purpose

Before executing a multi-step task, the agent generates a high-level plan and presents it to the user for review. The user can approve, edit, or reject the plan before execution begins. This mirrors Google Gemini's behavior of showing an action plan before automating.

#### Public API

```python
class PlanPreview:
    def __init__(self, planner: Planner):
        """Initialize with a Planner instance."""
    
    def generate_plan(self, task: str) -> list[str]:
        """
        Ask Claude to generate a high-level step plan without executing.
        Args:
            task: Natural language instruction
        Returns:
            List of planned steps as human-readable strings
            e.g. ["Open Uber app", "Enter destination: Airport", 
                   "Check price", "Compare with Lyft price from memory"]
        """
    
    def present_and_confirm(self, plan: list[str]) -> tuple[bool, list[str]]:
        """
        Display plan to user and wait for confirmation.
        Returns:
            (approved: bool, modified_plan: list[str])
        """
```

#### LLM Tool Definition

Add a `plan` tool that the planner uses to generate a preview:

```python
{
    "name": "plan",
    "description": "Generate a step-by-step plan for completing the task. Call this FIRST before taking any actions when the task involves multiple apps or more than 3 steps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of high-level steps to complete the task"
            },
            "reasoning": {"type": "string"}
        },
        "required": ["steps", "reasoning"]
    }
}
```

#### Behavior

- For simple tasks (single app, < 3 steps like "Turn on Dark Mode"), the agent skips planning and executes directly
- For complex tasks (cross-app, comparison, ordering), the agent generates a plan first
- The plan is displayed in the terminal UI with numbered steps
- User presses Enter to approve, or types modifications
- The approved plan is injected into the system prompt as context for execution
- The agent is not rigidly bound to the plan — it adapts if the app state differs from expectations

---

### 5.11 Confirmation Gates (core/gates.py)

#### Purpose

The agent automatically pauses and asks for user confirmation before executing irreversible or sensitive actions. This prevents the agent from accidentally sending messages, placing orders, or making payments without human approval.

#### Public API

```python
class ConfirmationGate:
    # Actions that always require confirmation
    SENSITIVE_ACTIONS = {
        'send_message',    # Sending texts, emails
        'place_order',     # Confirming purchases
        'make_payment',    # Payment confirmation
        'delete',          # Deleting content
        'submit_form',     # Submitting forms with personal data
    }
    
    # UI element labels that trigger confirmation
    SENSITIVE_LABELS = [
        'send', 'submit', 'place order', 'confirm order', 'pay',
        'purchase', 'buy now', 'delete', 'remove', 'book ride',
        'confirm booking', 'checkout',
    ]
    
    def check(self, action: dict, ref_map: dict) -> bool:
        """
        Returns True if this action requires user confirmation.
        Checks both the action type and the target element's label.
        """
    
    def request_confirmation(self, action: dict, ref_map: dict) -> bool:
        """
        Display the pending action to the user and wait for yes/no.
        Returns True if user approves, False if user rejects.
        """
```

#### Integration with Agent Loop

The gate check happens between the planner's decision and the executor's action:

```python
action = planner.next_action(...)

# Check if this action needs confirmation
if gate.check(action, ref_map):
    approved = gate.request_confirmation(action, ref_map)
    if not approved:
        # Inject "user rejected this action" into history
        history.append(f"Step {step}: {action['name']} → REJECTED by user")
        continue  # Re-plan

result = executor.run(action['name'], action['input'], ref_map)
```

#### Detection Logic

The gate triggers when either:
- The LLM explicitly calls a sensitive tool name (if we add `send_message` or `place_order` as tool variants)
- The target element's label (from ref_map) matches any entry in `SENSITIVE_LABELS` (case-insensitive substring match)
- The planner's reasoning mentions keywords like "send", "purchase", "confirm", "pay"

---

### 5.12 User Takeover (core/takeover.py)

#### Purpose

Allow the user to pause the agent mid-task, take manual control of the simulator to perform sensitive actions (like entering a password or payment info), and then hand control back to the agent to continue. This matches Google Gemini's "take control" mode.

#### Public API

```python
class TakeoverManager:
    def __init__(self):
        """Initialize takeover state."""
    
    def pause(self, reason: str) -> None:
        """
        Pause the agent loop and notify the user they have control.
        Args:
            reason: Why control is being handed over (e.g. "Password entry required")
        """
    
    def wait_for_resume(self) -> None:
        """
        Block until the user signals they're done (presses Enter).
        """
    
    def is_paused(self) -> bool:
        """Check if agent is currently paused for user takeover."""
```

#### LLM Tool Definition

Add a `handoff` tool:

```python
{
    "name": "handoff",
    "description": "Pause execution and hand control to the user for sensitive input like passwords, payment details, or personal information that should not be handled by the agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "What the user needs to do manually"},
            "resume_hint": {"type": "string", "description": "What the agent should look for when resuming (e.g. 'the payment form should be completed')"}
        },
        "required": ["reason"]
    }
}
```

#### Integration with Agent Loop

```python
if action['name'] == 'handoff':
    takeover.pause(action['input']['reason'])
    # Display: "🤚 Your turn: {reason}. Press Enter when done."
    takeover.wait_for_resume()
    # Agent re-snaps tree and continues from new state
    continue
```

#### When the Agent Should Hand Off

The system prompt instructs Claude to use `handoff` when it encounters:
- Password or login fields (SecureTextField elements)
- Payment forms or credit card entry
- Fields asking for SSN, ID numbers, or other PII
- Any screen the agent cannot safely navigate without personal credentials

---

### 5.13 Background Execution (core/background.py)

#### Purpose

Allow the agent to continue executing tasks while the user can observe progress through notifications/status updates rather than watching every step. For the hackathon (running on simulator via terminal), this means the agent runs non-blocking in a background thread while the terminal UI shows a live progress feed.

#### Public API

```python
class BackgroundRunner:
    def __init__(self):
        """Initialize background execution state."""
    
    def start(self, task: str, callback: callable = None) -> None:
        """
        Launch run_agent in a background thread.
        Args:
            task: Natural language instruction
            callback: Called with (step_num, action, result, status) after each step
        """
    
    def get_status(self) -> dict:
        """
        Returns current execution state:
        {
            'running': bool,
            'current_step': int,
            'last_action': str,
            'last_result': str,
            'task': str,
            'completed': bool,
            'success': bool | None,
        }
        """
    
    def stop(self) -> None:
        """Stop execution after current step completes."""
    
    def is_running(self) -> bool:
        """Check if a task is currently executing."""
```

#### Behavior

- The agent loop runs in a Python `threading.Thread`
- The main thread remains free for user input (pause, stop, new commands)
- A callback fires after each step, feeding the terminal UI with progress updates
- The terminal UI shows a compact progress bar: `Step 4/15: Tapped "Wi-Fi" ✓`
- User can type `stop` or press Ctrl+C to halt execution gracefully
- If a confirmation gate triggers, the background thread blocks and surfaces the prompt to the main thread

#### Hackathon Implementation Note

On the iOS simulator, this is straightforward — WDA commands are HTTP calls that don't block the terminal. The "background" aspect is that the user sees a live status feed rather than watching the full tree dump each step. For a production on-device version, this would map to Android's virtual window concept or an iOS background process.

---

### 5.14 Task Router (core/router.py)

#### Purpose

Interpret high-level user intent and route it to the correct app. When the user says "order food" or "get a ride home," the router determines which app to open and how to frame the task for the agent loop. This removes the need for the user to specify the app name.

#### Public API

```python
class TaskRouter:
    # App registry: maps categories to installed apps
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
    
    def __init__(self, planner: Planner):
        """Initialize with planner for intent classification."""
    
    def route(self, task: str) -> dict:
        """
        Classify user intent and determine target app(s).
        Args:
            task: Natural language instruction
        Returns: {
            'category': str,           # e.g. 'rideshare'
            'apps': list[dict],        # Target app(s) to use
            'refined_task': str,       # Task rewritten for the agent
            'multi_app': bool,         # Whether task requires multiple apps
            'comparison': bool,        # Whether task involves comparing across apps
        }
        """
    
    def detect_installed_apps(self) -> list[str]:
        """
        Query the simulator for installed apps.
        Uses: xcrun simctl listapps or WDA /wda/apps/list
        """
```

#### Intent Classification

The router uses a lightweight Claude call (or keyword matching for speed) to classify the task:

```python
ROUTING_PROMPT = """Classify this task into a category and identify the target app(s).

Categories: rideshare, food_delivery, grocery, messaging, settings, browser, general

Task: "{task}"

Respond with JSON: {{"category": "...", "apps": ["..."], "multi_app": bool, "comparison": bool}}"""
```

#### Integration with Agent Loop

The router runs before the main agent loop:

```python
def run_task(user_input: str):
    route = router.route(user_input)
    
    if route['comparison']:
        # Multi-app comparison flow
        results = {}
        for app in route['apps']:
            executor.open_app(app['bundle_id'])
            result = run_agent(route['refined_task'], memory=memory)
            results[app['name']] = memory.recall_all()
        # Final comparison step
        run_agent(f"Compare results and pick the best: {results}")
    else:
        # Single app flow
        if route['apps']:
            executor.open_app(route['apps'][0]['bundle_id'])
        run_agent(route['refined_task'])
```

#### App Opening

The executor needs a new method to open apps by bundle ID:

```python
def open_app(self, bundle_id: str) -> str:
    """Launch an app on the simulator."""
    import subprocess
    subprocess.run(['xcrun', 'simctl', 'launch', 'booted', bundle_id])
    time.sleep(2)  # Wait for app to launch
    return f"Opened {bundle_id}"
```

---

### 5.15 WebSocket Server (server/ws_server.py)

#### Purpose

Bridge between the SwiftUI iOS app and the Python agent backend. Runs on the Mac, accepts WebSocket connections from the Spectra app on the simulator, receives commands, runs the agent loop, and pushes real-time status updates, confirmation requests, and results back to the app.

#### Public API

```python
# FastAPI + WebSocket server

from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Bidirectional WebSocket connection with the iOS app.
    
    Messages FROM iOS app (JSON):
        {"type": "command", "task": "Turn on Dark Mode"}
        {"type": "command_voice", "audio_b64": "..."}  # base64 audio
        {"type": "confirm", "approved": true}
        {"type": "stop"}
        {"type": "plan_approve", "approved": true, "modified_steps": [...]}
        {"type": "takeover_done"}
    
    Messages TO iOS app (JSON):
        {"type": "status", "step": 3, "total": 15, "action": "tap", "detail": "Tapped 'Wi-Fi'", "app": "Settings"}
        {"type": "memory_update", "key": "uber_price", "value": "$18.50"}
        {"type": "plan_preview", "steps": ["Open Uber", "Find price", ...], "task": "Compare rides"}
        {"type": "confirm_request", "action": "tap", "label": "Book ride", "app": "Lyft", "detail": "Lyft ride for $15.00"}
        {"type": "handoff_request", "reason": "Password entry required"}
        {"type": "done", "success": true, "summary": "Booked Lyft for $15.00", "steps": 8, "duration": 12.3}
        {"type": "stuck", "reason": "Cannot find the checkout button"}
        {"type": "error", "message": "WDA connection lost"}
    """
```

#### Server Startup

```bash
# Run on Mac (not on simulator)
pip install fastapi uvicorn websockets
uvicorn server.ws_server:app --host 0.0.0.0 --port 8765
```

The iOS simulator can reach the Mac's localhost. The Spectra iOS app connects to `ws://localhost:8765/ws`.

#### Integration with Agent Loop

The WebSocket server wraps the existing `BackgroundRunner`. When a command arrives:

1. `TaskRouter.route()` classifies the task
2. If complex, `PlanPreview.generate_plan()` generates a plan → sends `plan_preview` to app → waits for `plan_approve`
3. `BackgroundRunner.start()` launches the agent loop with a callback
4. The callback sends `status` messages to the app after each step
5. If `ConfirmationGate.check()` triggers → sends `confirm_request` → waits for `confirm` response
6. If `handoff` tool is called → sends `handoff_request` → waits for `takeover_done`
7. `AgentMemory.store()` events → sends `memory_update`
8. On completion → sends `done` with summary

---

### 5.16 Spectra iOS App (ios/Spectra/)

#### Purpose

Native SwiftUI app running on the iOS simulator. Provides voice/text input, displays task status via notifications, shows plan previews, handles confirmation gates, and displays results. Communicates with the Python backend over WebSocket.

#### Architecture

```
ios/Spectra/
├── Spectra.xcodeproj
├── Spectra/
│   ├── SpectraApp.swift           # App entry point
│   ├── ContentView.swift          # Root view with tab/navigation
│   ├── Views/
│   │   ├── HomeView.swift         # Chat-style interface with mic button + task history
│   │   ├── TaskRunningView.swift  # Plan checklist, memory display, live action feed
│   │   ├── ConfirmationSheet.swift # Bottom sheet for confirmation gates
│   │   └── ResultView.swift       # Task completion summary
│   ├── Services/
│   │   ├── WebSocketService.swift # WebSocket client connecting to ws://localhost:8765/ws
│   │   ├── SpeechService.swift    # iOS Speech framework for voice input
│   │   └── NotificationService.swift # UNUserNotificationCenter for background notifications
│   ├── Models/
│   │   ├── TaskStatus.swift       # Status update model
│   │   ├── ConfirmationRequest.swift # Confirmation gate model
│   │   ├── PlanStep.swift         # Plan preview step model
│   │   └── MemoryItem.swift       # Cross-app memory key-value model
│   └── Assets.xcassets            # App icon, colors
```

#### Screen Definitions

**Screen 1 — Home (HomeView.swift)**
- Chat-style scrollable list of completed tasks (compact cards with status, steps, timing)
- Large purple mic button (centered) — taps to start iOS Speech recognition
- Text input bar at bottom with send button
- On command: sends `{"type": "command", "task": "..."}` via WebSocket
- On voice: uses `SFSpeechRecognizer` to transcribe, then sends command

**Screen 2 — Task Running (TaskRunningView.swift)**
- Header: task name + "Running" / "Waiting" badge
- Plan checklist: numbered steps with checkmark (done), spinner (current), empty (upcoming)
- Memory section: purple pills showing stored key-value pairs
- Live action feed: scrolling list of completed steps with timestamps
- "Stop task" button at bottom (sends `{"type": "stop"}`)
- Navigated to automatically when task starts

**Screen 3 — Confirmation Sheet (ConfirmationSheet.swift)**
- Bottom sheet (`.sheet` modifier) that slides up when `confirm_request` arrives
- Shows: app name, action description, details (price, comparison data)
- Cancel and Confirm buttons
- Sends `{"type": "confirm", "approved": true/false}` via WebSocket
- Also triggered by `handoff_request` — shows "Your turn: {reason}" with a "Done" button

**Screen 4 — Result (ResultView.swift)**
- Task summary: what was accomplished
- Stats: steps taken, duration, apps used
- Memory values used (if any)
- "New task" button to return to Home

#### Notifications (NotificationService.swift)

Uses `UNUserNotificationCenter` to post local notifications while the Spectra app is in the background (because WDA is controlling other apps on the simulator):

```swift
func postProgress(step: Int, total: Int, detail: String) {
    let content = UNMutableNotificationContent()
    content.title = "Spectra"
    content.body = "Step \(step)/\(total): \(detail)"
    content.sound = nil  // Silent
    // Post immediately
    let request = UNNotificationRequest(identifier: "step-\(step)", content: content, trigger: nil)
    UNUserNotificationCenter.current().add(request)
}

func postConfirmation(action: String, detail: String) {
    let content = UNMutableNotificationContent()
    content.title = "Spectra"
    content.body = "Approval needed: \(action)"
    content.subtitle = detail
    content.sound = .default
    content.categoryIdentifier = "CONFIRMATION"
    // Deep-link back to Spectra app
    let request = UNNotificationRequest(identifier: "confirm", content: content, trigger: nil)
    UNUserNotificationCenter.current().add(request)
}

func postCompletion(summary: String, steps: Int, duration: Double) {
    let content = UNMutableNotificationContent()
    content.title = "Spectra"
    content.body = "Done! \(summary)"
    content.subtitle = "\(steps) steps · \(String(format: "%.1f", duration))s"
    content.sound = .default
    let request = UNNotificationRequest(identifier: "done", content: content, trigger: nil)
    UNUserNotificationCenter.current().add(request)
}
```

#### Notification Types

| Type | When | Icon Color | Sound | Deep-links back? |
|------|------|-----------|-------|-------------------|
| Progress | Each agent step | Purple | Silent | No |
| Memory stored | Agent calls `remember` | Purple | Silent | No |
| Confirmation needed | Confirmation gate triggers | Purple (bold border) | Default | Yes |
| Handoff | Agent calls `handoff` | Purple (bold border) | Default | Yes |
| Completion | Task finishes | Green | Default | Yes |
| Error/Stuck | Agent stuck or WDA fails | Red | Default | Yes |

#### WebSocket Message Flow

```
User taps mic → SpeechService transcribes → WebSocketService sends command
    ↓
Python server receives → runs TaskRouter → sends plan_preview
    ↓
App shows TaskRunningView with plan → user taps approve → sends plan_approve
    ↓
Python runs agent loop → sends status updates → app updates live feed + posts notifications
    ↓
Agent hits "Book ride" button → ConfirmationGate triggers → Python sends confirm_request
    ↓
App posts notification → user taps notification → app shows ConfirmationSheet → user taps Confirm
    ↓
Python continues → agent completes → sends done → app shows ResultView + posts completion notification
```

#### Build and Deploy to Simulator

```bash
cd ios/Spectra
open Spectra.xcodeproj
# In Xcode: select iPhone 17 Pro simulator, hit Cmd+R to build and run
```

Or via command line:
```bash
xcodebuild -project ios/Spectra/Spectra.xcodeproj \
  -scheme Spectra \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  build
xcrun simctl install booted ios/Spectra/build/Debug-iphonesimulator/Spectra.app
xcrun simctl launch booted com.spectra.agent
```

#### Design System

**Colors:**
- Primary brand: `#534AB7` (purple) — mic button, progress bars, plan step indicators, active states
- Success: `#1D9E75` (green) — completed steps, done notifications
- Warning: `#BA7517` (amber) — "Running" / "Waiting" badges
- Danger: `#E24B4A` (red) — stop button, error states, stuck notifications
- Memory pills background: `#EEEDFE` (light purple), text: `#3C3489`
- Card background: `systemBackground`
- Secondary text: `.secondary`
- Borders: `Color(.systemGray5)`

**Typography:**
- Screen titles: `.title2` weight `.semibold`
- Section headers: `.caption` weight `.semibold` color `.secondary`
- Body text: `.subheadline`
- Notification text: `.footnote`
- Stats/numbers: `.title3` weight `.semibold`
- Badges: `.caption2` weight `.semibold`

**Corner radius:** 16pt for cards, 24pt for bottom sheets, full round for mic button and badges

**Spacing:** 12pt between list items, 16pt section padding, 20pt screen padding

#### Screen 1: HomeView.swift — Detailed Layout

```
┌─────────────────────────────────┐
│ "Spectra"              .title2  │
│ "your iOS agent"     .caption   │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ ✓ Completed                 │ │
│ │ Turned on Dark Mode         │ │
│ │ 3 steps · 4.2s · Settings   │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ✓ Completed                 │ │
│ │ Sent "running late" to Mom  │ │
│ │ 6 steps · 8.1s · Messages   │ │
│ └─────────────────────────────┘ │
│                                 │
│    "What can I help you with?"  │
│                                 │
│          ┌──────────┐           │
│          │  🎤 MIC  │  52pt     │
│          │  purple  │  circle   │
│          └──────────┘           │
│                                 │
│ ┌─────────────────────┐ ┌────┐ │
│ │ Type a task...      │ │ ➤  │ │
│ └─────────────────────┘ └────┘ │
└─────────────────────────────────┘
```

**SwiftUI structure:**

```swift
struct HomeView: View {
    @StateObject var vm: HomeViewModel
    @State private var taskText = ""
    @State private var isListening = false
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 4) {
                Text("Spectra").font(.title2).fontWeight(.semibold)
                Text("your iOS agent").font(.caption).foregroundStyle(.secondary)
            }.padding(.top, 20)
            
            // Task history (scrollable)
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(vm.completedTasks) { task in
                        TaskCard(task: task)
                    }
                }.padding(.horizontal, 20)
            }
            
            Spacer()
            
            // Prompt
            Text("What can I help you with?")
                .font(.subheadline).foregroundStyle(.secondary)
                .padding(.bottom, 16)
            
            // Mic button
            Button(action: { vm.toggleListening() }) {
                Circle()
                    .fill(Color(hex: "534AB7"))
                    .frame(width: 56, height: 56)
                    .overlay(
                        Image(systemName: isListening ? "waveform" : "mic.fill")
                            .foregroundColor(.white).font(.title3)
                    )
            }.padding(.bottom, 12)
            
            // Text input
            HStack(spacing: 8) {
                TextField("Type a task...", text: $taskText)
                    .textFieldStyle(.roundedBorder)
                Button(action: { vm.sendCommand(taskText); taskText = "" }) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundColor(Color(hex: "534AB7"))
                }
            }.padding(.horizontal, 20).padding(.bottom, 16)
        }
    }
}
```

**TaskCard component:**

```swift
struct TaskCard: View {
    let task: CompletedTask
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(Color(hex: "1D9E75")).font(.caption)
                Text("Completed").font(.caption).fontWeight(.semibold)
                    .foregroundColor(Color(hex: "1D9E75"))
            }
            Text(task.summary).font(.subheadline)
            Text("\(task.steps) steps · \(task.duration) · \(task.app)")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}
```

#### Screen 2: TaskRunningView.swift — Detailed Layout

```
┌─────────────────────────────────┐
│ ← Compare ride prices  Running  │
│                         (amber) │
│─────────────────────────────────│
│ PLAN                            │
│ ✓ Open Uber, find airport price │
│ ✓ Store Uber price              │
│ ● Open Lyft, find airport price │ (● = current, amber)
│ ○ Compare and book cheaper      │ (○ = upcoming, gray)
│─────────────────────────────────│
│ MEMORY                          │
│ ┌──────────┐ ┌──────────┐      │
│ │uber_price│ │ uber_eta │      │ (light purple pills)
│ │ $18.50   │ │  8 min   │      │
│ └──────────┘ └──────────┘      │
│─────────────────────────────────│
│ LIVE ACTIONS                    │
│ step 5  Tapped "Airport" Lyft  │
│ step 4  Opened Lyft            │
│ step 3  Stored uber_price      │
│ step 2  Found price on Uber    │
│─────────────────────────────────│
│      ┌──────────────────┐      │
│      │    Stop task      │      │ (red outline)
│      └──────────────────┘      │
└─────────────────────────────────┘
```

**SwiftUI structure:**

```swift
struct TaskRunningView: View {
    @StateObject var vm: TaskRunningViewModel
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Plan section
                SectionHeader(title: "Plan")
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(vm.planSteps.enumerated()), id: \.offset) { i, step in
                        PlanStepRow(index: i, step: step, status: vm.stepStatus(i))
                    }
                }
                
                Divider()
                
                // Memory section
                if !vm.memory.isEmpty {
                    SectionHeader(title: "Memory")
                    FlowLayout(spacing: 8) {
                        ForEach(vm.memory, id: \.key) { item in
                            MemoryPill(key: item.key, value: item.value)
                        }
                    }
                    Divider()
                }
                
                // Live actions
                SectionHeader(title: "Live actions")
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(vm.actions.reversed()) { action in
                        HStack(spacing: 8) {
                            Text("step \(action.step)")
                                .font(.caption2).foregroundColor(Color(hex: "1D9E75"))
                                .frame(width: 44, alignment: .leading)
                            Text(action.detail).font(.caption).lineLimit(1)
                        }
                    }
                }
            }.padding(20)
        }
        .navigationTitle(vm.taskName)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                StatusBadge(status: vm.status) // "Running" or "Waiting"
            }
        }
        .safeAreaInset(edge: .bottom) {
            Button("Stop task") { vm.stopTask() }
                .foregroundColor(Color(hex: "E24B4A"))
                .padding(.vertical, 10).padding(.horizontal, 32)
                .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color(hex: "E24B4A"), lineWidth: 1))
                .padding(.bottom, 16)
        }
        .sheet(isPresented: $vm.showConfirmation) {
            ConfirmationSheet(request: vm.confirmationRequest, onConfirm: vm.confirm, onCancel: vm.cancel)
        }
    }
}
```

**MemoryPill component:**

```swift
struct MemoryPill: View {
    let key: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(key).font(.caption2).foregroundColor(Color(hex: "3C3489"))
            Text(value).font(.subheadline).fontWeight(.semibold).foregroundColor(Color(hex: "26215C"))
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(Color(hex: "EEEDFE"))
        .cornerRadius(8)
    }
}
```

**PlanStepRow component:**

```swift
struct PlanStepRow: View {
    let index: Int
    let step: String
    let status: StepStatus // .done, .current, .upcoming
    
    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(status == .done ? Color(hex: "1D9E75") :
                      status == .current ? Color(hex: "BA7517") : Color(.systemGray4))
                .frame(width: 18, height: 18)
                .overlay(
                    Group {
                        if status == .done {
                            Image(systemName: "checkmark").font(.system(size: 9, weight: .bold)).foregroundColor(.white)
                        } else {
                            Text("\(index + 1)").font(.system(size: 9, weight: .semibold))
                                .foregroundColor(status == .current ? .white : .gray)
                        }
                    }
                )
            Text(step).font(.caption)
                .fontWeight(status == .current ? .semibold : .regular)
                .foregroundStyle(status == .upcoming ? .secondary : .primary)
        }
    }
}
```

#### Screen 3: ConfirmationSheet.swift — Detailed Layout

```
┌─────────────────────────────────┐
│          ─── (drag handle)      │
│                                 │
│  ⚠️  Confirm booking           │
│      Spectra wants to book ride │
│                                 │
│  ┌─────────────────────────────┐│
│  │ App          Lyft           ││
│  │ Action       Tap "Book"    ││
│  │ Price        $15.00 ✓      ││
│  │ vs. Uber     $18.50        ││
│  └─────────────────────────────┘│
│                                 │
│  ┌────────────┐ ┌─────────────┐│
│  │   Cancel    │ │   Confirm   ││ (Confirm = purple fill)
│  └────────────┘ └─────────────┘│
└─────────────────────────────────┘
```

**SwiftUI structure:**

```swift
struct ConfirmationSheet: View {
    let request: ConfirmationRequest
    let onConfirm: () -> Void
    let onCancel: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            // Drag handle
            RoundedRectangle(cornerRadius: 2)
                .fill(Color(.systemGray3))
                .frame(width: 36, height: 4)
                .padding(.top, 8)
            
            // Header
            HStack(spacing: 10) {
                Circle()
                    .fill(Color(hex: "FAEEDA"))
                    .frame(width: 36, height: 36)
                    .overlay(Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(Color(hex: "BA7517")).font(.body))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Confirm booking").font(.headline)
                    Text("Spectra wants to book a ride").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
            }.padding(.horizontal, 20)
            
            // Details card
            VStack(spacing: 8) {
                DetailRow(label: "App", value: request.app)
                DetailRow(label: "Action", value: "Tap \"\(request.label)\"")
                DetailRow(label: "Price", value: request.price ?? "", highlight: true)
                if let comparison = request.comparison {
                    DetailRow(label: "vs. \(comparison.app)", value: comparison.price)
                }
            }
            .padding(14)
            .background(Color(.secondarySystemBackground))
            .cornerRadius(12)
            .padding(.horizontal, 20)
            
            // Buttons
            HStack(spacing: 12) {
                Button("Cancel") { onCancel() }
                    .frame(maxWidth: .infinity).padding(.vertical, 12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(.systemGray3)))
                
                Button("Confirm") { onConfirm() }
                    .frame(maxWidth: .infinity).padding(.vertical, 12)
                    .background(Color(hex: "534AB7")).foregroundColor(.white)
                    .cornerRadius(12)
            }.padding(.horizontal, 20)
            
            Spacer()
        }
        .presentationDetents([.medium])
        .presentationDragIndicator(.hidden)
    }
}
```

#### Screen 4: ResultView.swift — Detailed Layout

```
┌─────────────────────────────────┐
│                                 │
│          ✓ (big green)          │
│       "Task complete"           │
│                                 │
│  Booked Lyft to airport for     │
│  $15.00 (saved $3.50 vs Uber)  │
│                                 │
│  ┌──────────┐ ┌──────────┐     │
│  │ 8 steps  │ │  12.3s   │     │ (stat cards)
│  └──────────┘ └──────────┘     │
│  ┌──────────┐ ┌──────────┐     │
│  │ 2 apps   │ │ 2 values │     │
│  └──────────┘ └──────────┘     │
│                                 │
│  MEMORY USED                    │
│  uber_price: $18.50             │
│  lyft_price: $15.00             │
│                                 │
│      ┌──────────────────┐      │
│      │    New task       │      │ (purple fill)
│      └──────────────────┘      │
└─────────────────────────────────┘
```

#### WebSocketService.swift — Implementation Pattern

```swift
class WebSocketService: ObservableObject {
    @Published var isConnected = false
    @Published var latestStatus: TaskStatus?
    @Published var confirmationRequest: ConfirmationRequest?
    @Published var planPreview: PlanPreview?
    @Published var memoryItems: [MemoryItem] = []
    @Published var taskResult: TaskResult?
    
    private var webSocketTask: URLSessionWebSocketTask?
    
    func connect() {
        let url = URL(string: "ws://localhost:8765/ws")!
        webSocketTask = URLSession.shared.webSocketTask(with: url)
        webSocketTask?.resume()
        isConnected = true
        listenForMessages()
    }
    
    func send(_ message: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: message),
              let string = String(data: data, encoding: .utf8) else { return }
        webSocketTask?.send(.string(string)) { _ in }
    }
    
    func sendCommand(_ task: String) {
        send(["type": "command", "task": task])
    }
    
    func sendConfirmation(_ approved: Bool) {
        send(["type": "confirm", "approved": approved])
    }
    
    func sendPlanApproval(_ approved: Bool) {
        send(["type": "plan_approve", "approved": approved])
    }
    
    func sendStop() {
        send(["type": "stop"])
    }
    
    private func listenForMessages() {
        webSocketTask?.receive { [weak self] result in
            switch result {
            case .success(let message):
                if case .string(let text) = message,
                   let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let type = json["type"] as? String {
                    DispatchQueue.main.async {
                        self?.handleMessage(type: type, json: json)
                    }
                }
                self?.listenForMessages() // Continue listening
            case .failure:
                DispatchQueue.main.async { self?.isConnected = false }
            }
        }
    }
    
    private func handleMessage(type: String, json: [String: Any]) {
        switch type {
        case "status":
            latestStatus = TaskStatus(
                step: json["step"] as? Int ?? 0,
                total: json["total"] as? Int ?? 0,
                action: json["action"] as? String ?? "",
                detail: json["detail"] as? String ?? "",
                app: json["app"] as? String ?? ""
            )
            NotificationService.shared.postProgress(
                step: latestStatus!.step, total: latestStatus!.total, detail: latestStatus!.detail
            )
        case "memory_update":
            let item = MemoryItem(key: json["key"] as? String ?? "", value: json["value"] as? String ?? "")
            memoryItems.removeAll { $0.key == item.key }
            memoryItems.append(item)
        case "plan_preview":
            planPreview = PlanPreview(
                steps: json["steps"] as? [String] ?? [],
                task: json["task"] as? String ?? ""
            )
        case "confirm_request":
            confirmationRequest = ConfirmationRequest(
                action: json["action"] as? String ?? "",
                label: json["label"] as? String ?? "",
                app: json["app"] as? String ?? "",
                detail: json["detail"] as? String ?? ""
            )
            NotificationService.shared.postConfirmation(
                action: confirmationRequest!.label, detail: confirmationRequest!.detail
            )
        case "handoff_request":
            confirmationRequest = ConfirmationRequest(
                action: "handoff", label: "Your turn",
                app: "", detail: json["reason"] as? String ?? ""
            )
            NotificationService.shared.postConfirmation(
                action: "Your turn", detail: json["reason"] as? String ?? ""
            )
        case "done":
            taskResult = TaskResult(
                success: json["success"] as? Bool ?? false,
                summary: json["summary"] as? String ?? "",
                steps: json["steps"] as? Int ?? 0,
                duration: json["duration"] as? Double ?? 0
            )
            NotificationService.shared.postCompletion(
                summary: taskResult!.summary, steps: taskResult!.steps, duration: taskResult!.duration
            )
        case "stuck":
            taskResult = TaskResult(success: false, summary: json["reason"] as? String ?? "", steps: 0, duration: 0)
        default: break
        }
    }
}
```

#### App Entry Point

```swift
@main
struct SpectraApp: App {
    @StateObject private var ws = WebSocketService()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(ws)
                .onAppear { ws.connect() }
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var ws: WebSocketService
    
    var body: some View {
        NavigationStack {
            if let result = ws.taskResult {
                ResultView(result: result, onNewTask: { ws.taskResult = nil })
            } else if ws.latestStatus != nil {
                TaskRunningView(vm: TaskRunningViewModel(ws: ws))
            } else {
                HomeView(vm: HomeViewModel(ws: ws))
            }
        }
    }
}
```

#### Design System

**Brand colors:**
- Primary: `#534AB7` (purple — mic button, accent, progress bars)
- Primary light: `#EEEDFE` (purple tint — memory pills, highlights)
- Success: `#1D9E75` (green — completed steps, done states)
- Warning: `#BA7517` (amber — running/waiting badges)
- Danger: `#E24B4A` (red — stop button, error states)
- Background: system default (respects light/dark mode)

**Typography:**
- Task titles: 16pt semibold
- Body text: 14pt regular
- Captions/metadata: 12pt regular, secondary color
- Step labels: 11pt, color-coded by status

**Corner radius:** 16pt for cards, 24pt for the phone frame, full round for buttons and pills

#### SwiftUI View Specifications

**HomeView.swift:**
```swift
// Layout: VStack with ScrollView of task history cards + bottom input area
// Task history cards: rounded rect with status color left border
//   - Status label ("Completed" in green, "Failed" in red)
//   - Task description (1 line, bold)
//   - Metadata: "3 steps · 4.2s · Settings" in caption gray
// Center: large circular mic button (56pt diameter, #534AB7 fill, white mic SF Symbol)
//   - Tap triggers SpeechService.startListening()
//   - While listening: pulsing animation on button, waveform indicator
// Bottom: HStack with TextField("Type a task...") + send button
//   - TextField: rounded capsule border, 44pt height
//   - Send button: circle, secondary background, arrow.up SF Symbol
// Navigation: pushes to TaskRunningView when command sent
```

**TaskRunningView.swift:**
```swift
// Header: HStack with back chevron, task name (bold), status badge
//   - Badge: "Running" (amber bg #FAEEDA, amber text #854F0B)
//           "Waiting" (amber, when confirmation/handoff pending)
//           "Done" (green bg, green text)
//
// Section 1 — Plan (if plan was generated):
//   - Label "Plan" in caption gray
//   - ForEach step: HStack with status circle + step text
//     - Completed: green filled circle with white checkmark (checkmark SF Symbol)
//     - Current: amber ring with step number, text is bold
//     - Upcoming: gray ring with step number, text is tertiary color
//
// Section 2 — Memory (if any values stored):
//   - Label "Memory" in caption gray
//   - Horizontal ScrollView of pills: purple-tint bg (#EEEDFE), key in small caption, value in bold
//
// Section 3 — Live actions:
//   - Label "Live actions" in caption gray
//   - ScrollView of action rows, newest on top
//   - Each row: HStack with "step N" in green caption + action description
//   - Auto-scrolls to newest
//
// Bottom: "Stop task" button (danger background, white text, full width, rounded)
//   - Sends {"type": "stop"} via WebSocket
```

**ConfirmationSheet.swift:**
```swift
// Presented as .sheet(isPresented:) — bottom sheet style
// Top: drag handle (32pt wide, 3pt tall, gray, centered)
// Header: HStack with amber warning triangle SF Symbol (exclamationmark.triangle) + title
//   - Title: "Confirm booking" or "Confirm send" etc. (16pt semibold)
//   - Subtitle: "Spectra wants to book a ride" (12pt secondary)
//
// Detail card: rounded rect with secondary background
//   - Key-value rows: App, Action, Price (if applicable), Comparison (if applicable)
//   - Price in green if it's the cheaper option
//
// Buttons: HStack with equal-width Cancel (outline) and Confirm (purple filled)
//   - Cancel: sends {"type": "confirm", "approved": false}
//   - Confirm: sends {"type": "confirm", "approved": true}
//
// Also used for handoff: shows "Your turn: {reason}" with a single "I'm done" button
//   - Sends {"type": "takeover_done"}
```

**ResultView.swift:**
```swift
// Centered layout showing task completion
// Top: large green checkmark circle (64pt) or red X for failure
// Title: summary text (16pt semibold)
// Stats row: HStack of stat pills
//   - "8 steps" | "12.3s" | "2 apps" — each in secondary bg pill
// Memory section (if any): same pill layout as TaskRunningView
// Action log: expandable list of all steps taken
// Bottom: "New task" button (purple filled, full width) — pops back to HomeView
```

#### WebSocket Service Pattern

```swift
// WebSocketService.swift — ObservableObject for SwiftUI
class WebSocketService: ObservableObject {
    @Published var isConnected = false
    @Published var currentStatus: TaskStatus?
    @Published var memoryItems: [MemoryItem] = []
    @Published var planSteps: [PlanStep] = []
    @Published var confirmationRequest: ConfirmationRequest?
    @Published var handoffRequest: HandoffRequest?
    @Published var taskResult: TaskResult?
    
    private var webSocket: URLSessionWebSocketTask?
    
    func connect() {
        let url = URL(string: "ws://localhost:8765/ws")!
        webSocket = URLSession.shared.webSocketTask(with: url)
        webSocket?.resume()
        isConnected = true
        receiveMessage()  // Start listening loop
    }
    
    func sendCommand(task: String) {
        let msg = ["type": "command", "task": task]
        send(msg)
    }
    
    func sendConfirmation(approved: Bool) {
        send(["type": "confirm", "approved": approved ? "true" : "false"])
        confirmationRequest = nil
    }
    
    func sendTakeoverDone() {
        send(["type": "takeover_done"])
        handoffRequest = nil
    }
    
    func sendStop() {
        send(["type": "stop"])
    }
    
    func sendPlanApproval(approved: Bool) {
        send(["type": "plan_approve", "approved": approved ? "true" : "false"])
    }
    
    private func receiveMessage() {
        webSocket?.receive { [weak self] result in
            // Parse JSON, update @Published properties based on "type" field
            // Post local notifications via NotificationService
            // Then call receiveMessage() again to keep listening
        }
    }
}
```

#### Speech Service Pattern

```swift
// SpeechService.swift
import Speech

class SpeechService: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""
    
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    
    func startListening() {
        // Request authorization, start audio engine, begin recognition
        // Update transcript as words are recognized
        // After 3s of silence, stop and return final transcript
    }
    
    func stopListening() {
        audioEngine.stop()
        recognitionTask?.cancel()
        isListening = false
    }
}
```

---

## 6. Project Structure

```
spectra/
├── README.md
├── .env.example              # GEMINI_API_KEY=...
├── requirements.txt          # facebook-wda, google-genai, rich, pydantic, fastapi, uvicorn, websockets
│
├── core/
│   ├── __init__.py
│   ├── tree_reader.py       # WDA connection + tree extraction + metadata + screenshot fallback
│   ├── tree_parser.py       # XML → compact ref format
│   ├── planner.py           # Gemini API integration with function calling
│   ├── executor.py          # Translate tool calls → WDA actions
│   ├── agent.py             # Main observe→think→act loop
│   ├── stuck_detector.py    # Loop/stuck detection logic
│   ├── memory.py            # Cross-app key-value memory store
│   ├── plan_preview.py      # Action plan generation and user approval
│   ├── gates.py             # Confirmation gates for sensitive actions
│   ├── takeover.py          # User takeover / pause-resume control
│   ├── background.py        # Background threaded execution
│   └── router.py            # Task intent classification and app routing
│
├── server/
│   ├── __init__.py
│   └── ws_server.py         # FastAPI WebSocket server bridging iOS app ↔ agent
│
├── ios/
│   └── Spectra/
│       ├── Spectra.xcodeproj
│       └── Spectra/
│           ├── SpectraApp.swift
│           ├── ContentView.swift
│           ├── Views/
│           │   ├── HomeView.swift
│           │   ├── TaskRunningView.swift
│           │   ├── ConfirmationSheet.swift
│           │   └── ResultView.swift
│           ├── Services/
│           │   ├── WebSocketService.swift
│           │   ├── SpeechService.swift
│           │   └── NotificationService.swift
│           ├── Models/
│           │   ├── TaskStatus.swift
│           │   ├── ConfirmationRequest.swift
│           │   ├── PlanStep.swift
│           │   └── MemoryItem.swift
│           └── Assets.xcassets
│
├── voice/
│   ├── __init__.py
│   └── listener.py          # Speech-to-text (terminal fallback)
│
├── recorder/
│   ├── __init__.py
│   ├── recorder.py          # Record actions to .spectra JSONL
│   ├── replayer.py          # Replay with element matching
│   └── matcher.py           # Weighted multi-signal element matching
│
├── flows/                    # Saved .spectra flow files
│   └── .gitkeep
│
├── scripts/
│   ├── start_wda.sh         # Launch WDA
│   ├── start_server.sh      # Launch WebSocket server
│   └── run_agent.sh         # Set env + run agent (terminal mode)
│
└── tests/
    ├── test_tree_parser.py
    ├── test_executor.py
    └── test_ws_server.py
```

---

## 7. Environment Setup

Follow these steps exactly. The entire stack depends on WDA running successfully.

### 7.1 Prerequisites

| Requirement | Verification Command |
|-------------|---------------------|
| Xcode 16.x or later | `xcodebuild -version` |
| Xcode CLI tools | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` |
| Python 3.11+ | `python3 --version` |
| pip packages | `pip install facebook-wda google-genai rich pydantic fastapi uvicorn websockets` |
| Gemini API key | `export GEMINI_API_KEY="your-key-here"` in ~/.zshrc |

### 7.2 Boot the iOS Simulator

```bash
xcrun simctl list devices available | grep iPhone
xcrun simctl boot "iPhone 17 Pro"
open -a Simulator
```

Wait for the home screen, then open the Settings app manually.

### 7.3 Build and Launch WDA

```bash
cd ~
git clone https://github.com/appium/WebDriverAgent.git
cd WebDriverAgent

xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  test
```

First build takes 3–5 minutes. Success looks like: `ServerURLHere->http://10.x.x.x:8100<-ServerURLHere`. Leave this terminal running.

### 7.4 Verify the Full Stack

```bash
# In a new terminal tab:
curl http://localhost:8100/status
# Should return JSON with "ready": true

python3 -c "
import wda
c = wda.Client('http://localhost:8100')
print('Connected:', c.status()['state'])
tree = c.source()
print('Tree length:', len(tree))
print(tree[:500])
"
```

### 7.5 Troubleshooting

| Problem | Fix |
|---------|-----|
| simctl not found | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` |
| No runtimes | `xcodebuild -downloadPlatform iOS` and wait for download |
| WDA build fails with code signing | Add `CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO` to xcodebuild command |
| curl localhost:8100 refused | WDA is not running. Check the build terminal for errors |
| No module named 'wda' | `python3 -m pip install facebook-wda` |
| WDA crashes mid-session | Re-run the xcodebuild test command in the WDA terminal |

---

## 8. Sprint Plan

Each sprint is a self-contained work unit. Sprints 1–5 are sequential. Sprints 6–8 are parallel once Sprint 5 works.

### Sprint 1 — Environment Setup
**Owner:** Pre-work (Krish) · **Time:** 2 hours · **Depends on:** Nothing
**Goal:** WDA running, Python pulling accessibility tree XML.
**Status:** COMPLETE.
**Acceptance criteria:**
- [x] iOS simulator booted and showing Settings app
- [x] WDA running on localhost:8100
- [x] `curl http://localhost:8100/status` returns `"ready": true`
- [x] Python script prints accessibility tree XML (length > 10,000 chars)

### Sprint 2 — Tree Parser and Filter
**Owner:** Pre-work (Krish) · **Time:** 2 hours · **Depends on:** Sprint 1
**Goal:** Convert raw XML into compact ref-tagged format. See Module 5.1 for full specification.
**Deliverable:** `core/tree_parser.py` with `parse_tree()` producing < 500 tokens for Settings screen.
**Acceptance criteria:**
- [ ] `parse_tree(xml_string)` returns `(compact_text, ref_map)`
- [ ] `compact_text` contains only interactive/meaningful elements with [ref] numbers
- [ ] `ref_map` is a dict mapping ref → {type, label, value, x, y, width, height}
- [ ] Settings top-level screen produces < 500 tokens
- [ ] No zero-size elements (width=0 or height=0) in output
- [ ] Tested on at least 3 different app screens (Settings, Messages, Calendar)
**Test:**
```bash
python3 -c "
import wda
from core.tree_parser import parse_tree
c = wda.Client('http://localhost:8100')
raw = c.source()
compact, refs = parse_tree(raw)
print(compact)
print(f'\n--- {len(refs)} elements, ~{len(compact.split())} tokens ---')
"
```

### Sprint 3 — Tree Reader Module
**Owner:** Pre-work (Krish) · **Time:** 1 hour · **Depends on:** Sprint 2
**Goal:** Clean module wrapping WDA connection + tree extraction + metadata + screenshot fallback. See Module 5.2.
**Deliverable:** `core/tree_reader.py` with `TreeReader.snapshot()` returning (compact_tree, ref_map, metadata).
**Acceptance criteria:**
- [ ] `TreeReader.snapshot()` returns `(compact_text, ref_map, metadata)`
- [ ] `metadata` includes: `app_name`, `keyboard_visible`, `alert_present`, `perception_mode`
- [ ] When tree has < 3 elements, `perception_mode` is `'screenshot'` and `screenshot_b64` is populated
- [ ] Handles WDA connection errors gracefully (falls back to screenshot, doesn't crash)
- [ ] Detects if an alert/sheet is present
- [ ] Detects if keyboard is visible
**Test:**
```bash
python3 -c "
from core.tree_reader import TreeReader
reader = TreeReader()
tree, refs, meta = reader.snapshot()
print(tree[:500])
print(f'\nRefs: {len(refs)}')
print(f'Metadata: {meta}')
"
```

### Sprint 4 — LLM Planner
**Owner:** Pre-work (Krish) or hackathon · **Time:** 2 hours · **Depends on:** Sprint 3
**Goal:** Send compact tree + user goal to Claude, get structured action back. See Module 5.3.
**Deliverable:** `core/planner.py` with `Planner.next_action()` and `next_action_vision()` using Claude tool_use.
**Acceptance criteria:**
- [ ] `Planner.next_action(tree, task, history, metadata)` returns a tool call dict
- [ ] Uses Claude's native `tool_use` — no text parsing needed
- [ ] All 12 tools defined: tap, tap_xy, type_text, scroll, go_back, go_home, wait, remember, handoff, plan, done, stuck
- [ ] System prompt includes iOS patterns, memory instructions, safety rules, planning guidance
- [ ] Uses `tool_choice={"type": "any"}` to force action selection
- [ ] Prompt caching enabled on system prompt
- [ ] `next_action_vision()` sends screenshot as base64 image for fallback mode
**Test:**
```bash
python3 -c "
from core.tree_reader import TreeReader
from core.planner import Planner
reader = TreeReader()
planner = Planner()
tree, refs, meta = reader.snapshot()
action = planner.next_action(tree, 'Turn on Dark Mode', [], meta)
print(f'Action: {action}')
"
```

### Sprint 5 — Action Executor and Agent Loop
**Owner:** Hackathon hours 0–8 · **Time:** 4–6 hours · **Depends on:** Sprint 4
**Goal:** Complete the observe→think→act loop. Agent executes multi-step task end-to-end. See Modules 5.4, 5.5, 5.6.
**Key milestone:** "Turn on Dark Mode" completes successfully on Settings app.
**Acceptance criteria:**
- [ ] `Executor.run(action_name, params, ref_map)` dispatches the correct WDA call
- [ ] Tap works: finds element by ref coordinates, taps center point
- [ ] Type works: taps field, waits 300ms, sends keystrokes
- [ ] Scroll works: swipe up (to scroll down) or swipe down (to scroll up)
- [ ] go_back works: left-edge swipe
- [ ] go_home works: presses home button
- [ ] open_app works: launches app by bundle_id
- [ ] Agent loop runs: snapshot → plan → execute → repeat, max 25 steps
- [ ] Stuck detection: 3 identical tree hashes in a row → inject warning
- [ ] Memory: `remember` tool stores values, injected into next prompt
- [ ] Confirmation gates: pauses before "Send"/"Buy"/"Delete" labels
- [ ] **"Turn on Dark Mode" completes successfully on Settings app**
**Test:**
```bash
python3 -c "from core.agent import run_agent; run_agent('Turn on Dark Mode')"
```

### Sprint 6 — iOS App + WebSocket Server (PARALLEL)
**Owner:** Krish (SwiftUI) + Person B (WebSocket server) · **Time:** 8–12 hours · **Depends on:** Sprint 5 working
**Goal:** Native SwiftUI app on the simulator as the primary UI, connected to Python backend via WebSocket. See Modules 5.15 and 5.16.
**Acceptance criteria:**
- [ ] FastAPI WebSocket server runs on Mac at `ws://localhost:8765/ws`
- [ ] Server wraps BackgroundRunner and sends status/confirm/done messages as JSON
- [ ] SwiftUI app connects to WebSocket on launch
- [ ] HomeView: chat-style task history + mic button + text input
- [ ] Voice input works via iOS `SFSpeechRecognizer`
- [ ] TaskRunningView: plan checklist, memory pills, live action feed, stop button
- [ ] ConfirmationSheet: bottom sheet with action details + Cancel/Confirm buttons
- [ ] ResultView: task summary with stats
- [ ] Local notifications for progress, memory, confirmation, and completion
- [ ] Confirmation notification deep-links back to app and shows ConfirmationSheet
- [ ] End-to-end: speak "Turn on Dark Mode" → agent runs → notifications appear → done notification → tap to see results

### Sprint 7 — Recording and Replay (PARALLEL)
**Owner:** Person C · **Time:** 8–12 hours · **Depends on:** Sprint 5 working
**Goal:** Record agent flows to .spectra files and replay deterministically. See Module 5.8.
**Acceptance criteria:**
- [ ] Each action appended to JSONL file as it happens
- [ ] Each line captures: tree hash, action, params, element metadata (label, type, position)
- [ ] Replay loads .spectra file and executes each step sequentially
- [ ] Element matching: exact label+type → fuzzy label+type → position-based
- [ ] Per-step report: matched (exact/fuzzy/position) or failed
- [ ] Final summary: X steps passed, Y fuzzy-matched, Z failed

### Sprint 8 — Demo Preparation (PARALLEL)
**Owner:** Person D · **Time:** Full hackathon · **Depends on:** Sprint 5+
**Goal:** 4 demo scenarios tested 10+ times each, backup videos recorded, pitch deck written.
**Acceptance criteria:**
- [ ] 4 demo scenarios working reliably (Dark Mode, Send Message, Cross-App Comparison, Record+Replay)
- [ ] Backup video recorded for each scenario
- [ ] Pitch deck written and rehearsed
- [ ] Recovery script: if WDA crashes, restart in < 15 seconds
- [ ] Demo machine set up (screen sharing, font sizes, simulator visible)

---

## 9. Demo Scenarios

### Scenario 1: Turn on Dark Mode (30 seconds)
**Path:** Settings → Display & Brightness → tap Dark → done
**Why:** Settings has the best accessibility tree. Visually obvious result.

### Scenario 2: Send a Message to Mom (45 seconds)
**Path:** Messages → find "Mom" conversation → tap text field → type message → send
**Pre-setup:** Create a contact "Mom" in the simulator, have a recent conversation visible.
**Features shown:** Confirmation gate pauses before sending. User approves.

### Scenario 3: Cross-App Price Comparison (60 seconds)
**Path:** "Get me a ride to the airport — pick the cheapest option" → Agent opens Uber → reads price → stores in memory → presses home → opens Lyft → reads price → compares → books the cheaper one
**Pre-setup:** Install Uber and Lyft on simulator (or mock apps). Set a destination.
**Features shown:** Task routing, cross-app memory, action plan preview, confirmation gate before booking.
**Why:** This is the flagship demo. Matches Google Gemini's headline feature. Shows planning, memory, multi-app, and human-in-the-loop all in one flow.

### Scenario 4: Record and Replay (30 seconds)
**Path:** Record Scenario 1 → show the .spectra file → reset to Light Mode → replay → watch it re-execute without LLM calls
**Why:** Proves deterministic automation. Bridges to the testing story.

### Recovery Plan

```bash
cd ~/WebDriverAgent && xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  test &
sleep 30
python3 agent.py "Turn on Dark Mode"
```

---

## 10. Technical Gotchas

### 10.1 WDA on iOS 18+
- **Build failure (error code 70) with Xcode 16.2:** Use XCUITest driver version 7.35.1 or later.
- **"Application has not loaded accessibility" timeout:** On iOS 18, XCTest waits 60s then auto-recovers, corrupting the session. Catch this error and restart.
- **Session instability:** Sessions die after 4–5 operations using deprecated `/touch/perform`. Use W3C Actions.
- **Memory leak:** App memory grows to ~1.8GB under automation. Monitor and restart proactively.

### 10.2 WDA Element Coordinates
WDA provides `x`, `y`, `width`, `height` on every element in the tree — these are always present and always accurate for visible elements. Three edge cases to handle:
- **Off-screen elements don't exist.** UITableView/UICollectionView recycle cells. Off-screen items have no node in the tree at all. Scroll and re-snap to find them.
- **Overlapping elements.** When an alert covers the screen, elements behind it are still in the tree with original coordinates, but tapping those coords hits the alert. Handle alerts first.
- **Zero-size elements.** Some containers have `width=0 height=0` — logical groupings with no visual footprint. The tree parser must skip these since they can't be tapped.

### 10.3 Scroll View Cell Recycling
UITableView and UICollectionView recycle cells — off-screen elements do not exist in the accessibility tree. Implement scroll-and-scan: scroll, re-snap tree, check if target appeared, repeat up to 10 times.

### 10.4 System Alerts
Permission dialogs appear under `com.apple.springboard`, not in the app's tree. Check for alerts before each action and auto-accept based on button text ("Allow", "OK", "Continue").

### 10.5 Claude API Rate Limits
At Tier 1: 50 RPM, 40K ITPM. An agent loop at 2–3s intervals = ~20–30 RPM (fits). But 30 requests × 3K tokens = 90K ITPM (exceeds). Use prompt caching — cached tokens don't count toward ITPM. Upgrade to Tier 2 ($40) for safety.

### 10.6 Accessibility Tree Quality by Framework

| Framework | Tree Quality | Notes |
|-----------|-------------|-------|
| Apple apps (Settings, Safari) | Excellent | Proper labels, roles, identifiers |
| SwiftUI apps | Good by default | Auto-exposes accessibility |
| UIKit apps | Variable | Depends on developer effort |
| React Native apps | Highly variable | Needs explicit accessibilityRole |
| Flutter apps | Generally good | Standard widgets auto-labeled |

---

## 11. Scope Boundaries

### 11.1 In Scope (Hackathon)
- Accessibility tree extraction from any running iOS app via WDA
- Tree serialization into compact, token-efficient format with stable element refs
- Screenshot fallback when tree is unavailable (WDA failure) or too sparse (< 3 interactive elements)
- LLM integration (Gemini 3 Flash) with structured function calling
- Action execution: tap, tap_xy, type text, scroll, navigate back, go home, wait
- Multi-step task completion with automatic re-snapping after each action
- Stuck/loop detection with automatic strategy changes
- Cross-app memory: key-value store persisting across app switches within a task
- Action plan preview: agent generates plan for complex tasks, user approves before execution
- Confirmation gates: agent pauses before irreversible actions (send, purchase, delete)
- User takeover: agent hands control to user for sensitive input (passwords, payment), resumes after
- Background execution: agent runs in background thread with live progress feed
- Task routing: automatic intent classification and app selection from natural language
- Native SwiftUI iOS app as primary frontend (chat UI, mic input, plan approval, confirmations)
- WebSocket server bridging iOS app to Python agent backend
- iOS local notifications for progress, confirmations, and completion
- Voice command input via iOS SFSpeechRecognizer
- Flow recording to .spectra JSONL files
- Deterministic replay with three-tier element matching
- Demo scenarios with backup videos

### 11.2 Out of Scope (Post-Hackathon)
- On-device LLM inference
- Running without a Mac
- Cloud infrastructure for running agents at scale
- MCP server interface for developer tool integration
- Self-healing locator system with confidence scoring
- Real device support (simulator only for hackathon)
- Scheduled/recurring task automation
- Multi-user support

---

## 12. Glossary

| Term | Definition |
|------|-----------|
| WDA (WebDriverAgent) | HTTP server on the iOS simulator exposing the accessibility tree and action APIs via REST on port 8100 |
| Accessibility tree | Structured, semantic map of every UI element — names, types, positions, states — exposed for screen readers like VoiceOver |
| Ref / Reference number | Sequential integer [1], [2], [3] assigned to each interactive element. Used by the LLM to specify targets. Regenerated every turn. |
| Compact tree | Filtered, token-efficient text representation. ~200–500 tokens vs. 3,000–5,000 for a screenshot. |
| tool_use | Claude API feature returning structured JSON tool calls. Zero parse errors. |
| facebook-wda | Python library wrapping WDA's REST API. Direct HTTP, no Appium. |
| .spectra file | JSONL recording format for deterministic replay |
| Prompt caching | Anthropic API feature caching the system prompt across turns, ~80% input cost reduction |
| perception_mode | Metadata field indicating whether the agent is using 'tree' (primary) or 'screenshot' (fallback) perception |
| Cross-app memory | Key-value store persisting within a task session, enabling the agent to remember values (e.g. prices) across app switches |
| Confirmation gate | Safety check that pauses the agent before irreversible actions (send, purchase, delete) and requires user approval |
| User takeover / handoff | Agent pauses and gives manual control to the user for sensitive input like passwords or payment, then resumes |
| Task router | Intent classifier that maps natural language commands to target apps and categories (rideshare, food, messaging) |
| Action plan preview | High-level step plan generated by the agent before execution, presented to user for approval or editing |
| Background execution | Agent runs in a background thread with live progress callbacks, freeing the main thread for user interaction |
