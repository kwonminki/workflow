"""Isolated browser fixture. No external calls; never imports installed Connector."""
import json
import os
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow.bridge import Bridge,write_json
from workflow.server import make_server
from workflow.store import Store

root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
cfg=root/'bridge.json';connector=root/'connector.json'
write_json(connector,{'discord':{'guildId':'123456789012345678'}})
write_json(cfg,{'enabled':True,'session_id':None,'discord_enabled':False,'connector_config':str(connector),
               'source_kind':'workflow','base_url':'http://127.0.0.1','source_url':'unused'})
os.environ['WORKFLOW_BRIDGE_CONFIG']=str(cfg)
effects={'sends':[],'discord_posts':[]};effects_path=root/'effects.json';write_json(effects_path,effects)
sid='00000000-0000-0000-0000-000000000001'
def adapter(self,c,action,message=''):
    if action=='list':return {'status':'ready','sessions':[{'session_id':sid,'title':'Example main session'}]}
    if action=='check':return {'status':'ready' if c.get('session_id')==sid else 'failed'}
    effects['sends'].append({'session_id':c.get('session_id'),'message':message});write_json(effects_path,effects)
    return {'status':'accepted','accepted':True,'turnStarted':False}
def discord(self,c,method,route,body=None):
    if method=='GET' and '/messages' in route:return []
    if method=='GET':return {'id':'223456789012345678','guild_id':'123456789012345678','type':11}
    if method=='POST':effects['discord_posts'].append(body);write_json(effects_path,effects)
    return {'id':'333456789012345678'}
Bridge.adapter=adapter;Bridge.discord=discord
store=Store(root/'workspace');store.initialize('Bridge UI fixture')
server=make_server(store,0);base='http://127.0.0.1:'+str(server.server_port)
c=json.loads(cfg.read_text());c['base_url']=base;write_json(cfg,c)
b=Bridge(cfg)
def worker():
    while True:
        b.tick(store.read());time.sleep(.15)
threading.Thread(target=worker,daemon=True).start()
print(base,flush=True)
server.serve_forever()
