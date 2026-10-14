// Isolated UI test: synthetic Connector/session and a real loopback HTTP server.
import {spawn} from 'node:child_process';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'bridge-controls-'));
const out=process.env.WORKFLOW_BROWSER_OUTPUT||path.join(tmp,'evidence');await fs.mkdir(out,{recursive:true});
const chrome=process.env.CHROME_BINARY;if(!chrome)throw Error('CHROME_BINARY required');
const server=spawn('python3',['tests/bridge_fixture.py',path.join(tmp,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});let errorsText='';server.stderr.on('data',b=>errorsText+=b);
const pause=ms=>new Promise(r=>setTimeout(r,ms));let browser,ws;const result={checks:[],runtime_errors:[],isolated:true};
function check(name,condition){if(!condition)throw Error(name);result.checks.push(name);}
try{
 const base=await new Promise((resolve,reject)=>{server.stdout.once('data',b=>resolve(String(b).trim()));server.on('exit',code=>reject(Error('fixture '+code+' '+errorsText)));});
 const profile=path.join(tmp,'chrome');browser=spawn(chrome,['--no-sandbox','--headless','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
 let port;for(let i=0;i<100;i++){try{port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await pause(100);}}
 const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();ws=new WebSocket(tabs[0].webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p[1](Error(JSON.stringify(m.error))):p[0](m.result);}else if(m.method==='Runtime.exceptionThrown')result.runtime_errors.push(m.params.exceptionDetails.text);};
 const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,[resolve,reject]);ws.send(JSON.stringify({id,method,params}));});
 const ev=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
 const until=async expression=>{for(let i=0;i<100;i++){if(await ev(expression))return;await pause(100);}throw Error('Timeout: '+expression);};
 const effects=async()=>JSON.parse(await fs.readFile(path.join(tmp,'data/effects.json'),'utf8'));
 await call('Page.enable');await call('Runtime.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:base});await until("document.querySelector('#main-session-send')&&!document.querySelector('#main-session-send').disabled");
 await ev("document.querySelector('#main-session-send').click()");await until("document.querySelector('#main-session-dialog').open");
 check('opener does not submit',!(await effects()).sends.length);
 check('unconfigured dialog shows status and disables send',await ev("document.querySelector('#main-session-connection').textContent==='연결 안 됨'&&document.querySelector('#main-session-submit').disabled"));
 await ev("document.querySelector('#main-session-copy-request').click()");await until("document.querySelector('#main-session-dialog .bridge-result').textContent.includes('요청문을 복사했습니다')||document.querySelector('#main-session-dialog .bridge-result').textContent.includes('아래 요청문을 선택')");check('agent setup request can be copied or manually selected',true);
 await ev("document.querySelector('#main-session-direct').click()");await until("document.querySelector('#main-session-options').options.length===2");
 await ev("document.querySelector('#main-session-options').selectedIndex=1;document.querySelector('#main-session-options').dispatchEvent(new Event('change'));document.querySelector('#main-session-connect-save').click()");await until("document.querySelector('#main-session-connection').textContent==='연결됨'");
 check('direct session connection succeeds without a send',!(await effects()).sends.length);
 await ev("document.querySelector('#main-session-message').value='추가 메시지\n두 번째 줄';document.querySelector('#main-session-submit').click()".replace("메시지\n두","메시지\\n두"));
 await until("document.querySelector('#main-session-status').textContent==='전달됨'");
 check('explicit send delivers exact extra text',(await effects()).sends.length===1&&(await effects()).sends[0].message.includes('추가 메시지\n두 번째 줄'));
 await fs.writeFile(path.join(out,'session-dialog.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await ev("document.querySelector('#bridge-dialog-close').click();document.querySelector('#discord-alerts-toggle').click()");
 check('Discord dropdown displays disconnected state',await ev("!document.querySelector('#discord-alerts-panel').hidden&&document.querySelector('#discord-connection-status').textContent==='연결 안 됨'"));
 await ev("document.querySelector('#discord-direct-connect').click();document.querySelector('#discord-thread-url').value='https://discord.com/channels/123456789012345678/223456789012345678';document.querySelector('#discord-connect-save').click()");await until("document.querySelector('#discord-connection-status').textContent==='연결 설정됨'");
 check('new Discord destination starts OFF',await ev("document.querySelector('#discord-alerts-switch').getAttribute('aria-checked')==='false'"));
 await ev("document.querySelector('#discord-alerts-switch').click()");await until("document.querySelector('#discord-alerts-switch').getAttribute('aria-checked')==='true'");
 await call('Page.reload');await until("document.querySelector('#discord-alerts-switch')?.getAttribute('aria-checked')==='true'");check('Discord ON survives reload',true);
 await ev("document.querySelector('#discord-alerts-toggle').click()");await fs.writeFile(path.join(out,'discord-dropdown.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await ev("document.querySelector('#discord-alerts-switch').click()");await until("document.querySelector('#discord-alerts-switch').getAttribute('aria-checked')==='false'");
 await ev("document.querySelector('#discord-ask-agent').click()");await until("document.querySelector('#main-session-dialog').open");
 check('agent request is prepared for explicit send',await ev("document.querySelector('#main-session-message').value.includes('Discord 알림')")&&(await effects()).sends.length===1);
 check('Discord OFF leaves main session send available',await ev("!document.querySelector('#main-session-submit').disabled"));
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(250);
 check('dialog fits mobile viewport',await ev("document.querySelector('#main-session-dialog').getBoundingClientRect().right<=390&&document.documentElement.scrollWidth<=390"));
 await fs.writeFile(path.join(out,'mobile-dialog.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 check('no verbose diagnostic banner',await ev("!document.body.textContent.includes('전달 여부 불명')&&!document.body.textContent.includes('중복 전송 전')"));
 check('no browser exceptions',!result.runtime_errors.length);
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({output:out,...result},null,2));
}finally{ws?.close();browser?.kill();server.kill();}
