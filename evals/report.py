"""Summarize a perception-eval JSONL: success rate per mode with 95% CIs, cost, per-task table.

    python -m evals.report evals/results/<run>.jsonl [more.jsonl ...] [--md out.md]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from statistics import mean, median


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _fmt(x, nd=1):
    return '–' if x is None else f'{x:.{nd}f}'


def summarize(rows: list[dict]) -> str:
    modes = sorted({r['mode'] for r in rows}, key=lambda m: ('tree', 'screenshot', 'screenshot_raw').index(m)
                   if m in ('tree', 'screenshot', 'screenshot_raw') else 9)
    by_mode = defaultdict(list)
    for r in rows:
        by_mode[r['mode']].append(r)

    out = ['## Overall', '',
           '| Mode | Success | Rate (95% CI) | Steps (median, success) | Time/run s (median) | Tokens/run (median) | Errors |',
           '|---|---|---|---|---|---|---|']
    for m in modes:
        rs = by_mode[m]
        k, n = sum(r['success'] for r in rs), len(rs)
        lo, hi = wilson(k, n)
        ok_steps = [r['steps'] for r in rs if r['success'] and r['steps']]
        times = [r['elapsed_s'] for r in rs if r['elapsed_s'] is not None]
        toks = [(r['prompt_tokens'] or 0) + (r['output_tokens'] or 0) for r in rs if r['prompt_tokens'] is not None]
        errs = sum(r['outcome'] == 'error' for r in rs)
        out.append(f'| {m} | {k}/{n} | {100*k/n:.0f}% ({100*lo:.0f}–{100*hi:.0f}%) | '
                   f'{_fmt(median(ok_steps) if ok_steps else None)} | {_fmt(median(times) if times else None)} | '
                   f'{_fmt(median(toks) if toks else None, 0)} | {errs} |')

    # Sensitivity: drop runs that crashed (malformed model output, not a wrong
    # action), to show the conclusion doesn't hinge on how those are scored.
    out += ['', '## Excluding errored runs', '', '| Mode | Success | Rate (95% CI) |', '|---|---|---|']
    for m in modes:
        rs = [r for r in by_mode[m] if r['outcome'] != 'error']
        k, n = sum(r['success'] for r in rs), len(rs)
        lo, hi = wilson(k, n)
        out.append(f'| {m} | {k}/{n} | {100*k/max(n,1):.0f}% ({100*lo:.0f}–{100*hi:.0f}%) |')

    # Paired comparison against tree on the same (task, trial).
    if 'tree' in by_mode:
        key = lambda r: (r['task'], r['trial'])
        tree = {key(r): r['success'] for r in by_mode['tree']}
        out += ['', '## Paired vs tree (same task, same trial)', '',
                '| Mode | Both pass | Only tree | Only this mode | Both fail | Exact McNemar p |', '|---|---|---|---|---|---|']
        for m in modes:
            if m == 'tree':
                continue
            pairs = [(tree[key(r)], r['success']) for r in by_mode[m] if key(r) in tree]
            both = sum(a and b for a, b in pairs)
            only_t = sum(a and not b for a, b in pairs)
            only_m = sum(b and not a for a, b in pairs)
            neither = sum(not a and not b for a, b in pairs)
            out.append(f'| {m} | {both} | {only_t} | {only_m} | {neither} | {exact_mcnemar(only_t, only_m):.3g} |')

    # Outcome breakdown: how runs ended vs whether the check passed.
    out += ['', '## How runs ended', '', '| Mode | ' + ' | '.join(
        ['done ✓', 'done ✗ (claimed, check failed)', 'stuck', 'timeout', 'hard_stuck', 'error']) + ' |',
        '|---|---|---|---|---|---|---|']
    for m in modes:
        rs = by_mode[m]
        cnt = lambda o, s=None: sum(r['outcome'] == o and (s is None or r['success'] == s) for r in rs)
        out.append(f"| {m} | {cnt('done', True)} | {cnt('done', False)} | {cnt('stuck')} | "
                   f"{cnt('timeout')} | {cnt('hard_stuck')} | {cnt('error')} |")

    # Per task.
    tasks = list(dict.fromkeys(r['task'] for r in rows))
    out += ['', '## Per task (passes / runs)', '', '| Task | ' + ' | '.join(modes) + ' |',
            '|---|' + '---|' * len(modes)]
    for t in tasks:
        cells = []
        for m in modes:
            rs = [r for r in by_mode[m] if r['task'] == t]
            cells.append(f"{sum(r['success'] for r in rs)}/{len(rs)}" if rs else '–')
        out.append(f'| {t} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl', nargs='+', help='one or more result files, combined')
    ap.add_argument('--md', help='also write the summary to this markdown file')
    args = ap.parse_args()
    rows = [json.loads(l) for path in args.jsonl for l in open(path) if l.strip()]
    text = summarize(rows)
    print(text)
    if args.md:
        with open(args.md, 'w') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main()
