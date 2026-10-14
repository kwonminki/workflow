"""Versioned JSON state. Local POSIX lock + atomic replacement; no external services."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
import uuid

STATUSES = {'planned', 'running', 'partial', 'review', 'done', 'blocked'}
OUTCOMES = {'seen', 'applied', 'deferred'}

class Conflict(ValueError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def ident(prefix):
    return prefix + '-' + uuid.uuid4().hex[:12]

def text(value, field, limit=20000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'{field}: nonempty text, maximum {limit} characters')
    return value

def strings(value, field):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f'{field}: list, maximum 100 entries')
    return [text(x, field, 2000) for x in value]

def named(items, key):
    for item in items:
        if item['id'] == key:
            return item
    raise ValueError(f'unknown id: {key}')

def empty_state(title):
    return {'schema': 'workflow.v1', 'revision': 0, 'title': title, 'nodes': [],
            'documents': [], 'threads': [], 'runs': [], 'agents': [], 'events': []}

def pending(state):
    return [{'thread_id': t['id'], 'target': t['target'], 'anchor': t['anchor'],
             'owner': t['owner'], 'messages': t['messages'], 'pending_message_ids':
             [m['id'] for m in t['messages'] if m['kind'] == 'user' and
              not any(r.get('reply_to') == m['id'] and r.get('outcome') in {'applied', 'deferred'}
                      for r in t['messages'])]}
            for t in state['threads'] if any(m['kind'] == 'user' and
              not any(r.get('reply_to') == m['id'] and r.get('outcome') in {'applied', 'deferred'}
                      for r in t['messages']) for m in t['messages'])]

def validate_graph(nodes):
    by_id = {n['id']: n for n in nodes}
    incoming = {n['id']: len(set(n['depends_on'])) for n in nodes}
    outgoing = {key: [] for key in by_id}
    for node in nodes:
        for dep in set(node['depends_on']):
            if dep not in by_id:
                raise ValueError(f'unknown dependency: {dep}')
            outgoing[dep].append(node['id'])
    ready = [key for key, degree in incoming.items() if degree == 0]
    visited = 0
    while ready:
        key = ready.pop()
        visited += 1
        for successor in outgoing[key]:
            incoming[successor] -= 1
            if incoming[successor] == 0:
                ready.append(successor)
    if visited != len(nodes):
        raise ValueError('dependency cycle')

def actor_for(state, agent_id):
    agent = named(state['agents'], agent_id)
    return {key: agent[key] for key in ('id', 'role', 'session')}

def apply(state, action, data, actor='user'):
    """Mutate a working copy; caller commits only when all checks pass."""
    stamp = now()
    agent = actor_for(state, actor) if actor != 'user' else {'id': 'user', 'role': 'user', 'session': 'browser-or-local-cli'}
    if action == 'agent':
        role = text(data.get('role'), 'role', 120)
        session = text(data.get('session'), 'session', 500)
        key = text(data.get('id'), 'id', 100)
        if key == 'user' or not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('invalid agent id')
        existing = next((a for a in state['agents'] if a['id'] == key), None)
        value = {'id': key, 'role': role, 'session': session, 'updated_at': stamp}
        if existing:
            existing.update(value)
        else:
            state['agents'].append(value)
        result = value
    elif action == 'node':
        key = data.get('id') or ident('task')
        text(key, 'id', 100)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('id must use letters, numbers, underscore or hyphen')
        old = next((n for n in state['nodes'] if n['id'] == key), None)
        value = copy.deepcopy(old) if old else {'id': key, 'title': '', 'group': 'General',
            'status': 'planned', 'goal': '', 'next_action': '', 'depends_on': [],
            'owner': '', 'evidence': [], 'completion': '', 'priority': 50, 'links': []}
        for field in ('title', 'group', 'goal', 'next_action', 'completion'):
            if field in data:
                value[field] = text(data[field], field, empty=field not in {'title', 'group'})
        text(value['title'], 'title', 200)
        for field in ('depends_on', 'evidence', 'links'):
            if field in data:
                value[field] = strings(data[field], field)
        if 'owner' in data:
            value['owner'] = text(data['owner'], 'owner', 100, empty=True)
            if value['owner']:
                named(state['agents'], value['owner'])
        if 'priority' in data:
            if type(data['priority']) is not int or not 0 <= data['priority'] <= 100:
                raise ValueError('priority must be an integer 0..100')
            value['priority'] = data['priority']
        value['status'] = data.get('status', value['status'])
        if value['status'] not in STATUSES:
            raise ValueError('unknown status')
        if value['status'] == 'done' and (not value['completion'].strip() or not value['evidence']):
            raise ValueError('done needs completion explanation and evidence')
        value.update(updated_at=stamp, author=agent)
        if old:
            old.update(value)
        else:
            state['nodes'].append(value)
        validate_graph(state['nodes'])
        result = value
    elif action == 'document':
        key = data.get('id') or ident('doc')
        text(key, 'id', 100)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('id must use letters, numbers, underscore or hyphen')
        title = text(data.get('title'), 'title', 200)
        body = text(data.get('body'), 'body', 200000)
        old = next((d for d in state['documents'] if d['id'] == key), None)
        history = old['history'] if old else []
        if old:
            history.append({k: old[k] for k in ('revision', 'body', 'title', 'author', 'updated_at')})
        value = {'id': key, 'title': title, 'body': body, 'history': history,
                 'revision': hashlib.sha256(body.encode()).hexdigest(), 'author': agent, 'updated_at': stamp}
        if old:
            old.update(value)
        else:
            state['documents'].append(value)
        result = value
    elif action == 'comment':
        target = data.get('target', {})
        if not isinstance(target, dict) or target.get('kind') not in {'node', 'document'}:
            raise ValueError('comment needs node/document target')
        source = named(state['nodes' if target['kind'] == 'node' else 'documents'], target.get('id'))
        anchor = data.get('anchor')
        if anchor:
            if target['kind'] != 'document' or not isinstance(anchor, dict):
                raise ValueError('anchor requires document')
            start, end = anchor.get('start'), anchor.get('end')
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source['body']):
                raise ValueError('invalid anchor offsets')
            if anchor.get('revision') != source['revision'] or source['body'][start:end] != anchor.get('quote'):
                raise Conflict('document changed; reselect the passage')
            anchor = {**anchor, 'prefix': source['body'][max(0,start-80):start], 'suffix': source['body'][end:end+80]}
        owner = source.get('owner') or source.get('author', {}).get('id')
        result = {'id': ident('thread'), 'target': target, 'anchor': anchor,
                  'owner': owner or '', 'created_at': stamp, 'messages': []}
        state['threads'].append(result)
        result['messages'].append({'id': ident('message'), 'kind': 'user',
            'text': text(data.get('text'), 'text'), 'created_at': stamp, 'author': agent})
    elif action in {'followup', 'reply'}:
        thread = named(state['threads'], data.get('thread_id'))
        parent = named(thread['messages'], data.get('reply_to'))
        result = {'id': ident('message'), 'kind': 'user' if action == 'followup' else 'agent',
                  'reply_to': parent['id'], 'text': text(data.get('text'), 'text'),
                  'author': agent, 'created_at': stamp}
        if action == 'reply':
            if actor == 'user' or parent['kind'] != 'user':
                raise ValueError('registered agent must reply to a user message')
            outcome = data.get('outcome')
            if outcome not in OUTCOMES:
                raise ValueError('outcome must be seen/applied/deferred')
            evidence = strings(data.get('evidence', []), 'evidence')
            if outcome == 'applied' and not evidence:
                raise ValueError('applied requires evidence')
            if outcome == 'deferred':
                named(state['nodes'], data.get('workflow_node'))
            result.update(outcome=outcome, evidence=evidence, workflow_node=data.get('workflow_node'), read_at=None)
        thread['messages'].append(result)
    elif action == 'read':
        if actor != 'user':
            raise ValueError('only user marks notification read')
        result = named(named(state['threads'], data.get('thread_id'))['messages'], data.get('message_id'))
        if result['kind'] != 'agent':
            raise ValueError('only agent reply is a notification')
        result['read_at'] = stamp
    elif action in {'run', 'run_start'}:
        named(state['nodes'], data.get('node_id'))
        result = {'id': ident('run'), 'node_id': data['node_id'], 'created_at': stamp, 'author': agent}
        for field in ('summary', 'cwd', 'validation', 'result'):
            result[field] = text(data.get(field, ''), field, empty=field != 'summary')
        for field in ('command', 'inputs', 'outputs', 'evidence'):
            result[field] = strings(data.get(field, []), field)
        result['source'] = 'execution_wrapper' if action == 'run_start' else 'self_report'
        if action == 'run_start':
            result.update(status='running', started_at=stamp)
        state['runs'].append(result)
    elif action == 'run_finish':
        result = named(state['runs'], data.get('id'))
        if result['source'] != 'execution_wrapper' or result.get('status') != 'running':
            raise ValueError('run is not running')
        code = data.get('exit_code')
        if type(code) is not int:
            raise ValueError('exit_code must be integer')
        result.update(status='succeeded' if code == 0 else 'failed', exit_code=code,
                      finished_at=stamp, output_facts=data.get('output_facts', []),
                      error=data.get('error', ''))
    else:
        raise ValueError(f'unknown action: {action}')
    state['events'].append({'id': ident('event'), 'at': stamp, 'action': action,
                            'actor': agent, 'record_id': result['id'], 'data': copy.deepcopy(data)})
    return result

class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'state.json'

    def read(self):
        with self.path.open() as stream:
            state = json.load(stream)
        if state.get('schema') != 'workflow.v1':
            raise ValueError('unsupported workspace schema')
        return state

    def write(self, state):
        fd, path = tempfile.mkstemp(prefix='.state-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def initialize(self, title):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                raise ValueError('workspace already exists; refusing to overwrite')
            self.write(empty_state(text(title, 'title', 200)))

    def change(self, action, data, actor='user', revision=None):
        if not isinstance(data, dict):
            raise ValueError('data must be an object')
        with (self.directory / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.read()
            if revision is not None and (type(revision) is not int or revision != state['revision']):
                raise Conflict('workspace changed; reload before saving')
            result = apply(state, action, data, actor)
            state['revision'] += 1
            self.write(state)
            return {'record': result, 'revision': state['revision']}
