import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from workflow.store import Store, Conflict, pending, validate_graph
from workflow.demo import populate
from workflow.server import make_server
ROOT=Path(__file__).resolve().parents[1]

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.store.initialize('Synthetic');populate(self.store)
    def tearDown(self):self.temp.cleanup()
    def comment(self):return self.store.change('comment',{'target':{'kind':'node','id':'implementation'},'text':'new opinion'})['record']
    def reply(self,t,**extra):return self.store.change('reply',{'thread_id':t['id'],'reply_to':t['messages'][0]['id'],'text':'Processed','outcome':'applied','evidence':['#graph'],**extra},'worker')['record']
    def cli(self,*args):return subprocess.run([sys.executable,'-m','workflow','--data',self.temp.name,*args],cwd=ROOT,capture_output=True,text=True)
    def test_init_does_not_overwrite(self):
        before=self.store.path.read_bytes()
        with self.assertRaises(ValueError):self.store.initialize('New')
        self.assertEqual(before,self.store.path.read_bytes())
    def test_stale_revision(self):
        before=self.store.path.read_bytes()
        with self.assertRaises(Conflict):self.store.change('node',{'id':'implementation','title':'Lost'},revision=0)
        self.assertEqual(before,self.store.path.read_bytes())
    def test_cycle_is_atomic(self):
        before=self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'cycle'):self.store.change('node',{'id':'contract','depends_on':['review']})
        self.assertEqual(before,self.store.path.read_bytes())
    def test_large_graph(self):validate_graph([{'id':str(i),'depends_on':[str(i-1)] if i else []} for i in range(3000)])
    def test_invalid_id_and_dependency(self):
        for data in [{'id':'x/y','title':'bad'},{'id':'implementation','depends_on':['missing']}]:
            with self.assertRaises(ValueError):self.store.change('node',data)
    def test_done_needs_reason_and_evidence(self):
        with self.assertRaises(ValueError):self.store.change('node',{'id':'implementation','status':'done'})
        self.store.change('node',{'id':'implementation','status':'done','completion':'bounded test','evidence':['artifact.json']})
    def test_pending_seen_applied_followup(self):
        t=self.comment();self.reply(t,outcome='seen',evidence=[]);self.assertEqual(len(pending(self.store.read())),1)
        r=self.reply(t);self.assertEqual(pending(self.store.read()),[])
        self.store.change('followup',{'thread_id':t['id'],'reply_to':r['id'],'text':'followup'})
        self.assertEqual(len(pending(self.store.read())[0]['pending_message_ids']),1)
    def test_apply_and_defer_validation(self):
        t=self.comment()
        with self.assertRaises(ValueError):self.reply(t,evidence=[])
        with self.assertRaises(ValueError):self.reply(t,outcome='deferred',workflow_node='missing')
        self.reply(t,outcome='deferred',workflow_node='implementation');self.assertEqual(pending(self.store.read()),[])
    def test_read_is_separate(self):
        t=self.comment();r=self.reply(t,outcome='seen')
        with self.assertRaises(ValueError):self.store.change('read',{'thread_id':t['id'],'message_id':r['id']},'worker')
        self.store.change('read',{'thread_id':t['id'],'message_id':r['id']})
        self.assertEqual(len(pending(self.store.read())),1)
        self.assertIsNone(self.reply(t)['read_at'])
        self.assertIsNotNone(self.store.read()['threads'][0]['messages'][1]['read_at'])
    def test_session_history(self):
        t=self.comment();self.reply(t)
        self.store.change('agent',{'id':'worker','role':'Implementation','session':'next-session'})
        self.assertEqual(self.store.read()['threads'][0]['messages'][-1]['author']['session'],'example-session-002')
    def test_unicode_anchor_and_history(self):
        d=self.store.change('document',{'id':'unicode','title':'Unicode','body':'앞 😀 의견\n\n뒤'})['record']
        anchor={'start':2,'end':6,'quote':'😀 의견','revision':d['revision']}
        self.store.change('comment',{'target':{'kind':'document','id':'unicode'},'text':'opinion','anchor':anchor})
        self.store.change('document',{'id':'unicode','title':'Unicode','body':'수정된 문서'})
        with self.assertRaises(ValueError):self.store.change('comment',{'target':{'kind':'document','id':'unicode'},'text':'stale','anchor':anchor})
        self.assertEqual(self.store.read()['documents'][-1]['history'][0]['body'],'앞 😀 의견\n\n뒤')
        self.assertEqual(self.store.read()['threads'][-1]['anchor']['quote'],'😀 의견')
    def test_real_command_records_failure_and_artifact(self):
        out=Path(self.temp.name)/'result.txt'
        r=self.cli('run','--node','implementation','--agent','worker','--summary','bounded execution','--output',str(out),'--',sys.executable,'-c',f'from pathlib import Path;Path({str(out)!r}).write_text("ok");raise SystemExit(7)')
        self.assertEqual(r.returncode,7,r.stderr);run=self.store.read()['runs'][-1]
        self.assertEqual(run['exit_code'],7);self.assertEqual(run['status'],'failed')
        self.assertEqual(run['output_facts'][0]['bytes'],2);self.assertEqual(len(run['output_facts'][0]['sha256']),64)
        self.assertEqual(self.store.read()['nodes'][1]['status'],'planned')
    def test_real_command_success(self):
        result=self.cli('run','--node','implementation','--agent','worker','--summary','success','--',sys.executable,'-c','print("example")')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.store.read()['runs'][-1]['status'],'succeeded')
    def test_launch_error_recorded(self):
        r=self.cli('run','--node','implementation','--agent','worker','--summary','missing','--','/no-such-program')
        self.assertEqual(r.returncode,127);self.assertEqual(self.store.read()['runs'][-1]['status'],'failed')
    def test_inbox_blocks_new_run(self):
        self.comment();self.assertEqual(self.cli('inbox','--require-clear').returncode,3)
        r=self.cli('run','--node','implementation','--agent','worker','--summary','blocked','--',sys.executable,'-c','print("never")')
        self.assertEqual(r.returncode,1);self.assertEqual(self.store.read()['runs'],[])
    def test_concurrent_writers(self):
        errors=[]
        def write(i):
            try:self.store.change('comment',{'target':{'kind':'node','id':'implementation'},'text':f'comment {i}'})
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=write,args=(i,)) for i in range(12)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(self.store.read()['threads']),12)
    def test_project_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            other=Store(directory);other.initialize('Other');self.comment();self.assertEqual(other.read()['threads'],[])

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.store.initialize('HTTP');populate(self.store)
        try:self.server=make_server(self.store,0)
        except PermissionError as exc:self.temp.cleanup();self.skipTest(f'socket restricted: {exc}')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        if hasattr(self,'server'):self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
        try:
            with urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except HTTPError as r:
            with r:return r.code,r.read(),r.headers
    def test_get_path_boundary(self):
        self.assertEqual(self.request('/api/state')[0],200);self.assertEqual(self.request('/../../etc/passwd')[0],404)
        self.assertEqual(self.request('/state.json')[0],404);self.assertEqual(self.request('/')[0],200)
        self.assertIn("script-src 'self'",self.request('/')[2]['Content-Security-Policy'])
    def test_origin_host_rejection(self):
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/action',{})[0],403)
        self.assertEqual(self.request('/api/action',{},headers={'Origin':'https://evil.example'})[0],403)
    def test_save_conflict(self):
        headers={'Origin':self.base,'Content-Type':'application/json'}
        body={'action':'comment','revision':self.store.read()['revision'],'data':{'target':{'kind':'node','id':'implementation'},'text':'<script>alert(1)</script>'}}
        self.assertEqual(self.request('/api/action',body,headers)[0],200);self.assertEqual(self.request('/api/action',body,headers)[0],409)
        self.assertEqual(self.store.read()['threads'][0]['messages'][0]['text'],'<script>alert(1)</script>')
    def test_no_command_or_agent_api(self):
        headers={'Origin':self.base,'Content-Type':'application/json'}
        for action in ['run_start','run_finish','run','agent','reply','document']:
            self.assertEqual(self.request('/api/action',{'action':action,'revision':0,'data':{}},headers)[0],400)

