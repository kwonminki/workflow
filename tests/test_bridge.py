import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workflow.bridge import Bridge, attention_items, write_json


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'bridge.json'
        write_json(self.path,{'enabled':True,'session_id':'session-a','base_url':'http://127.0.0.1:8040','source_kind':'workflow','thread_id':'123'})
        self.b=Bridge(self.path)
        self.calls=[]
        self.b.adapter=lambda c,a,message='': self.calls.append(message) or {'status':'accepted','accepted':True,'turnStarted':False}
        self.b.discord=lambda c,m,r,body=None: [] if m=='GET' else {'id':'message-1'}
    def payload(self,rid='request-0001'):
        return {'request_id':rid,'page':'/#document/design','title':'design'}
    def source(self,status='review',title='decision'):
        return {'nodes':[{'id':'one','status':status,'title':title,'goal':'goal','next_action':'choose'}]}
    def state(self):return json.loads(self.path.with_suffix('.state.json').read_text())
    def test_disabled(self):
        self.assertEqual(Bridge('/nonexistent/bridge').status(),{'enabled':False})
    def test_no_commands_and_no_absolute_urls(self):
        for p in [dict(self.payload(),command='shell'),dict(self.payload(),page='//external/'),dict(self.payload(),page='https://external/'),dict(self.payload(),page='/x\ncommand')]:
            with self.assertRaises(ValueError):self.b.enqueue(p)
    def test_duplicate_click_once(self):
        self.b.enqueue(self.payload());self.b.enqueue(self.payload())
        self.b.tick(self.source());self.b.tick(self.source())
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.b.status()['request']['status'],'accepted')
        with self.assertRaises(ValueError):self.b.enqueue(dict(self.payload(),page='/other'))
    def test_multiple_tab_cooldown(self):
        self.assertEqual(self.b.enqueue(self.payload()),self.b.enqueue(self.payload('request-0002')))
    def test_session_change_never_redirects_old_request(self):
        self.b.enqueue(self.payload());c=self.b.config();c['session_id']='session-b';write_json(self.path,c)
        self.b.tick(self.source());self.assertFalse(self.calls);self.assertEqual(self.b.status()['request']['status'],'failed')
    def test_ambiguous_delivery_never_retried(self):
        self.b.enqueue(self.payload())
        def timeout(*args):raise TimeoutError()
        self.b.adapter=timeout;self.b.tick(self.source())
        self.assertEqual(self.b.status()['request']['status'],'unknown')
        self.b.adapter=lambda *a:self.fail('must not retry');self.b.tick(self.source())
    def test_worker_crash_after_claim(self):
        self.b.enqueue(self.payload())
        with self.b.locked() as s:s['requests'][0]['status']='sending'
        self.b.tick(self.source());self.assertFalse(self.calls);self.assertEqual(self.b.status()['request']['status'],'unknown')
    def test_baseline_new_revision_and_reopen(self):
        self.b.tick(self.source());self.assertEqual(self.state()['notices'],[])
        self.b.tick(self.source(title='new question'));self.assertEqual(len(self.state()['notices']),1)
        self.b.tick(self.source(title='new question'));self.assertEqual(len(self.state()['notices']),1)
        self.b.tick(self.source(status='done'));self.b.tick(self.source(title='new question'))
        self.assertEqual(len(self.state()['notices']),2)
    def test_discord_error_retry_and_duplicate_recovery(self):
        self.b.tick(self.source())
        def fail(*a):raise RuntimeError('Discord HTTP 503')
        self.b.discord=fail;self.b.tick(self.source(title='new question'))
        with self.b.locked() as s:
            n=s['notices'][0];self.assertEqual(n['status'],'pending');n['retry_at']=0;nonce=n['nonce']
        def recovered(c,m,r,body=None):
            if m=='POST':self.fail('already delivered')
            return [{'id':'already-there','nonce':nonce}]
        self.b.discord=recovered;self.b.tick(self.source(title='new question'))
        self.assertEqual(self.state()['notices'][0]['message_id'],'already-there')
    def test_hub_filters_only_home_attention(self):
        value={'notion':[{'id':'n','updated_at':'1','title':'doc','url':'#doc','locally_read':True}],
               'human_requests':[{'id':'q','revision':'1','title':'question','url':'#q','status':'open','answered':True},
                                 {'id':'r','revision':'1','title':'result','url':'#r','status':'reference','category':'work_result','answered':False}],
               'samples':[{'id':'s','revision':'1','requests':[],'review':None}]}
        self.assertEqual([x['id'] for x in attention_items(value,'hub')],['request:r'])
    def test_pending_comment_alerts_do_not_mark_read(self):
        value={'nodes':[],'threads':[{'target':{'id':'plan'},'messages':[{'id':'user1','kind':'user'}]}]}
        original=json.dumps(value)
        self.assertEqual(attention_items(value,'workflow')[0]['id'],'comment:user1')
        self.assertEqual(json.dumps(value),original)
        value['threads'][0]['messages'].append({'id':'reply1','kind':'agent','reply_to':'user1','outcome':'applied'})
        self.assertEqual(attention_items(value,'workflow'),[])
    def test_source_failure_does_not_erase_baseline(self):
        self.b.tick(self.source())
        with patch('workflow.bridge.urlopen',side_effect=OSError()):self.b.tick()
        self.assertEqual(len(self.state()['active']),1);self.assertTrue(self.state()['source_error'])

    def test_additional_message_exact_and_distinct_requests(self):
        self.b.enqueue(dict(self.payload(),message='첫째\n둘째 <script>'))
        self.b.enqueue(dict(self.payload('request-0002'),message='다른 내용'))
        self.assertEqual(len(self.state()['requests']),2)
        with self.assertRaises(ValueError):self.b.enqueue(dict(self.payload(),message='수정'))
        self.b.tick(self.source());self.assertIn('첫째\n둘째 <script>',self.calls[0])
        self.b.tick(self.source());self.assertIn('다른 내용',self.calls[1])
        with self.assertRaises(ValueError):self.b.enqueue(dict(self.payload('request-0003'),message='x'*4001))

    def test_discord_off_does_not_disable_session_or_catch_up(self):
        self.b.tick(self.source())
        self.b.control({'action':'discord_toggle','on':False})
        self.assertFalse(Bridge(self.path).status()['discord_on'])
        self.b.enqueue(self.payload());self.b.tick(self.source(title='off change'))
        self.assertEqual(len(self.calls),1);self.assertFalse(self.state()['notices'])
        self.b.control({'action':'discord_toggle','on':True})
        self.b.tick(self.source(title='off change'));self.assertFalse(self.state()['notices'])
        self.b.tick(self.source(title='new after on'));self.assertEqual(len(self.state()['notices']),1)

    def test_off_cancels_queued_discord_retry(self):
        self.b.tick(self.source())
        def fail(*args):raise RuntimeError('Discord HTTP 503')
        self.b.discord=fail;self.b.tick(self.source(title='change'))
        self.assertEqual(self.state()['notices'][0]['status'],'pending')
        self.b.control({'action':'discord_toggle','on':False})
        self.assertEqual(self.state()['notices'][0]['status'],'cancelled')

    def test_control_rejects_executables_and_invalid_values(self):
        for payload in [{'action':'connect_session','session_id':'x','command':'sh'},
                        {'action':'discord_toggle','on':'false'}, {'action':'connect_session','session_id':'/tmp/file'},
                        {'action':'connect_discord','thread_url':'https://evil.invalid/123'}, {'action':'anything'}]:
            with self.assertRaises(ValueError):self.b.control(payload)

    def test_session_connect_validates_and_preserves_old_pending_target(self):
        self.b.enqueue(self.payload());sid='00000000-0000-0000-0000-000000000001'
        self.b.adapter=lambda *a:{'status':'failed'}
        with self.assertRaises(ValueError):self.b.control({'action':'connect_session','session_id':sid})
        self.assertEqual(self.b.config()['session_id'],'session-a')
        self.b.adapter=lambda *a:{'status':'ready'}
        result=self.b.control({'action':'connect_session','session_id':sid})
        self.assertEqual(result['session_id'],sid);self.assertEqual(result['session_check']['status'],'ready')
        self.b.tick(self.source());self.assertEqual(self.state()['requests'][0]['status'],'failed')

    def test_discord_connection_checks_guild_type_and_preserves_off(self):
        guild='123456789012345678';thread='223456789012345678'
        config=Path(self.tmp.name)/'connector.json';write_json(config,{'discord':{'guildId':guild}})
        c=self.b.config();c['connector_config']=str(config);write_json(self.path,c)
        self.b.discord=lambda c,m,r,body=None: {'guild_id':guild,'type':0} if r=='/channels/'+thread else []
        with self.assertRaises(ValueError):self.b.control({'action':'connect_discord','thread_url':f'https://discord.com/channels/{guild}/{thread}'})
        self.b.discord=lambda c,m,r,body=None: {'guild_id':guild,'type':11} if r=='/channels/'+thread else []
        result=self.b.control({'action':'connect_discord','thread_url':f'https://discord.com/channels/{guild}/{thread}'})
        self.assertTrue(result['discord_configured']);self.assertFalse(result['discord_on'])
        with self.assertRaises(ValueError):self.b.control({'action':'connect_discord','thread_url':f'https://discord.com/channels/923456789012345678/{thread}'})

    def test_switch_while_polling_cannot_send_to_new_destination(self):
        self.b.tick(self.source())
        def fail(*args):raise RuntimeError('Discord HTTP 503')
        self.b.discord=fail;self.b.tick(self.source(title='change'))
        with self.b.locked() as s:s['notices'][0]['retry_at']=0
        c=self.b.config();c['thread_id']='456';write_json(self.path,c)
        self.b.discord=lambda *a:self.fail('old notice cannot be redirected')
        self.b.tick(self.source(title='change'))

    def test_optional_bootstrap_has_no_token_or_connected_destinations(self):
        root=Path(self.tmp.name)/'connector';(root/'.connect').mkdir(parents=True)
        write_json(root/'.connect/config.json',{'discord':{'token':'synthetic-fixture-only'},'direct':{'orca':{'command':'/fixed/orca'}}})
        path=Path(self.tmp.name)/'new-workspace/bridge.json';b=Bridge(path)
        with patch.dict('os.environ',{'WORKFLOW_CONNECTOR_ROOT':str(root),'WORKFLOW_PUBLIC_URL':'http://192.168.1.20:18743'}):
            b.prepare('http://127.0.0.1:18743')
        c=b.config();self.assertIsNone(c['session_id']);self.assertFalse(c['discord_enabled'])
        self.assertEqual(c['base_url'],'http://192.168.1.20:18743');self.assertNotIn('synthetic-fixture-only',path.read_text())
        self.assertNotIn('connector_root',b.status())
        with patch.dict('os.environ',{'WORKFLOW_CONNECTOR_ROOT':str(root)}):b.prepare('http://127.0.0.1:9999')
        self.assertEqual(b.config(),c)

