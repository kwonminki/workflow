"""Optional local bridge. Explicit config, durable outbox, no browser commands.

Discord delivery retries with a stable nonce. Terminal delivery is at-most-once:
ambiguous sends remain unknown and require checking the original session.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def attention_items(value, kind):
    """Mirror explicit home cards, not every sample or running process."""
    result = []
    def add(key, revision, title, url):
        result.append({'id': key, 'revision': str(revision), 'title': title, 'url': url})
    if kind == 'workflow':
        for n in value['nodes']:
            if n['status'] == 'review':
                revision = hashlib.sha256(json.dumps({k:n.get(k) for k in ('title','goal','next_action','evidence','links')}, sort_keys=True).encode()).hexdigest()
                add('node:'+n['id'], revision, n['title'], '#graph/'+n['id'])
        for t in value.get('threads', []):
            for m in t.get('messages', []):
                if m['kind']=='user' and not any(r.get('reply_to')==m['id'] and r.get('outcome') in ('applied','deferred') for r in t['messages']):
                    add('comment:'+m['id'], m['id'], '새 사용자 의견 · '+t['target']['id'], '#home')
    elif kind == 'hub':
        for e in value.get('pending', []):
            add('comment:'+e['id'], e['id'], '새 사용자 의견 · '+e.get('target',{}).get('title','웹 의견'), e.get('target',{}).get('url','#'))
        for n in value['notion']:
            if not n.get('locally_read'): add('notion:'+n['id'], n['updated_at'], n['title'], n['url'])
        for r in value['human_requests']:
            if not r.get('answered') and (r['status'] == 'open' or r.get('category') == 'work_result'):
                add('request:'+r['id'], r['revision'], r['title'], r.get('review_url') or r['url'])
        for s in value['samples']:
            for r in s.get('requests', []):
                add('sample:'+s['id']+':'+r['id'], s['revision']+':'+r.get('question',''), r.get('question', s['id']), '#review='+s['id'])
    else:
        raise ValueError('source_kind must be workflow or hub')
    return result


class Bridge:
    def __init__(self, config_path=None):
        raw = config_path or os.environ.get('WORKFLOW_BRIDGE_CONFIG')
        self.path = Path(raw).resolve() if raw else None

    def config(self):
        if not self.path or not self.path.exists(): return None
        c = json.loads(self.path.read_text())
        return c if c.get('enabled') else None

    @contextmanager
    def locked(self):
        if not self.path: raise ValueError('bridge is not configured')
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            p = self.path.with_suffix('.state.json')
            s = json.loads(p.read_text()) if p.exists() else {'requests':[], 'notices':[], 'active':None, 'worker_at':None}
            yield s
            write_json(p, s)

    def status(self, request_id=None):
        c = self.config()
        if not c: return {'enabled':False}
        with self.locked() as s:
            request = next((r for r in reversed(s['requests']) if not request_id or r['id']==request_id), None)
            return {'enabled':True, 'session_id':c['session_id'], 'thread_url':c.get('thread_url'),
                    'worker_at':s.get('worker_at'), 'request':request,
                    'notice_errors':sum(n['status'] not in ('sent','cancelled') for n in s['notices']),
                    'source_error':s.get('source_error')}

    def enqueue(self, payload):
        c = self.config()
        if not c: raise ValueError('세션 연결이 설정되지 않았습니다.')
        if not isinstance(payload, dict) or set(payload) != {'request_id','page','title'}:
            raise ValueError('request_id, page, title required')
        rid, page, title = (payload[k] for k in ('request_id','page','title'))
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',rid): raise ValueError('invalid request_id')
        if not isinstance(page,str) or len(page)>2000 or not page.startswith('/') or page.startswith('//') or any(x in page for x in ('\n','\r','\\')):
            raise ValueError('relative page required')
        if not isinstance(title,str) or len(title)>300: raise ValueError('invalid title')
        with self.locked() as s:
            for r in s['requests']:
                if r['id']==rid:
                    if (r['page'], r['title']) != (page,title): raise ValueError('request_id content mismatch')
                    return r
            # Repeated clicks / multiple tabs during the cooldown return the same receipt.
            if s['requests'] and time.time()-s['requests'][-1]['created_epoch']<20: return s['requests'][-1]
            r = {'id':rid,'page':page,'title':title,'session_id':c['session_id'], 'status':'queued','at':now(),'created_epoch':time.time()}
            s['requests'].append(r)
            return r

    def adapter(self, c, action, message=''):
        root = Path(c['connector_root']).expanduser().resolve()
        executable = root/'node_modules/tsx/dist/cli.mjs'
        node = c.get('node_command', 'node')
        script = Path(__file__).resolve().parent.parent/'integrations/orca-send.mts'
        result = subprocess.run([node, str(executable), str(script)], input=json.dumps({
            'root':str(root),'command':c['orca_command'],'session_id':c['session_id'], 'action':action,'text':message}),
            text=True, capture_output=True, timeout=75, cwd=root)
        try: reply=json.loads(result.stdout)
        except ValueError: raise RuntimeError('Orca adapter failed; check connector installation (raw output withheld)')
        return reply

    def discord(self, c, method, route, body=None):
        config = json.loads(Path(c['connector_config']).expanduser().read_text())
        token = config['discord']['token']
        request = Request('https://discord.com/api/v10'+route,
            data=json.dumps(body).encode() if body is not None else None, method=method,
            headers={'Authorization':'Bot '+token,'Content-Type':'application/json','User-Agent':'WorkflowBridge/1.0'})
        try:
            with urlopen(request, timeout=20) as response:
                raw=response.read(); return json.loads(raw) if raw else {}
        except HTTPError as exc:
            # Never include response bodies, authorization, or configuration in errors.
            raise RuntimeError('Discord HTTP '+str(exc.code)) from None

    def tick(self, source=None):
        c=self.config()
        if not c: return {'enabled':False}
        # Separate worker lock prevents overlap; writes from the web remain quick.
        with self.path.with_suffix('.worker.lock').open('a') as worker:
            try: fcntl.flock(worker, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return {'busy':True}
            self._tick(c,source)
        return self.status()

    def _tick(self,c,source):
        with self.locked() as s:
            s['worker_at']=now()
            # A previous worker died after claiming a terminal send. Never resend.
            for r in s['requests']:
                if r['status']=='sending': r.update(status='unknown',error='전송 중 중단됨. 원래 세션에서 수신 여부를 확인하세요.')
            pending=next((dict(r) for r in s['requests'] if r['status']=='queued'),None)
            if pending:
                r=next(r for r in s['requests'] if r['id']==pending['id'])
                r['status']='sending';r['attempted_at']=now()
        if pending:
            if pending['session_id']!=c['session_id']:
                reply={'status':'failed','error':'설정의 세션이 변경되어 이전 요청을 보내지 않았습니다.'}
            else:
                message=('사용자가 웹에서 작업을 마쳤습니다. 새 댓글과 변경 내용을 확인하고 이어서 진행해 주세요.\n'
                    f'페이지: {c["base_url"].rstrip("/")}{pending["page"]}\n'
                    f'화면: {pending["title"]}\n요청 ID: {pending["id"]}')
                try: reply=self.adapter(c,'send',message)
                except Exception: reply={'status':'unknown','error':'전송 결과를 확인하지 못했습니다. 중복 전송 전 원래 세션을 확인하세요.'}
            with self.locked() as s:
                r=next(r for r in s['requests'] if r['id']==pending['id'])
                r.update({k:v for k,v in reply.items() if k in ('status','error','accepted','turnStarted','target')}); r['finished_at']=now()
        try:
            if source is None:
                with urlopen(c['source_url'],timeout=20) as response: source=json.load(response)
            items=attention_items(source,c['source_kind'])
            active={x['id']:x['revision'] for x in items}
            with self.locked() as s:
                previous=s['active'];s['active']=active;s['source_error']=None
                # First successful snapshot is a baseline, not a flood of old work.
                if previous is not None:
                    for item in items:
                        if previous.get(item['id'])!=item['revision']:
                            nonce=hashlib.sha256((item['id']+item['revision']+now()).encode()).hexdigest()[:24]
                            s['notices'].append(dict(item,nonce=nonce,status='pending',attempts=0,at=now()))
                for n in s['notices']:
                    if n['status']=='pending' and active.get(n['id'])!=n['revision']: n['status']='cancelled'
        except Exception:
            with self.locked() as s: s['source_error']='확인 목록 조회 실패. 마지막 정상 기준을 유지합니다.'
        # Bounded batch; retry failures at most 5 times with backoff. Stable nonce
        # plus recent-history lookup handles an ambiguous POST response / restart.
        with self.locked() as s:
            notices=[dict(n) for n in s['notices'] if n['status']=='pending' and n['attempts']<5 and time.time()>=n.get('retry_at',0)][:5]
        for n in notices:
            try:
                thread=c['thread_id']; marker='workflow:'+n['nonce']
                recent=self.discord(c,'GET',f'/channels/{thread}/messages?limit=100')
                found=next((m for m in recent if m.get('nonce')==n['nonce'] or marker in m.get('content','')),None)
                if found: sent=found
                else:
                    url=n['url'] if n['url'].startswith('https://') else c['base_url'].rstrip('/')+'/'+n['url'].lstrip('/')
                    mention=c.get('notify_user_id')
                    prefix=f'<@{mention}> ' if mention else ''
                    sent=self.discord(c,'POST',f'/channels/{thread}/messages',{
                        'content':f'{prefix}지금 확인 · 새 항목/새 버전\n**{n["title"][:250]}**\n{url}\n`{marker}`',
                        'allowed_mentions':{'parse':[],'users':[mention] if mention else []},'nonce':n['nonce'],'enforce_nonce':True})
                update={'status':'sent','message_id':sent['id'],'sent_at':now(),'error':None}
            except Exception as exc:
                update={'error':str(exc) if isinstance(exc,RuntimeError) else 'Discord delivery failed','retry_at':time.time()+min(900,30*2**n['attempts'])}
            with self.locked() as s:
                row=next(x for x in s['notices'] if x['nonce']==n['nonce']);row.update(update);row['attempts']+=1
                if row['status']=='pending' and row['attempts']>=5: row['status']='failed'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    p.add_argument('action',choices=['check','status','once','watch'])
    args=p.parse_args();b=Bridge(args.config)
    if args.action=='check': print(json.dumps(b.adapter(b.config(),'check'),ensure_ascii=False));return
    if args.action=='status': print(json.dumps(b.status(),ensure_ascii=False,indent=2));return
    if args.action=='once': print(json.dumps(b.tick(),ensure_ascii=False));return
    while True:
        try: b.tick()
        except Exception: print('Workflow bridge cycle failed; inspect configuration/state.',flush=True)
        time.sleep(15)

if __name__=='__main__': main()
