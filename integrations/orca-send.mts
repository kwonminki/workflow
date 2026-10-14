// Reuse Connector's process/session discovery and guarded Orca terminal client.
// stdin JSON keeps page text out of process argv. No shell or second Codex writer.
import { pathToFileURL } from 'node:url';
import path from 'node:path';
let attempted = false;
try {
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  const input = JSON.parse(raw);
  if (!['list', 'check', 'send'].includes(input.action) || (input.action !== 'list' && !/^[0-9a-f-]{36}$/i.test(input.session_id))) throw new Error('Invalid action/session.');
  const { createOrcaClient, sameOrcaTarget } = await import(pathToFileURL(path.join(input.root, 'apps/discord-bot/src/orcaClient.ts')).href);
  const client = createOrcaClient(input.command);
  if (input.action === 'list') {
    const {listOrcaCodexOwners} = await import(pathToFileURL(path.join(input.root,'apps/discord-bot/src/orcaSessionOwner.ts')).href);
    const owners = await listOrcaCodexOwners();
    const {terminals} = await client.list();
    const sessions = owners.flatMap(owner => {
      const t=terminals.find(t=>t.handle===owner.terminalHandle && t.agentIdentity==='codex' && t.connected && t.writable && !t.orphaned);
      return t ? [{session_id:owner.sessionId,title:t.title}] : [];
    });
    console.log(JSON.stringify({status:'ready',sessions}));
  } else {
  const before = await client.resolveSession('codex', input.session_id);
  if (!before) throw new Error('The configured Codex session has no live Orca owner.');
  if (input.action === 'check') {
    console.log(JSON.stringify({status:'ready',target:{handle:before.handle,incarnationId:before.incarnationId,session_id:input.session_id}}));
  } else {
    await client.screen(before, true);
    const current = await client.resolveSession('codex', input.session_id);
    if (!current || !sameOrcaTarget(before,current) || before.processKey !== current.processKey) throw new Error('Session owner changed; no input forwarded.');
    attempted = true;
    const result = await client.send(current,input.text);
    console.log(JSON.stringify({...result,status:result.accepted?'accepted':'failed',target:{handle:current.handle,incarnationId:current.incarnationId,session_id:input.session_id}}));
  }
  }
} catch {
  console.log(JSON.stringify({status:attempted?'unknown':'failed',error:attempted?'Orca 전송 결과 불명. 원래 세션에서 수신 여부 확인 필요.':'대상 세션·Orca 연결 또는 미전송 입력을 확인하세요. 메시지를 보내지 않았습니다.'}));
  process.exitCode=1;
}
