"""python -m workflow --help"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from .store import Store, pending
from .server import serve


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def facts(paths):
    result = []
    for raw in paths:
        path = Path(raw)
        item = {'path': raw, 'exists': path.exists()}
        if path.is_file():
            item['bytes'] = path.stat().st_size
            if item['bytes'] <= 16 * 1024 * 1024:
                item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                item['sha256'] = None
                item['hash_note'] = 'larger than 16 MiB; supply a separate manifest'
        result.append(item)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local coordination workspace; see README.md')
    parser.add_argument('--data', default=os.environ.get('WORKFLOW_DATA', '.workflow-data'))
    subs = parser.add_subparsers(dest='command', required=True)
    init = subs.add_parser('init'); init.add_argument('--title', default='My project'); init.add_argument('--demo', action='store_true')
    web = subs.add_parser('serve'); web.add_argument('--port', type=int, default=8040); web.add_argument('--host', default='127.0.0.1', help='Bind IP; use a trusted LAN IP for direct access; --port 0 chooses a free port')
    subs.add_parser('state')
    inbox = subs.add_parser('inbox'); inbox.add_argument('--require-clear', action='store_true'); inbox.add_argument('--owner')
    change = subs.add_parser('apply', help='Apply a JSON action from a file or stdin (-)')
    change.add_argument('action', choices=['agent', 'node', 'document', 'comment', 'followup', 'reply', 'run'])
    change.add_argument('--file', required=True); change.add_argument('--agent', default='user'); change.add_argument('--revision', type=int)
    run = subs.add_parser('run', help='Run a local command; record argv, cwd, input/output paths and exit code')
    run.add_argument('--node', required=True); run.add_argument('--agent', required=True)
    run.add_argument('--summary', required=True); run.add_argument('--cwd', default='.')
    run.add_argument('--input', action='append', default=[]); run.add_argument('--output', action='append', default=[])
    run.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    store = Store(args.data)
    try:
        if args.command == 'init':
            store.initialize(args.title)
            if args.demo:
                from .demo import populate
                populate(store)
            emit({'workspace': str(store.directory.resolve()), 'revision': store.read()['revision']})
        elif args.command == 'serve':
            serve(args.data, args.port, args.host)
        elif args.command == 'state':
            emit(store.read())
        elif args.command == 'inbox':
            rows = pending(store.read())
            if args.owner:
                rows = [row for row in rows if row['owner'] == args.owner]
            emit({'pending_threads': len(rows), 'threads': rows})
            return 3 if rows and args.require_clear else 0
        elif args.command == 'apply':
            raw = sys.stdin.read() if args.file == '-' else Path(args.file).read_text()
            emit(store.change(args.action, json.loads(raw), args.agent, args.revision))
        elif args.command == 'run':
            command = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            if not command:
                raise ValueError('command required after --')
            if pending(store.read()):
                raise ValueError('unresolved user comments: inspect inbox and apply or defer them before a new run')
            cwd = str(Path(args.cwd).resolve())
            if not Path(cwd).is_dir():
                raise ValueError('cwd does not exist')
            paths = lambda items: [p if Path(p).is_absolute() else str(Path(cwd) / p) for p in items]
            outputs = paths(args.output)
            row = store.change('run_start', {'node_id': args.node, 'summary': args.summary, 'cwd': cwd,
                'command': command, 'inputs': paths(args.input), 'outputs': outputs}, args.agent)['record']
            print('WORKFLOW_RUN_ID=' + row['id'], flush=True)
            error = ''
            try:
                # No shell, no environment dump, no stdout/stderr capture. Command output stays in the terminal.
                code = subprocess.run(command, cwd=cwd, check=False).returncode
            except OSError as exc:
                code, error = 127, str(exc)
            except KeyboardInterrupt:
                code, error = 130, 'interrupted'
            try:
                output_facts = facts(outputs)
            except OSError as exc:
                output_facts = [{'error': str(exc)}]
            emit(store.change('run_finish', {'id': row['id'], 'exit_code': code, 'error': error,
                 'output_facts': output_facts}, args.agent))
            return code if code >= 0 else 128 - code
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
