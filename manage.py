"""Benchmark execution and consistent SQLite backup."""

import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from benchmarks import benchmark_cases
from evaluation import ARMS, evaluate_case, new_run, summarize
from model_client import ModelClient, load_settings
from storage import Store

def run_evaluation(store, arms, workers):
    settings = load_settings()
    client = ModelClient(settings)
    if any(a != 'A' for a in arms) and not client.configured:
        raise ValueError('Configure a model before running B or C; A is offline.')
    run = new_run(arms, benchmark_cases(), settings.model, settings.public_parameters())
    run['execution'] = {'workers': workers, 'entrypoint': 'manage.py evaluate'}
    store.save_evaluation(run)
    print('Evaluation:', run['id'], flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(evaluate_case, case, arm, client) for arm in arms for case in benchmark_cases()]
        for future in as_completed(futures):
            row = future.result()
            run['rows'].append(row)
            store.update_evaluation(run)
            print(f"{row['arm']} {row['case_id']}: complete={row['complete']} category_match={row['matched']}", flush=True)
    run['rows'].sort(key=lambda row: (row['arm'], row['case_id']))
    run['complete'] = True
    store.update_evaluation(run)
    return summarize(run['rows'])


def backup(store, output):
    target = Path(output).expanduser().resolve()
    if target == store.path.resolve() or target.exists():
        raise ValueError('Choose a new backup filename; existing files are never overwritten.')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the output before opening SQLite to avoid clobbering an existing file.
    with target.open('xb'):
        pass
    with store.connection() as source:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed.')
        finally:
            destination.close()
    return str(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    evaluate = commands.add_parser('evaluate', help='A is offline; B/C make real model API calls')
    evaluate.add_argument('--arms', nargs='+', choices=list(ARMS), default=['A'])
    evaluate.add_argument('--workers', type=int, choices=[1, 2, 3], default=1)
    back = commands.add_parser('backup', help='Make a consistent SQLite backup; never overwrites a file')
    back.add_argument('--output', required=True)
    commands.add_parser('results', help='Print summaries of saved evaluations')
    args = parser.parse_args()
    try:
        store = Store()
        if args.command == 'evaluate':
            print(json.dumps(run_evaluation(store, list(dict.fromkeys(args.arms)), args.workers), indent=2))
        elif args.command == 'backup':
            print('Backup saved:', backup(store, args.output))
        else:
            print(json.dumps([{'id': run['id'], 'complete': run['complete'], 'summary': summarize(run['rows'])}
                              for run in store.evaluations()], indent=2))
    except (ValueError, OSError, sqlite3.Error):
        # Do not print model-setting validation exceptions, which could contain secrets.
        parser.exit(1, 'Operation failed. Check configuration, input paths and workspace permissions.\n')


if __name__ == '__main__':
    main()
