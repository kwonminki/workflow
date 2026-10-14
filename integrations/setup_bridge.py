#!/usr/bin/env python3
"""Explicitly connect an installed connector; never install/copy bot credentials."""
import argparse
import json
import shutil
from pathlib import Path
import sys
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow.bridge import Bridge, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    p.add_argument('--connector',required=True)
    p.add_argument('--connector-config')
    p.add_argument('--session',required=True)
    p.add_argument('--base-url',required=True)
    p.add_argument('--source-kind',choices=['workflow','hub'],default='workflow')
    p.add_argument('--thread-name',default='Workflow · 지금 확인')
    p.add_argument('--thread-id',help='Reuse an existing dedicated notification thread')
    p.add_argument('--notify-user',help='Discord user ID to mention; optional')
    args=p.parse_args()
    dest=Path(args.config).expanduser().resolve()
    if dest.exists(): raise SystemExit('Config already exists. Edit the existing local config deliberately; no duplicate thread created.')
    root=Path(args.connector).expanduser().resolve()
    cp=Path(args.connector_config).expanduser().resolve() if args.connector_config else root/'.connect/config.json'
    installed=json.loads(cp.read_text())
    base=args.base_url.rstrip('/')
    u=urlsplit(base)
    if u.scheme not in ('http','https') or not u.netloc or u.path or u.query or u.fragment or u.username:
        raise SystemExit('--base-url must be an HTTP(S) origin including the actual port')
    c={'enabled':True,'connector_root':str(root),'connector_config':str(cp),
       'orca_command':installed.get('direct',{}).get('orca',{}).get('command','orca'),
       'node_command':str(Path(shutil.which('node') or '/missing-node').resolve()),
       'session_id':args.session,'base_url':base,'source_kind':args.source_kind,
       'source_url':base+('/api/state' if args.source_kind=='workflow' else '/api/attention')}
    if args.notify_user:
        if not args.notify_user.isdigit(): raise SystemExit('Invalid Discord user ID')
        c['notify_user_id']=args.notify_user
    b=Bridge(dest)
    result=b.adapter(c,'check')
    if result.get('status')!='ready': raise SystemExit(json.dumps(result,ensure_ascii=False))
    parent=installed['direct']['channelId'];guild=installed['discord']['guildId']
    parent_info=b.discord(c,'GET','/channels/'+parent)
    if parent_info.get('guild_id')!=guild or parent_info.get('type')!=0:
        raise SystemExit('Configured Codex parent must be a text channel in the configured guild')
    if args.thread_id:
        thread=b.discord(c,'GET','/channels/'+args.thread_id)
        if thread.get('guild_id')!=guild or thread.get('type') not in (11,12): raise SystemExit('Invalid existing thread')
    else:
        thread=b.discord(c,'POST',f'/channels/{parent}/threads',{'name':args.thread_name[:100],'type':11,'auto_archive_duration':1440})
    c.update(thread_id=thread['id'],thread_url=f'https://discord.com/channels/{guild}/{thread["id"]}')
    # Persist immediately so a welcome-message failure does not create a second thread.
    write_json(dest,c)
    if args.notify_user:
        b.discord(c,'PUT',f'/channels/{thread["id"]}/thread-members/{args.notify_user}')
    b.discord(c,'POST',f'/channels/{thread["id"]}/messages',{
        'content':f'웹 알림 연결: {base}/\n새 확인 항목/새 버전을 이 스레드에 알립니다. 초기 기존 항목은 기준으로만 저장합니다.\n웹의 「메인 세션에 완료 전달하기」는 설정한 Codex/Orca 세션으로 직접 전달합니다.\n이 스레드는 알림 전용입니다. 대화는 기존 메인 세션에서 이어가세요.',
        'allowed_mentions':{'parse':[]}})
    print(json.dumps({'config':str(dest),'session':args.session,'thread_url':c['thread_url'],'check':result},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
