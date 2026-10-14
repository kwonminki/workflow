# Discord 알림과 메인 세션 연결

## 무엇이 연결되는가

선택 기능입니다. 기본 웹은 Python만으로 동작하고, 이 연동을 켤 때만 **Node.js와 설치된 Discord Connector**를 사용합니다.

- `지금 확인`에 `review` 작업이 새로 나타나거나 제목·목표·다음 행동·근거가 바뀌면 Discord 전용 스레드로 알립니다. `review → done → review`도 다시 알립니다. 모든 실행·문서·샘플이 알림 대상은 아닙니다.
- 웹 홈의 에이전트 처리 대기에도 새 사용자 의견이 나타나면 제목과 위치를 알립니다. 댓글 본문 전체를 Discord로 복사하지 않습니다.
- 첫 정상 조회는 기존 항목의 기준만 저장합니다. 웹을 닫아도 별도 worker가 15초마다 확인합니다. 15초 사이에 생겼다가 사라진 항목은 감지하지 못할 수 있습니다.
- 오른쪽 위 **메인 세션에 완료 전달하기**를 누르면 보고 있던 페이지와 제목, 요청 ID가 설정된 **기존 Codex/Orca 세션**으로 전달됩니다. 저장하지 않은 편집 내용은 보내지 않으므로 먼저 저장하세요.
- Discord 스레드는 **알림 전용**입니다. 이 스레드의 답글을 임의 명령으로 실행하지 않습니다. 세션과의 양방향 대화는 Connector가 이미 연결한 원래 세션 스레드에서 합니다.
- 버튼은 댓글을 처리 완료로 바꾸거나 사용자 알림을 읽음 처리하지 않습니다. `accepted`는 터미널 입력 수락이며, 에이전트가 읽었거나 작업을 완료했다는 뜻은 아닙니다.

## 1. Discord 에이전트 봇 설치 권장

