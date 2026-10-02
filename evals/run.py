"""Run the perception eval: every task under every perception mode, scored by independent checks.

    SPECTRA_SIM_UDID=<udid> python -m evals.run --trials 3
    python -m evals.report evals/results/<run>.jsonl

Needs a booted simulator with WebDriverAgent on :8100 and GEMINI_API_KEY (env or .env).
Runs are appended to a JSONL file as they finish; pass --resume <file> to pick up
where an interrupted run stopped.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import random
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _load_dotenv() -> None:
    path = os.path.join(ROOT, '.env')
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"\''))


_load_dotenv()

from core.agent import run_agent          # noqa: E402
from core.gates import ConfirmationGate   # noqa: E402
from core.takeover import TakeoverManager  # noqa: E402
from core.tree_reader import PERCEPTION_MODES  # noqa: E402
from evals import sim                      # noqa: E402
from evals.tasks import SUITES, TASKS_BY_ID, SETTINGS  # noqa: E402


class _AutoApproveGate(ConfirmationGate):
    """Every eval task is something the user asked for, so approve sensitive taps."""

    def request_confirmation(self, action, ref_map) -> bool:
        return True


class _NoHumanTakeover(TakeoverManager):
    def pause(self, reason: str) -> None:
        self._paused = True

    def wait_for_resume(self) -> None:
        self._paused = False


def _no_answer(question, options) -> str:
    return 'No one is available to answer. Use your best judgment and continue.'


def _is_api_outage(msg: str) -> bool:
    """Rate limits and 5xx are infrastructure, not agent failures: redo the run."""
    return any(x in msg for x in ('429', 'rate limit', 'RESOURCE_EXHAUSTED', '503', '500', 'UNAVAILABLE', 'ServerError'))


def build_plan(task_ids: list[str], modes: list[str], trials: int, seed: int, k_offset: int = 0) -> list[dict]:
    """Interleave modes inside each (trial, task) in a seeded random order, so drift
    over the run (network, simulator state, API latency) lands on every mode alike."""
    plan = []
    for trial in range(trials):
        for t_idx, tid in enumerate(task_ids):
            order = modes[:]
            random.Random(f'{seed}-{trial}-{tid}').shuffle(order)
            for pos, mode in enumerate(order):
                # k indexes the task's parameter pool; unique per run so created
                # records never collide across runs. Give separate invocations
                # different --k-offset values so they can't collide either.
                k = k_offset + trial * len(modes) + pos
                plan.append({'trial': trial, 'task': tid, 'mode': mode, 'k': k})
    return plan


def _run_id(item: dict) -> str:
    return f"{item['task']}-{item['mode'].replace('@', '__')}-t{item['trial']}"


def _agent(prompt: str, mode: str, max_steps: int, stats: dict) -> None:
    """Run one task under a mode spec: '<perception>[@<model>]' or 'computer_use'."""
    if mode == 'computer_use':
        from evals.computer_use_agent import run_computer_use
        run_computer_use(prompt, max_steps=max_steps, stats=stats, wda_url=sim.WDA_URL)
        return
    perception, _, model = mode.partition('@')
    run_agent(
        prompt, max_steps=max_steps, verbose=True, wda_url=sim.WDA_URL,
        gate=_AutoApproveGate(), takeover=_NoHumanTakeover(), ask_user_fn=_no_answer,
        perception=perception, learn=False, stats=stats, model=model or None,
    )


def run_one(item: dict, max_steps: int, log_dir: str) -> dict:
    task = TASKS_BY_ID[item['task']]
    params = task.params(item['k'])
    prompt = task.render(params)
    run_id = _run_id(item)
    record = {**item, 'run_id': run_id, 'prompt': prompt, 'params': params,
              'started_at': dt.datetime.now().isoformat(timespec='seconds')}

    task.setup(params)
    sim.reset_to_app(task.app, also_terminate=(SETTINGS,))

    stats: dict = {}
    log_path = os.path.join(log_dir, f'{run_id}.log')
    for attempt in range(3):
        try:
            with open(log_path, 'w') as log, contextlib.redirect_stdout(log):
                print(f'TASK: {prompt}\nMODE: {item["mode"]}\n')
                _agent(prompt, item['mode'], max_steps, stats)
            break
        except Exception as e:
            msg = f'{type(e).__name__}: {e}'
            with open(log_path, 'a') as log:
                log.write('\n' + traceback.format_exc())
            if attempt < 2 and _is_api_outage(msg):
                print(f'    API error ({msg[:60]}), redoing run in 60s', flush=True)
                time.sleep(60)
                task.setup(params)
                sim.reset_to_app(task.app, also_terminate=(SETTINGS,))
                stats = {}
                continue
            stats = {'outcome': 'error', 'error': msg[:300]}
            break

    time.sleep(2)  # let the app persist what the agent did before reading it back
    try:
        success, detail = task.check(params, stats)
    except Exception as e:
        success, detail = False, f'check error: {e}'
    sim.go_home()

    record.update(
        success=bool(success), check_detail=detail,
        outcome=stats.get('outcome'), steps=stats.get('steps'),
        elapsed_s=stats.get('elapsed_s'), planner_calls=stats.get('calls'),
        prompt_tokens=stats.get('prompt_tokens'), output_tokens=stats.get('output_tokens'), thought_tokens=stats.get('thought_tokens'),
        error=stats.get('error'), history=stats.get('history', []),
    )
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--modes', default='tree,screenshot',
                    help=f'comma-separated: <perception>[@<model>] with perception from {PERCEPTION_MODES}, '
                         'or computer_use')
    ap.add_argument('--suite', default='base', choices=sorted(SUITES))
    ap.add_argument('--shard', default='0/1', help='i/n: run every n-th plan item starting at i (parallel simulators)')
    ap.add_argument('--trials', type=int, default=3)
    ap.add_argument('--tasks', default='', help='comma-separated task ids (default: all)')
    ap.add_argument('--max-steps', type=int, default=20)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--k-offset', type=int, default=0,
                    help='shift the per-run name/number pool, e.g. 1000 for a run after pilots')
    ap.add_argument('--resume', help='append to this JSONL and skip runs already in it')
    ap.add_argument('--skip-done-in', nargs='*', default=[],
                    help='also skip runs recorded in these JSONL files (e.g. the other shard)')
    args = ap.parse_args()

    modes = args.modes.split(',')
    bad = [m for m in modes if m != 'computer_use' and m.partition('@')[0] not in PERCEPTION_MODES]
    if bad:
        ap.error(f'unknown modes {bad}')
    task_ids = args.tasks.split(',') if args.tasks else [t.id for t in SUITES[args.suite]]
    plan = build_plan(task_ids, modes, args.trials, args.seed, args.k_offset)
    shard_i, shard_n = (int(x) for x in args.shard.split('/'))
    plan = plan[shard_i::shard_n]

    out = args.resume or os.path.join(ROOT, 'evals', 'results',
                                      dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log_dir = out[:-len('.jsonl')] + '_logs'
    os.makedirs(log_dir, exist_ok=True)

    done = set()
    for path in [out, *args.skip_done_in]:
        if os.path.exists(path):
            done |= {json.loads(l)['run_id'] for l in open(path) if l.strip()}

    print(f'{len(plan)} runs ({len(done)} already done) -> {out}', flush=True)
    for i, item in enumerate(plan, 1):
        run_id = _run_id(item)
        if run_id in done:
            continue
        rec = run_one(item, args.max_steps, log_dir)
        with open(out, 'a') as f:
            f.write(json.dumps(rec) + '\n')
        mark = 'PASS' if rec['success'] else 'fail'
        print(f"[{i}/{len(plan)}] {mark} {run_id:<36} steps={rec['steps']} "
              f"{rec['elapsed_s']}s {rec['outcome']} | {rec['check_detail']}", flush=True)


if __name__ == '__main__':
    main()
