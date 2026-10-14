// Optional isolated Chromium smoke test. Requires Node 22+ and CHROME_BINARY.
// Never connects to a production workspace or assumes a fixed application port.
import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const chrome=process.env.CHROME_BINARY;
if(!chrome)throw Error('Set CHROME_BINARY to a Chromium/chrome-headless-shell executable');
const work=await fs.mkdtemp(path.join(os.tmpdir(),'workflow-browser-'));
const data=path.join(work,'data'),profile=path.join(work,'chrome');
const out=path.resolve(process.env.WORKFLOW_BROWSER_OUTPUT||path.join(work,'evidence'));
await fs.mkdir(out,{recursive:true});
const result={checks:[],errors:[],isolated_workspace:true};
const check=(name,condition,detail)=>{if(!condition)throw Error(name+': '+JSON.stringify(detail));result.checks.push(name);};
const py=process.env.PYTHON||'python3';
function cli(args,input){const r=spawnSync(py,['-m','workflow','--data',data,...args],{cwd:root,encoding:'utf8',input:input===undefined?undefined:JSON.stringify(input)});if(r.status!==0)throw Error('CLI failed: '+r.stderr);return JSON.parse(r.stdout);}
let server,browser,socket;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
try{
 cli(['init','--demo','--title','Isolated browser test']);
 const body=['첫 문단 의견입니다.',...Array.from({length:28},(_,i)=>`중간 문단 ${i+1}: 다른 위치로 잘못 이동하지 않는지 확인합니다.`),'마지막 😀 정확한 인용 대상 문장입니다.'].join('\n\n');
 cli(['apply','document','--agent','worker','--file','-'],{id:'browser-document',title:'브라우저 검증 문서',body});
 server=spawn(py,['-c',"from workflow.store import Store;from workflow.server import make_server;import sys;s=make_server(Store(sys.argv[1]),0);print(s.server_port,flush=True);s.serve_forever()",data],{cwd:root,stdio:['ignore','pipe','pipe']});
 let serverText='',serverError='';server.stdout.on('data',b=>serverText+=b);server.stderr.on('data',b=>serverError+=b);
 for(let i=0;i<100&&!serverText.includes('\n');i++){if(server.exitCode!==null)throw Error('Server startup: '+serverError);await pause(50);}
 const port=Number(serverText.trim());if(!port)throw Error('No server port: '+serverError);const base='http://127.0.0.1:'+port;
 browser=spawn(chrome,['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe']});
 let chromeError='';browser.stderr.on('data',b=>chromeError+=b);
 let debugPort;for(let i=0;i<100;i++){try{debugPort=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{}if(browser.exitCode!==null)throw Error('Chrome startup: '+chromeError);await pause(100);}
 if(!debugPort)throw Error('Chrome startup timeout: '+chromeError);
 const pages=await(await fetch('http://127.0.0.1:'+debugPort+'/json/list')).json();socket=new WebSocket(pages[0].webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 let sequence=0;const requests=new Map();socket.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=requests.get(m.id);if(p){requests.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}}if(m.method==='Runtime.exceptionThrown')result.errors.push(m.params.exceptionDetails);};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence,timeout=setTimeout(()=>{requests.delete(id);reject(Error('CDP timeout '+method));},10000);requests.set(id,{resolve:value=>{clearTimeout(timeout);resolve(value);},reject:e=>{clearTimeout(timeout);reject(e);}});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
 const until=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await pause(100);}throw Error('Timeout '+expression+' '+JSON.stringify(await evaluate("({hash:location.hash,error:document.querySelector('#error')?.textContent,panel:document.querySelector('#panel-body')?.textContent})")));};
 const getState=async()=>await(await fetch(base+'/api/state')).json();
 const close=async()=>evaluate("document.querySelector('#panel').close()");
 const saveMemo=async text=>{await evaluate(`document.querySelector('#panel-body textarea').value=${JSON.stringify(text)};document.querySelector('#panel-body form').requestSubmit()`);await until(`document.querySelector('#panel-body').textContent.includes(${JSON.stringify(text)}) && document.querySelector('#panel-body h3').textContent==='코멘트 · 답변'`);await close();};
 await call('Page.enable');await call('Runtime.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:base+'/#graph'});await until("document.querySelectorAll('.node').length===4");
 check('graph automatically includes all plan nodes',await evaluate("document.querySelectorAll('.edge').length===4"));
 await evaluate("document.querySelector('.node').dispatchEvent(new MouseEvent('mouseenter'))");check('hover highlights connected edges',await evaluate("document.querySelectorAll('.edge.hot').length>0"));
 await evaluate("[...document.querySelectorAll('#view button')].find(b=>b.textContent==='+').click()");check('graph zoom changes scale',await evaluate("document.querySelector('#view .row').textContent.includes('115%')"));
 await fs.writeFile(path.join(out,'graph-desktop.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await evaluate("location.hash='document/browser-document'");await until("document.querySelectorAll('.document p').length===30");
 await evaluate("document.querySelector('.document p').click()");await until("document.querySelector('#panel-body h3').textContent==='메모 남기기'");await saveMemo('첫 문단 코멘트');
 const first=(await getState()).threads.at(-1);check('paragraph comment stores exact paragraph',first.anchor.quote==='첫 문단 의견입니다.',first.anchor);
 await evaluate("(()=>{const p=[...document.querySelectorAll('.document p')].at(-1);p.scrollIntoView({block:'center'});const r=document.createRange();r.setStart(p.firstChild,4);r.setEnd(p.firstChild,p.firstChild.textContent.length);const s=window.getSelection();s.removeAllRanges();s.addRange(r);p.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));})()");
 await until("!document.querySelector('#selection-button').hidden");await evaluate("document.querySelector('#selection-button').click()");await saveMemo('두 번째 인용 코멘트');
 await evaluate('window.getSelection().removeAllRanges()');const second=(await getState()).threads.at(-1);
 check('Unicode drag anchor preserves quote',second.anchor.quote==='😀 정확한 인용 대상 문장입니다.',second.anchor);
 check('Unicode anchor uses codepoints',Array.from(body).slice(second.anchor.start,second.anchor.end).join('')===second.anchor.quote,second.anchor);
 check('two exact highlighted threads',await evaluate(`document.querySelectorAll('mark').length===2 && [...document.querySelectorAll('mark')].some(m=>m.dataset.threads===${JSON.stringify(second.id)})`));
 const reply=text=>cli(['apply','reply','--agent','worker','--file','-'],{thread_id:second.id,reply_to:second.messages[0].id,text,outcome:'applied',evidence:['#document/browser-document']}).record;
 const reply1=reply('첫 번째 에이전트 답변');await evaluate("document.querySelector('#reload').click();location.hash='notifications'");await until("document.querySelector('#unread').textContent==='1'");
 await evaluate("[...document.querySelectorAll('#view button')].find(b=>b.textContent==='답변 읽기').click()");await until("document.querySelector('#unread').textContent==='0'");check('opening one reply marks it read',(await getState()).threads.at(-1).messages.find(m=>m.id===reply1.id).read_at!==null);
 await close();await evaluate("[...document.querySelectorAll('#view button')].find(b=>b.textContent==='이전 알림으로 가기').click()");check('previous notification opens recently read thread',await evaluate("document.querySelector('#panel-body').textContent.includes('첫 번째 에이전트 답변')"));await close();
 const reply2=reply('새로운 두 번째 에이전트 답변');await evaluate("document.querySelector('#reload').click()");await until("document.querySelector('#unread').textContent==='1'");check('new reply is independently unread',(await getState()).threads.at(-1).messages.find(m=>m.id===reply2.id).read_at===null);
 await evaluate("[...document.querySelectorAll('#view button')].find(b=>b.textContent==='원문 위치').click()");await until("location.hash==='#document/browser-document' && document.querySelectorAll('mark').length===2");await pause(250);
 const spot=await evaluate(`(()=>{const m=[...document.querySelectorAll('mark')].find(m=>m.dataset.threads.split(',').includes(${JSON.stringify(second.id)}));return {top:m.getBoundingClientRect().top,bottom:m.getBoundingClientRect().bottom,viewport:innerHeight,text:m.textContent,scrollY};})()`);
 check('notification navigates to exact second quote',spot.top>=0&&spot.top<spot.viewport&&spot.scrollY>300,spot);
 check('only viewed notifications become read',(await getState()).threads.at(-1).messages.filter(m=>m.kind==='agent').every(m=>m.read_at));
 await evaluate(`document.querySelector('mark[data-threads="${second.id}"]').click()`);await until("document.querySelector('#panel[open]')!==null");check('highlight opens its original thread',await evaluate("document.querySelector('#panel-body').textContent.includes('두 번째 인용 코멘트')"));
 await evaluate("document.querySelector('#panel-body textarea').value='추가 사용자 의견';document.querySelector('#panel-body form').requestSubmit()");await until("document.querySelector('#panel-body').textContent.includes('추가 사용자 의견')");check('new user followup is pending',cli(['inbox']).pending_threads===2);await close();
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate("location.hash='graph'");await until("document.querySelector('.graph-wrap')!==null");await evaluate('window.scrollTo(0,0)');check('mobile graph contained within viewport',await evaluate('document.documentElement.scrollWidth-innerWidth<=1'));
 await fs.writeFile(path.join(out,'graph-mobile.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await evaluate("location.hash='document/browser-document'");await until("document.querySelector('.document')!==null");await evaluate('window.scrollTo(0,0)');check('mobile document contained within viewport',await evaluate('document.documentElement.scrollWidth-innerWidth<=1'));
 await fs.writeFile(path.join(out,'document-mobile.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 check('browser runtime exceptions absent',result.errors.length===0,result.errors);
 await fs.writeFile(path.join(out,'browser.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({output:out,...result},null,2));
}catch(error){result.failure=String(error);await fs.writeFile(path.join(out,'browser-failure.json'),JSON.stringify(result,null,2)+'\n');throw error;}
finally{socket?.close();for(const child of [browser,server]){if(child&&child.exitCode===null){child.kill('SIGTERM');await Promise.race([new Promise(r=>child.once('exit',r)),pause(1500)]);}}if(!out.startsWith(work+path.sep))await fs.rm(work,{recursive:true,force:true,maxRetries:5,retryDelay:100});}