if __name__=='__main__':unittest.main()

class BridgeHTTPTests(unittest.TestCase):
    def test_lan_host_random_port_origin_and_enqueue(self):
        import threading
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from workflow.server import make_server
        from workflow.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'workspace');store.initialize('Test')
            before=store.read()
            config=Path(tmp)/'bridge.json';write_json(config,{'enabled':True,'session_id':'session','thread_url':None})
            with patch.dict('os.environ',{'WORKFLOW_BRIDGE_CONFIG':str(config)}):server=make_server(store,0,'0.0.0.0')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                self.assertGreater(server.server_port,0)
                with urlopen(base+'/api/session-bridge') as r:self.assertTrue(json.load(r)['enabled'])
                body=json.dumps({'request_id':'browser-0001','page':'/#home','title':'home'}).encode()
                for origin in [None,'http://evil.invalid']:
                    headers={'Content-Type':'application/json'}
                    if origin:headers['Origin']=origin
                    with self.assertRaises(HTTPError) as err:urlopen(Request(base+'/api/session-bridge',data=body,headers=headers))
                    self.assertEqual(err.exception.code,403)
                with self.assertRaises(HTTPError):urlopen(Request(base+'/api/session-bridge',headers={'Host':'evil.invalid'}))
                with urlopen(Request(base+'/api/session-bridge',data=body,headers={'Content-Type':'application/json','Origin':base})) as r:
                    self.assertEqual(json.load(r)['status'],'queued')
                with urlopen(Request(base+'/api/session-bridge/control',data=json.dumps({'action':'discord_toggle','on':False}).encode(),headers={'Content-Type':'application/json','Origin':base})) as r:
                    self.assertFalse(json.load(r)['discord_on'])
                with self.assertRaises(HTTPError) as err:
                    urlopen(Request(base+'/api/session-bridge/control',data=b'{"action":"discord_toggle","on":false}',headers={'Content-Type':'application/json','Origin':'http://evil.invalid'}))
                self.assertEqual(err.exception.code,403)
                self.assertEqual(store.read(),before)
            finally:server.shutdown();server.server_close();thread.join()