여러 프로젝트/컴퓨터에서 에이전트를 사용하는 경우 [ai-agent-discord-connector](https://github.com/kwonminki/ai-agent-discord-connector)를 함께 설치하면 Discord에서 세션을 찾아 대화하고 완료 알림을 받을 수 있습니다.

설치 에이전트에게 저장소 URL과 함께 다음과 같이 요청할 수 있습니다.

> 이 저장소의 AI Agent Guide를 읽고 이 서버에 설치해 주세요. 내 비공개 Discord 서버와 Codex/Orca 세션을 연결하고 서비스 상태를 확인해 주세요.

상세 설치·업데이트·봇 권한은 Connector의 [AI Agent Guide](https://github.com/kwonminki/ai-agent-discord-connector/blob/main/docs/AI_AGENT_GUIDE.md), Orca 연결은 [한국어 Orca 안내](https://github.com/kwonminki/ai-agent-discord-connector/blob/main/docs/orca.ko.md)를 따릅니다. 이 프로젝트는 봇을 자동 설치하거나 봇 토큰을 발급하지 않습니다.

현재 어댑터는 Connector **2.3.1의 소스 checkout**에 있는 `apps/discord-bot/src/orcaClient.ts`와 설치된 `node_modules/.bin/tsx`를 재사용합니다. Connector 업데이트로 이 내부 경로/API가 바뀌면 다시 검사해야 합니다. npm 전역 설치만 있고 소스가 없는 형태는 현재 지원하지 않습니다.

봇에는 전용 스레드를 만들고 메시지를 보낼 권한이 필요합니다. 멘션을 받으려면 Discord 사용자 ID를 명시하세요. OS/Discord의 음소거·알림 설정까지 웹이 강제로 바꾸지는 않습니다.

## 2. 정확한 세션을 지정해 연결

Orca에서 실행 중인 **메인 Codex 세션의 실제 UUID**를 사용합니다. 에이전트는 자신의 `CODEX_THREAD_ID`를 확인할 수 있습니다. 설치 도구는 Node 실행 파일의 절대 경로도 `node_command`로 저장하므로 로그인 셸과 systemd의 PATH 차이에 의존하지 않습니다. Node 설치 위치를 바꾸면 이 값도 갱신하세요. 세션 제목/폴더를 보고 추측하거나 서브에이전트 UUID를 넣지 마세요. Connector 설정에 있는 Orca 명령과 해당 CLI의 relay 연결이 서버 서비스에서도 사용 가능해야 합니다.

```bash
# workflow 저장소 루트에서 실행. 값은 자신의 환경에 맞게 변경합니다.
python3 integrations/setup_bridge.py \
  --config /absolute/private/workspace/bridge.json \
  --connector /absolute/path/ai-agent-discord-connector \
  --session YOUR_ACTUAL_CODEX_SESSION_UUID \
  --base-url http://192.168.1.20:18743 \
  --thread-name 'My project · 지금 확인' \
  --notify-user YOUR_DISCORD_USER_ID
```

`--notify-user`는 선택입니다. 없으면 메시지는 올라가지만 사용자 멘션은 없습니다. Connector 설정 위치가 다르면 `--connector-config /path/to/config.json`을 추가합니다. 기존 전용 스레드를 쓸 때는 `--thread-id ID`를 추가합니다.

설정 도구는 **세션 소유 프로세스 확인 → 봇의 서버/채널 확인 → 전용 스레드 생성 → 로컬 설정 저장 → 연결 안내** 순서로 실행합니다. 이미 설정 파일이 있으면 중복 스레드를 만들지 않습니다. 이 명령은 실제 Discord 스레드를 만드는 명시적 작업입니다. 토큰은 기존 Connector 설정에서 실행 시 읽고 새 설정이나 Git에는 복사하지 않습니다.

전송 직전 동일 세션의 프로세스·터미널 incarnation·runtime을 다시 확인합니다. 미전송 로컬 입력, 죽은 세션, 연결 끊김, 소유 프로세스 교체는 전송을 막습니다. 새 Codex writer를 열거나 다른 세션으로 우회하지 않습니다. SSH로 연결한 Orca도 **같은 서버 계정에서 기존 Connector의 세션 연결 검사가 성공할 때** 지원됩니다. 모든 원격 환경을 자동 발견한다고 가정하지 않습니다.

## 3. 웹과 알림 worker 실행

```bash
# 터미널 1: 웹 서버
export WORKFLOW_BRIDGE_CONFIG=/absolute/private/workspace/bridge.json
python3 -m workflow --data /absolute/private/workspace serve \
  --host 192.168.1.20 --port 18743

# 터미널 2: 연결 검사 후 계속 실행하는 worker
python3 -m workflow.bridge --config /absolute/private/workspace/bridge.json check
python3 -m workflow.bridge --config /absolute/private/workspace/bridge.json watch
```

설정의 `base_url`/`source_url`과 실제 포트를 맞추세요. `--port 0`으로 빈 포트를 골랐다면 시작 로그에서 포트를 확인한 후 연결 설정을 만듭니다. 재시작 때마다 임의 포트를 바꾸면 설정도 변경해야 하므로 상시 운영에는 한 번 고른 포트를 고정하는 편이 편합니다.

Linux에서 로그아웃 후에도 유지하려면 사용자 systemd 서비스를 설치할 수 있습니다. 아래 경로는 모두 실제 절대경로로 바꿉니다. 웹 서비스에도 `Environment=WORKFLOW_BRIDGE_CONFIG=...`를 추가해야 버튼을 사용할 수 있습니다.

```ini
# ~/.config/systemd/user/workflow-bridge.service
[Unit]
Description=Workflow Discord notifications and session delivery
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/absolute/path/workflow
ExecStart=/usr/bin/python3 -m workflow.bridge --config /absolute/private/workspace/bridge.json watch
Restart=on-failure
RestartSec=10
UMask=0077

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now workflow-bridge.service
systemctl --user status workflow-bridge.service
```

OS 계정의 로그아웃 후 서비스 유지 정책은 서버 관리자 설정에 따릅니다. macOS에서는 별도 터미널 또는 본인의 서비스 관리 방식을 사용합니다. 기본 웹 실행만으로 worker가 자동 설치되지는 않습니다.

웹에는 **전달 중 / 전달됨 / 연결 확인 필요**만 간단히 표시합니다. 아래 상세 상태와 진단은 운영 기록에서 확인합니다.

## 상태·복구·세션 교체

```bash
python3 -m workflow.bridge --config /absolute/private/workspace/bridge.json status
python3 -m workflow.bridge --config /absolute/private/workspace/bridge.json once
```

설정 옆 `bridge.state.json`에 요청·Discord 알림 영수증·재시도 상태가 남고, `bridge.lock`과 `bridge.worker.lock`이 중복 처리를 막습니다. 설정 파일뿐 아니라 이 파일들도 비공개 경로에 보관하고 백업합니다. 기존 `state.json`과 별도입니다. 웹 상태는 `/api/session-bridge`에서 비밀 값 없이 제공합니다.

| 상태 | 의미·조치 |
| --- | --- |
| queued / sending | 대기/전송 중. worker heartbeat가 오래됐으면 서비스 상태 확인 |
| accepted | 기존 터미널이 입력을 수락. `turnStarted`는 별도 관측이며 완료 보장 아님 |
| failed | 전송 거절/세션 불일치 등. 대상 세션과 미전송 입력을 확인 후 버튼으로 새 요청 가능 |
| unknown | 타임아웃/전송 중 종료로 결과 불명. 중복 실행 방지를 위해 자동 재전송 안 함. 원래 세션 확인 후 필요할 때만 새 요청 |

같은 요청 ID는 한 번만 처리하고, 여러 탭의 20초 내 연속 클릭도 기존 영수증을 반환합니다. Discord는 고정 nonce와 최근 100개 메시지의 고유 표식으로 중복을 줄이며 최대 5회 지수 지연 재시도합니다. 아주 오래된 모호한 실패까지 분산 시스템의 exactly-once를 보장하지는 않습니다. 최종 `failed` 알림은 운영자가 원인과 기존 스레드 수신 여부를 확인해야 합니다.

메인 세션을 바꾸려면 worker를 멈추고 설정의 `session_id`를 새 실제 UUID로 변경한 뒤 `check`를 실행하고 다시 시작합니다. 옛 세션에 묶인 대기 요청을 새 세션으로 돌리지 않습니다. 새 요청을 명시적으로 제출하세요. 같은 세션을 정상 재개한 경우 현재 소유 프로세스를 다시 확인합니다. 연동을 끄려면 worker를 멈추고 설정의 `enabled`를 `false`로 바꿉니다.

이 API는 인증 없는 개인/신뢰된 내부망 웹의 명시적 사용자 버튼입니다. 외부 공개용 권한 시스템이 아니며, 같은 네트워크의 불특정 사용자가 접근하는 서버에는 인증을 추가해야 합니다. 브라우저는 명령·세션·봇 토큰을 지정할 수 없고, 서버의 고정 설정만 사용합니다.
