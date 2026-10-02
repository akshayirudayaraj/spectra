# Perception eval: accessibility tree vs screenshots

Does planning from the accessibility tree beat planning from screenshots? This harness runs the same tasks under three perception modes and scores every run by checking simulator state, never by the agent's own `done()`.

| Mode | What the planner sees | How it taps |
|---|---|---|
| `tree` | compact accessibility tree (screenshot only as fallback) | element ref |
| `screenshot` | screenshot with a numbered 3×6 grid (Spectra's existing fallback) | pixel coordinates, guided by grid cell centers |
| `screenshot_raw` | plain screenshot | Gemini's native 0–1000 coordinates |

## Results (2026-10-02, 180 runs)

20 tasks × 3 modes × 3 trials on an iPhone 17 Pro simulator (iOS 26.5), `gemini-3-flash-preview`, max 20 steps. Full tables: [`results/full_report.md`](results/full_report.md). Raw runs: [`results/full.jsonl`](results/full.jsonl), one log per run in `results/full_logs/`.

| Mode | Success | 95% CI | Median steps (passes) | Mean time/run | Mean tokens/run |
|---|---|---|---|---|---|
| tree | **54/60 (90%)** | 80–95% | 5 | 53 s | 36.5k |
| screenshot (grid) | 14/60 (23%) | 14–35% | 6 | 206 s | 138k |
| screenshot_raw | 52/60 (87%) | 76–93% | 4 | 59 s | 32.6k |

Paired on the same task and trial:
- **tree vs grid screenshots:** tree passed 40 runs that grid failed, and grid passed none that tree failed (exact McNemar p ≈ 2e-12).
- **tree vs raw screenshots:** 4 runs went to tree and 2 to raw (p = 0.69), which is no significant difference.

What the numbers say:
- **The tree beats Spectra's grid-screenshot fallback by a wide margin.** The grid only lets the model tap one of 18 cell centers, so it misses small targets. 36 of its 60 runs hit the step limit.
- **A well-prompted raw screenshot agent nearly matches the tree** on these tasks. The tree's clearest wins are form-filling: creating contacts went 6/6 vs 3/6, because typing into a field by ref is more reliable than tapping coordinates. Raw screenshots won on Calendar (2/3 vs 0/3), where the tree agent couldn't operate the time picker.
- **Failures common to all modes:** `text_size_up` (0/3 everywhere) needs a slider, and the model never manages it in any mode.

Caveats:
- Safari's page content isn't reachable through WDA, so all 3 `wiki_article` runs in tree mode fell back to screenshots. Overall, 10 of 463 tree-mode steps (2%) were screenshots. Without that task: tree 51/57, raw 49/57, grid 12/57.
- 14 runs crashed on malformed model output: no function call, or a `tap_xy` with no `x`. They count as failures. Excluding them gives tree 92%, raw 93%, grid 27%.
- Spectra never used OCR, so this compares tree perception against screenshots read by a vision model.

## Fixes the pilot runs forced

Pilot runs surfaced bugs that would have skewed the comparison. All were fixed before the 180-run eval:
- **Agent loop (real bug):** the loop waited only 4 s for a snapshot, then silently reused the previous screen. WDA `source()` takes about 4 s on busy screens, so the planner kept acting on stale trees, for example re-tapping toggles it had already flipped. It now waits up to 25 s.
- **`tap_xy`:** it guessed point vs pixel space from the coordinate values, which misplaced every tap in the top-left third of the screen. It now always scales.
- **Screenshot typing:** screenshot mode had no way to type without a ref. `type_text` now types into the focused field.
- **Mid-transition captures:** screenshots were taken mid-transition, because a screenshot is instant where a tree read takes 1–4 s. Capture now waits 1 s.
- **Raw-mode coordinates:** in a calibration test on real screenshots, Gemini hit 8/8 targets with 0–1000 coordinates on two screens, while its pixel coordinates were scattered.

## Running it

Needs a booted simulator with WebDriverAgent on :8100 and `GEMINI_API_KEY` in `.env`.

```bash
SPECTRA_SIM_UDID=<udid> python -m evals.run --modes tree,screenshot,screenshot_raw --trials 3 --k-offset 1000
python -m evals.report evals/results/<run>.jsonl --md report.md
```

Runs append to the JSONL as they finish; `--resume <file>` continues an interrupted run. Runs lost to API rate limits or 5xx are redone, not scored. Tasks that create records draw a fresh name per run, so give separate invocations different `--k-offset` values.

Before the first run, open each app once and clear its onboarding and permission prompts, so first-launch screens don't land on whichever mode runs first. Settings toggles are reset with `defaults write`. Keyboard settings are left out because writing their defaults doesn't change what Settings shows.
