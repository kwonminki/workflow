(() => {
  const opener=document.querySelector('#main-session-send');
  if(!opener)return;
  opener.disabled=false;
  // Remove the old inline status/link if this asset is refreshed in an existing shell.
  document.querySelector('#main-session-status')?.remove();
  const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const button=(text,id,fn)=>{const b=make('button',text);b.type='button';if(id)b.id=id;if(fn)b.addEventListener('click',fn);return b;};
  const field=(label,input)=>{const e=make('label',label,'bridge-field');e.append(input);return e;};
  const storage={get(k){try{return sessionStorage.getItem(k);}catch{return null;}},set(k,v){try{sessionStorage.setItem(k,v);}catch{}},remove(k){try{sessionStorage.removeItem(k);}catch{}}};
  const key='workflow-main-session-request';
  let state={enabled:false},requestId=storage.get(key),busy=false,context=null;
  const labels={queued:'전달 중',sending:'전달 중',accepted:'전달됨',failed:'연결 확인 필요',unknown:'연결 확인 필요'};
  const uuid=()=> 'web-'+(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random().toString(16).slice(2));
  const request=async(path,payload)=>{const r=await fetch(path,payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Workflow-Edit':'1'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error||'잠시 후 다시 시도해 주세요.');return d;};
  const control=payload=>request('/api/session-bridge/control',payload);
  const helpText=kind=>`이 웹 작업공간(${location.origin})의 ${kind==='discord'?'Discord 알림':'메인 Codex/Orca 세션 전달'} 연결을 설정해 주세요.\n${kind==='discord'?'서버의 ai-agent-discord-connector 설치 상태를 확인하고 알림 전용 스레드와 연결해 주세요.':'제가 대화 중인 정확한 메인 세션을 확인해 연결해 주세요.'}\n서버의 비공개 bridge 설정과 알림 worker도 확인하고 연결 검사를 해 주세요.\n안내: https://github.com/kwonminki/workflow/blob/main/docs/SESSION_BRIDGE.md\n봇 설치: https://github.com/kwonminki/ai-agent-discord-connector`;
  async function copy(text,result){
    try {if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);else {const t=make('textarea');t.value=text;t.className='bridge-copy-buffer';document.body.append(t);t.select();const ok=document.execCommand('copy');t.remove();if(!ok)throw Error();}result.textContent='요청문을 복사했습니다. 에이전트 대화에 붙여 넣어 주세요.';}
    catch {result.textContent='아래 요청문을 선택해 복사해 주세요.';const t=make('textarea');t.value=text;t.readOnly=true;t.rows=6;result.append(t);t.focus();t.select();}
  }
  const wrap=make('div',undefined,'bridge-dropdown');
  const discordButton=button('Discord 알림 ▾','discord-alerts-toggle');discordButton.setAttribute('aria-expanded','false');discordButton.setAttribute('aria-controls','discord-alerts-panel');
  const dropdown=make('section',undefined,'bridge-popover');dropdown.id='discord-alerts-panel';dropdown.hidden=true;dropdown.setAttribute('aria-label','Discord 알림 설정');
  const discordStatus=make('strong','연결 확인 중');discordStatus.id='discord-connection-status';
  const switchButton=button('알림 OFF','discord-alerts-switch');switchButton.setAttribute('role','switch');switchButton.setAttribute('aria-checked','false');
  const discordTop=make('div',undefined,'bridge-row');discordTop.append(discordStatus,switchButton);
  const threadLink=make('a','알림 스레드 열기 ↗');threadLink.target='_blank';threadLink.rel='noopener noreferrer';threadLink.hidden=true;
  const discordActions=make('div',undefined,'bridge-row');
  const discordDirect=button('직접 연결','discord-direct-connect',()=>{discordForm.hidden=!discordForm.hidden;threadInput.value=state.thread_url||'';if(!discordForm.hidden)threadInput.focus();});
  const discordAsk=button('에이전트에게 부탁하기','discord-ask-agent',()=>{
    if(state.session_configured){openDialog();const help=helpText('discord');if(!extra.value.includes(help))extra.value=[extra.value,help].filter(Boolean).join('\n\n');discordMessage.textContent='요청문을 준비했습니다. 창에서 전송을 눌러 주세요.';}
    else copy(helpText('discord'),discordMessage);
  });
  discordActions.append(discordDirect,discordAsk);
  const discordMessage=make('p',undefined,'bridge-result');discordMessage.setAttribute('role','status');
  const discordForm=make('form',undefined,'bridge-connect-form');discordForm.hidden=true;
  const threadInput=make('input');threadInput.type='url';threadInput.placeholder='https://discord.com/channels/서버ID/스레드ID';threadInput.required=true;threadInput.id='discord-thread-url';
  const discordSave=make('button','이 스레드 연결');discordSave.type='submit';discordSave.id='discord-connect-save';
  discordForm.append(field('봇이 참여한 Discord 스레드 주소',threadInput),make('p','봇은 서버에 설치된 연결 정보를 사용합니다. 토큰을 입력할 필요가 없습니다.','bridge-hint'),discordSave);
  discordForm.addEventListener('submit',async e=>{e.preventDefault();discordSave.disabled=true;discordMessage.textContent='연결 확인 중…';try{state=await control({action:'connect_discord',thread_url:threadInput.value.trim()});render();discordForm.hidden=true;discordMessage.textContent='연결했습니다. 알림 ON을 선택하면 새 항목부터 알려드립니다.';}catch(e){discordMessage.textContent=e.message;}finally{discordSave.disabled=false;}});
  switchButton.addEventListener('click',async()=>{switchButton.disabled=true;try{state=await control({action:'discord_toggle',on:!state.discord_on});render();discordMessage.textContent=state.discord_on?'알림을 켰습니다.':'알림을 껐습니다.';}catch(e){discordMessage.textContent=e.message;}finally{switchButton.disabled=!state.discord_configured;}});
  dropdown.append(discordTop,threadLink,make('p','알림을 꺼도 메인 세션에 메시지는 보낼 수 있습니다. 끈 동안의 항목은 나중에 몰아서 알리지 않습니다.','bridge-hint'),discordActions,discordForm,discordMessage);
  wrap.append(discordButton,dropdown);opener.after(wrap);
  discordButton.addEventListener('click',()=>{dropdown.hidden=!dropdown.hidden;discordButton.setAttribute('aria-expanded',String(!dropdown.hidden));if(!dropdown.hidden)refresh();});
  document.addEventListener('click',e=>{if(!wrap.contains(e.target)){dropdown.hidden=true;discordButton.setAttribute('aria-expanded','false');}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dropdown.hidden){dropdown.hidden=true;discordButton.setAttribute('aria-expanded','false');discordButton.focus();}});

  const dialog=make('dialog',undefined,'bridge-dialog');dialog.id='main-session-dialog';dialog.setAttribute('aria-labelledby','bridge-dialog-title');
  const top=make('div',undefined,'bridge-dialog-top');const heading=make('h2','메인 세션에 완료 전달하기');heading.id='bridge-dialog-title';
  const badge=make('span','연결 확인 중','bridge-badge');badge.id='main-session-connection';
  const close=button('닫기','bridge-dialog-close',()=>dialog.close());top.append(heading,badge,close);
  const connected=make('p',undefined,'bridge-hint');connected.id='main-session-connected-id';
  const row=make('div',undefined,'bridge-row');row.append(button('직접 연결','main-session-direct',()=>{sessionForm.hidden=!sessionForm.hidden;if(!sessionForm.hidden)loadSessions();}),button('에이전트 요청문 복사','main-session-copy-request',()=>copy(helpText('session'),connectMessage)));
  const connectMessage=make('p',undefined,'bridge-result');connectMessage.setAttribute('role','status');
  const sessionForm=make('form',undefined,'bridge-connect-form');sessionForm.hidden=true;
  const select=make('select');select.id='main-session-options';select.append(new Option('실행 중인 세션 불러오기',''));
  const sessionId=make('input');sessionId.id='main-session-id';sessionId.placeholder='메인 Codex 세션 UUID';sessionId.required=true;sessionId.maxLength=36;
  select.addEventListener('change',()=>{if(select.value)sessionId.value=select.value;});
  const save=make('button','선택한 세션 연결');save.type='submit';save.id='main-session-connect-save';
  sessionForm.append(field('실행 중인 Codex 세션',select),button('목록 새로고침','main-session-reload',loadSessions),field('세션 ID 직접 입력',sessionId),save);
  async function loadSessions(){sessionId.value=state.session_id||sessionId.value;select.disabled=true;connectMessage.textContent='세션 목록 확인 중…';try{const d=await control({action:'sessions'});select.replaceChildren(new Option('연결할 메인 세션을 선택하세요',''));for(const s of d.sessions)select.append(new Option(s.title+' · '+s.session_id,s.session_id));connectMessage.textContent=d.sessions.length?'메인 대화의 세션을 선택해 주세요.':'실행 중인 세션을 찾지 못했습니다. 세션 ID를 직접 입력하거나 에이전트에게 부탁해 주세요.';}catch(e){connectMessage.textContent=e.message;}finally{select.disabled=false;}}
  sessionForm.addEventListener('submit',async e=>{e.preventDefault();save.disabled=true;connectMessage.textContent='연결 확인 중…';try{state=await control({action:'connect_session',session_id:sessionId.value.trim()});requestId=null;storage.remove(key);storage.remove(key+'-pending');result.textContent='';render();sessionForm.hidden=true;connectMessage.textContent='메인 세션을 연결했습니다.';}catch(e){connectMessage.textContent=e.message;}finally{save.disabled=false;}});
  const page=make('p',undefined,'bridge-page');page.id='main-session-page';
  const extra=make('textarea');extra.id='main-session-message';extra.rows=5;extra.maxLength=4000;extra.placeholder='함께 전달할 내용이 있으면 작성해 주세요.';
  const send=button('전송','main-session-submit',sendMessage);
  const result=make('p',undefined,'bridge-result');result.id='main-session-status';result.setAttribute('role','status');
  const bottom=make('div',undefined,'bridge-row');bottom.append(result,send);
  dialog.append(top,connected,row,sessionForm,connectMessage,page,field('추가 메시지 (선택)',extra),make('p','페이지에서 작성한 내용은 먼저 저장해 주세요. 전송을 누르면 현재 페이지와 추가 메시지를 전달합니다.','bridge-hint'),bottom);document.body.append(dialog);
  function openDialog(){context={page:location.pathname+location.search+location.hash,title:(document.querySelector('#page-title')?.textContent||document.querySelector('#heading')?.textContent||document.title).slice(0,300)};page.textContent='전달할 페이지: '+context.title;page.title=location.origin+context.page;if(!dialog.open)dialog.showModal();render();refresh();if(state.session_configured)control({action:'check_session'}).then(d=>{state=d;render();}).catch(()=>{badge.textContent='연결 확인 필요';});}
  opener.addEventListener('click',openDialog);
  function render(){
    const configured=state.session_configured??!!state.session_id;
    state.session_configured=configured;
    discordStatus.textContent=state.discord_configured?'연결 설정됨':'연결 안 됨';
    switchButton.textContent=state.discord_on?'알림 ON':'알림 OFF';switchButton.setAttribute('aria-checked',String(!!state.discord_on));switchButton.disabled=!state.discord_configured;
    threadLink.hidden=!state.thread_url;if(state.thread_url&&/^https:\/\/discord\.com\/channels\/\d+\/\d+$/.test(state.thread_url))threadLink.href=state.thread_url;
    const checked=state.session_check?.session_id===state.session_id?state.session_check:null;
    badge.textContent=!configured?'연결 안 됨':checked?.status==='ready'?'연결됨':checked?'연결 확인 필요':'연결 설정됨';
    connected.textContent=configured?'연결된 세션: '+state.session_id:'아직 메인 세션을 연결하지 않았습니다.';
    const r=state.request;
    if(r && requestId===r.id)result.textContent=labels[r.status]||'연결 확인 필요';
    send.disabled=busy||!configured||!!(r&&r.id===requestId&&['queued','sending'].includes(r.status));
  }
  async function refresh(){try{state=await request('/api/session-bridge'+(requestId?'?request_id='+encodeURIComponent(requestId):''));render();}catch{discordStatus.textContent='연결 확인 필요';badge.textContent='연결 확인 필요';}}
  async function sendMessage(){
    if(busy)return;if(extra.value.length>4000){result.textContent='추가 메시지는 4000자까지 작성할 수 있습니다.';return;}busy=true;send.disabled=true;result.textContent='전달 중';
    const message=extra.value;let payload;
    try{const pending=JSON.parse(storage.get(key+'-pending')||'null');if(pending&&pending.page===context.page&&pending.title===context.title&&pending.message===message)payload=pending;}catch{}
    payload ||= {request_id:uuid(),...context,message};storage.set(key+'-pending',JSON.stringify(payload));requestId=payload.request_id;storage.set(key,requestId);
    try{const d=await request('/api/session-bridge',payload);requestId=d.id;storage.set(key,requestId);storage.remove(key+'-pending');if(extra.value===message)extra.value='';result.textContent=labels[d.status]||'전달 중';}
    catch {result.textContent='연결 확인 필요';}
    finally{busy=false;await refresh();}
  }
  refresh();setInterval(refresh,5000);
})();
