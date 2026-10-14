(() => {
  const button = document.querySelector('#main-session-send');
  if (!button) return;
  const output = document.createElement('span');
  output.id = 'main-session-status'; output.setAttribute('role','status');
  button.after(output);
  const discord=document.createElement('a');discord.textContent='Discord 알림';discord.hidden=true;discord.target='_blank';discord.rel='noopener noreferrer';output.after(discord);
  const labels = {queued:'전달 중',sending:'전달 중',accepted:'전달됨',failed:'연결 확인 필요',unknown:'연결 확인 필요'};
  let sending = false, requestId = null;
  const key = 'workflow-main-session-request';
  try { requestId = sessionStorage.getItem(key); } catch {}
  function display(data) {
    if (!data.enabled) {button.disabled=true;button.title='서버의 세션 연결 설정이 필요합니다.';return;}
    button.title='연결 세션: '+data.session_id;
    if (data.thread_url && /^https:\/\/discord\.com\/channels\/\d+\/\d+$/.test(data.thread_url)) {discord.href=data.thread_url;discord.hidden=false;}
    discord.title=data.source_error|| (data.notice_errors?'미전달 알림 '+data.notice_errors+'건 · 서버 전달 기록 확인':'새 확인 항목의 Discord 알림 스레드');
    const r=data.request;
    const active=r && (r.status==='queued'||r.status==='sending');
    button.disabled=active||sending;
    if (r) output.textContent=(labels[r.status]||'연결 확인 필요');
    if (active && (!data.worker_at || Date.now()-Date.parse(data.worker_at)>120000)) output.textContent='연결 확인 필요';
  }
  async function refresh() {
    try {const r=await fetch('/api/session-bridge'+(requestId?'?request_id='+encodeURIComponent(requestId):''));if(!r.ok)throw Error('연결 상태 조회 실패');display(await r.json());}
    catch {if(!sending) output.textContent='연결 확인 필요';}
  }
  button.addEventListener('click',async()=>{
    if(sending)return;
    sending=true;button.disabled=true;output.textContent='전달 요청 저장 중…';
    // Retain the exact payload for retry after a lost HTTP response.
    let payload;
    try {payload=JSON.parse(sessionStorage.getItem(key+'-pending')||'null');} catch {}
    payload ||= {request_id:'web-'+(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random().toString(16).slice(2)),page:location.pathname+location.search+location.hash,title:(document.querySelector('#page-title')?.textContent||document.querySelector('#heading')?.textContent||document.title).slice(0,300)};
    try {
      sessionStorage.setItem(key+'-pending',JSON.stringify(payload));
      const r=await fetch('/api/session-bridge',{method:'POST',headers:{'Content-Type':'application/json','X-Workflow-Edit':'1'},body:JSON.stringify(payload)});
      const data=await r.json();if(!r.ok)throw Error(data.error||'요청 저장 실패');
      requestId=data.id;sessionStorage.setItem(key,requestId);sessionStorage.removeItem(key+'-pending');
      output.textContent=labels[data.status]||data.status;
    } catch(e) {output.textContent='연결 확인 필요';}
    finally {sending=false;button.disabled=false;await refresh();}
  });
  refresh();setInterval(refresh,5000);
})();
