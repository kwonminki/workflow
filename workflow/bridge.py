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
import shutil
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

    def prepare(self, base_url):
        """Optional server-owned bootstrap; browser never supplies executable paths."""
        root = os.environ.get('WORKFLOW_CONNECTOR_ROOT')
        if not self.path or self.path.exists() or not root: return
        base_url=os.environ.get('WORKFLOW_PUBLIC_URL',base_url).rstrip('/')
        parsed=urlsplit(base_url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('WORKFLOW_PUBLIC_URL must be an HTTP(S) origin')
        root = Path(root).expanduser().resolve()
        cp = root / '.connect/config.json'
        installed = json.loads(cp.read_text())
        c = {'enabled':True, 'connector_root':str(root), 'connector_config':str(cp),
             'node_command':str(Path(shutil.which('node') or '/missing-node').resolve()),
             'orca_command':installed.get('direct',{}).get('orca',{}).get('command','orca'),
             'session_id':None, 'discord_enabled':False, 'base_url':base_url,
             'source_kind':'workflow','source_url':base_url+'/api/state'}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_lock():
            if not self.path.exists(): write_json(self.path,c)

    @contextmanager
    def settings_lock(self):
        if not self.path: raise ValueError('서버 연결 준비가 필요합니다. 요청문을 에이전트에게 전달해 주세요.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.settings.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            yield

    def control(self, payload):
        if not isinstance(payload,dict): raise ValueError('연결 요청을 확인해 주세요.')
        action=payload.get('action')
        fields={'sessions':set(), 'check_session':set(), 'connect_session':{'session_id'},
                'connect_discord':{'thread_url'}, 'discord_toggle':{'on'}}
        if action not in fields or set(payload)!={'action'}|fields[action]:
            raise ValueError('지원하지 않는 연결 설정입니다.')
        # Serialize configuration and delivery. A completed OFF prevents subsequent
        # Discord sends; a request already in flight may finish before OFF returns.
        with self.settings_lock():
            c=self.config()
            if not c: raise ValueError('서버 연결 준비가 필요합니다. 요청문을 에이전트에게 전달해 주세요.')
            if action=='sessions':
                try: result=self.adapter(c,'list')
                except Exception: raise ValueError('세션 목록을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.') from None
                if result.get('status')!='ready': raise ValueError('Orca 연결을 확인해 주세요.')
                return {'sessions':result.get('sessions',[])}
            if action in ('check_session','connect_session'):
                sid=payload.get('session_id',c.get('session_id'))
                if not isinstance(sid,str) or not re.fullmatch(r'[0-9a-fA-F-]{36}',sid):
                    raise ValueError('연결할 Codex 세션 ID를 선택해 주세요.')
                proposed=dict(c,session_id=sid)
                try: result=self.adapter(proposed,'check')
                except Exception: result={'status':'failed'}
                if action=='connect_session' and result.get('status')!='ready':
                    raise ValueError('이 세션에 연결할 수 없습니다. 실행 중인 메인 세션을 선택해 주세요.')
                if action=='connect_session': write_json(self.path,proposed)
                with self.locked() as state:
                    state['session_check']={'session_id':sid,'status':result.get('status','failed'),'at':now()}
            elif action=='connect_discord':
                raw=payload['thread_url']
                match=re.fullmatch(r'https://(?:www\.)?discord\.com/channels/(\d{15,22})/(\d{15,22})/?',raw) if isinstance(raw,str) else None
                if not match: raise ValueError('Discord 스레드 주소를 붙여 넣어 주세요.')
                try:
                    installed=json.loads(Path(c['connector_config']).expanduser().read_text())
                    if match[1]!=installed['discord']['guildId']: raise ValueError('봇이 설정된 Discord 서버의 스레드를 사용해 주세요.')
                    info=self.discord(c,'GET','/channels/'+match[2])
                    if info.get('guild_id')!=match[1] or info.get('type') not in (11,12):
                        raise ValueError('텍스트 채널 대신 알림을 받을 스레드를 선택해 주세요.')
                    if info.get('thread_metadata',{}).get('locked'): raise ValueError('잠긴 스레드에는 연결할 수 없습니다.')
                    self.discord(c,'GET',f'/channels/{match[2]}/messages?limit=1')
                except ValueError: raise
                except Exception: raise ValueError('봇이 이 스레드에 접근할 수 있는지 확인해 주세요.') from None
                # Membership allows subsequent messages in private/archived threads.
                try: self.discord(c,'PUT',f'/channels/{match[2]}/thread-members/@me')
                except Exception: raise ValueError('봇이 스레드에 참여할 수 없습니다. 권한을 확인해 주세요.') from None
                changed=c.get('thread_id')!=match[2]
                c.update(thread_id=match[2],thread_url=f'https://discord.com/channels/{match[1]}/{match[2]}')
                if changed:
                    c['discord_enabled']=False
                    with self.locked() as state:
                        state['active']=None
                        for n in state['notices']:
                            if n['status']=='pending': n.update(status='cancelled',reason='notification destination changed')
                write_json(self.path,c)
            elif action=='discord_toggle':
                if type(payload['on']) is not bool: raise ValueError('알림 켜기/끄기를 선택해 주세요.')
                if payload['on'] and not c.get('thread_id'): raise ValueError('Discord 스레드를 먼저 연결해 주세요.')
                on=payload['on']
                if c.get('discord_enabled',bool(c.get('thread_id')))!=on:
                    c['discord_enabled']=on;write_json(self.path,c)
                    with self.locked() as state:
                        state['active']=None
                        for n in state['notices']:
                            if n['status']=='pending': n.update(status='cancelled',reason='notifications switched off/on')
        return self.status()

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
            return {'enabled':True, 'session_id':c.get('session_id'), 'thread_url':c.get('thread_url'),
                    'discord_configured':bool(c.get('thread_id')),
                    'discord_on':c.get('discord_enabled',True) and bool(c.get('thread_id')),
                    'session_configured':bool(c.get('session_id')), 'session_check':s.get('session_check'),
                    'worker_at':s.get('worker_at'), 'request':request,
                    'notice_errors':sum(n['status'] not in ('sent','cancelled') for n in s['notices']),
                    'source_error':s.get('source_error')}

    def enqueue(self, payload):
        c = self.config()
        if not c or not c.get('session_id'): raise ValueError('메인 세션을 먼저 연결해 주세요.')
        if not isinstance(payload, dict) or set(payload)-{'request_id','page','title','message'} or not {'request_id','page','title'} <= set(payload):
            raise ValueError('request_id, page, title required')
        rid, page, title = (payload[k] for k in ('request_id','page','title'))
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',rid): raise ValueError('invalid request_id')
        if not isinstance(page,str) or len(page)>2000 or not page.startswith('/') or page.startswith('//') or any(x in page for x in ('\n','\r','\\')):
            raise ValueError('relative page required')
        if not isinstance(title,str) or len(title)>300: raise ValueError('invalid title')
        message=payload.get('message','')
        if not isinstance(message,str) or len(message)>4000: raise ValueError('추가 메시지는 4000자까지 작성할 수 있습니다.')
        with self.locked() as s:
            for r in s['requests']:
                if r['id']==rid:
                    if (r['page'], r['title'], r.get('message','')) != (page,title,message): raise ValueError('request_id content mismatch')
                    return r
            # Repeated clicks / multiple tabs during the cooldown return the same receipt.
            if s['requests'] and time.time()-s['requests'][-1]['created_epoch']<20:
                last=s['requests'][-1]
                if (last['page'],last['title'],last.get('message',''),last['session_id'])==(page,title,message,c['session_id']): return last
            r = {'id':rid,'page':page,'title':title,'message':message,'session_id':c['session_id'], 'status':'queued','at':now(),'created_epoch':time.time()}
            s['requests'].append(r)
            return r

    def adapter(self, c, action, message=''):
        root = Path(c['connector_root']).expanduser().resolve()
        executable = root/'node_modules/tsx/dist/cli.mjs'
        node = c.get('node_command', 'node')
        script = Path(__file__).resolve().parent.parent/'integrations/orca-send.mts'
        result = subprocess.run([node, str(executable), str(script)], input=json.dumps({
            'root':str(root),'command':c['orca_command'],'session_id':c.get('session_id'), 'action':action,'text':message}),
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
                if pending.get('message'): message+='\n추가 메시지:\n'+pending['message']
                try:
                    with self.settings_lock():
                        latest=self.config()
                        if not latest or latest.get('session_id')!=pending['session_id']:
                            reply={'status':'failed','error':'연결 세션이 변경되었습니다.'}
                        else: reply=self.adapter(latest,'send',message)
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
                if previous is not None and c.get('discord_enabled',True) and c.get('thread_id'):
                    for item in items:
                        if previous.get(item['id'])!=item['revision']:
                            nonce=hashlib.sha256((item['id']+item['revision']+now()).encode()).hexdigest()[:24]
                            s['notices'].append(dict(item,nonce=nonce,status='pending',attempts=0,at=now(),thread_id=c['thread_id']))
                for n in s['notices']:
                    if n['status']=='pending' and active.get(n['id'])!=n['revision']: n['status']='cancelled'
        except Exception:
            with self.locked() as s: s['source_error']='확인 목록 조회 실패. 마지막 정상 기준을 유지합니다.'
        # Bounded batch; retry failures at most 5 times with backoff. Stable nonce
        # plus recent-history lookup handles an ambiguous POST response / restart.
        with self.locked() as s:
            notices=[dict(n) for n in s['notices'] if n['status']=='pending' and n['attempts']<5 and time.time()>=n.get('retry_at',0)][:5]
        for n in notices:
            with self.settings_lock():
                current=self.config()
                if not current or not current.get('discord_enabled',True) or not current.get('thread_id'):
                    continue
                with self.locked() as s:
                    saved=next(x for x in s['notices'] if x['nonce']==n['nonce'])
                    if saved['status']!='pending': continue
                if n.get('thread_id',c.get('thread_id'))!=current['thread_id']: continue
                self.deliver_notice(current,n)

    def deliver_notice(self,c,n):
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