class HandlerTests(unittest.TestCase):
    """Exercise actual HTTP parsing/handler without opening a network socket."""
    def setUp(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.store.initialize('HTTP in memory');populate(self.store)
        with patch('workflow.server.ThreadingHTTPServer') as factory:
            make_server(self.store,8040)
            self.handler=factory.call_args.args[1]
        self.server=SimpleNamespace(server_port=8040)
    def tearDown(self):self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        import io
        payload=json.dumps(body).encode() if body is not None else b''
        fields={'Host':'127.0.0.1:8040','Connection':'close',**(headers or {})}
        if body is not None:fields['Content-Length']=str(len(payload))
        raw=(('POST' if body is not None else 'GET')+' '+path+' HTTP/1.1\r\n'+''.join(f'{k}: {v}\r\n' for k,v in fields.items())+'\r\n').encode()+payload
        class Socket:
            def __init__(self):self.output=bytearray()
            def makefile(self,*_args):return io.BytesIO(raw)
            def sendall(self,data):self.output.extend(data)
        sock=Socket();self.handler(sock,('127.0.0.1',12345),self.server)
        head,body=bytes(sock.output).split(b'\r\n\r\n',1)
        return int(head.split()[1]),head,body
    def test_static_allowlist_and_state(self):
        for path in ['/','/app.js','/style.css','/api/state']:self.assertEqual(self.request(path)[0],200)
        for path in ['/../../etc/passwd','/state.json','/docs/README.md']:self.assertEqual(self.request(path)[0],404)
    def test_host_origin_and_type(self):
        self.assertEqual(self.request('/',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/action',{})[0],403)
        self.assertEqual(self.request('/api/action',{},headers={'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.request('/api/action',{},headers={'Origin':'http://127.0.0.1:8040'})[0],415)
    def test_comment_and_stale_revision(self):
        h={'Origin':'http://127.0.0.1:8040','Content-Type':'application/json'}
        data={'action':'comment','revision':self.store.read()['revision'],'data':{'target':{'kind':'node','id':'implementation'},'text':'<img src=x onerror=alert(1)>'}}
        self.assertEqual(self.request('/api/action',data,h)[0],200)
        self.assertEqual(self.request('/api/action',data,h)[0],409)
        self.assertEqual(self.store.read()['threads'][0]['messages'][0]['text'],'<img src=x onerror=alert(1)>')
    def test_browser_cannot_execute_or_impersonate(self):
        h={'Origin':'http://127.0.0.1:8040','Content-Type':'application/json'}
        for action in ['agent','reply','document','run','run_start','run_finish']:
            self.assertEqual(self.request('/api/action',{'action':action,'revision':0,'data':{}},h)[0],400)
    def test_csp(self):
        head=self.request('/')[1]
        self.assertIn(b"script-src 'self'",head);self.assertIn(b"object-src 'none'",head)
        source=(ROOT/'workflow/static/app.js').read_text()
        self.assertNotIn('.innerHTML',source);self.assertNotIn('eval(',source)

if __name__=='__main__':unittest.main()
