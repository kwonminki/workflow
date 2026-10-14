# 데이터 모델과 API

`state.json`의 schema는 `workflow.v1`입니다. 각 성공한 변경은 revision을 하나 올리고 events에 action·actor snapshot·원 입력·record ID·시각을 추가합니다. 모든 문자열은 일반 텍스트이며 웹은 textContent로 표시합니다. 문서도 Markdown 실행기가 아닙니다.

| 컬렉션 | 주요 필드 | 의미 |
| --- | --- | --- |
| nodes | id, title, group, status, goal, next_action, depends_on, owner, priority, completion, evidence, links | 계획과 사용자 확인 요청. depends_on의 순환/없는 노드를 거부 |
| documents | id, title, body, revision, history, author | revision은 본문 UTF-8 SHA-256. 수정 전 본문·제목·시각·작성자를 history에 보존 |
| threads | id, target, anchor, owner, messages | 문서/작업에 붙인 대화. 생성 당시 owner는 라우팅 참고이며 자동 전달이 아님 |
| messages | id, kind, reply_to, author, text, outcome, evidence, workflow_node, read_at | 사용자 의견 또는 에이전트 답변. 사용자 후속은 별도 미처리 의견 |
| agents | id, role, session, updated_at | 현재 등록. 과거 기록은 복사된 author snapshot 유지 |
| runs | id, node_id, source, author, command, cwd, inputs, outputs, status, exit_code | 실행 wrapper 또는 self_report. 종료·출력 facts는 실행 완료 후 추가 |
| events | id, at, action, actor, record_id, data | 변경 이력. 삭제/정리 UI 없음 |

ID는 영문·숫자·`_`·`-`만 사용합니다. 우선순위는 정수 0~100이며 0이 먼저입니다. 작업 상태는 planned/running/partial/review/done/blocked입니다. `review`는 사용자가 봐야 하는 명시적인 작업입니다.

댓글 anchor는 document revision, Python/Unicode codepoint 기준 start/end, exact quote, 80자 prefix/suffix를 보존합니다. 브라우저 UTF-16 offset은 codepoint로 변환합니다. 현재 버전만 형광 표시하며 이전 버전을 자동 재부착하지 않습니다. 겹치는 인용은 구간을 나누어 thread 선택을 제공합니다.

답변 `seen`은 읽고 판단한 기록, `applied`는 실제 반영+근거, `deferred`는 존재하는 후속 노드와 이유입니다. 원 사용자 message에 applied/deferred가 붙었을 때만 pending에서 빠집니다. 새 후속 의견은 이전 상태를 상속하지 않습니다. 답변 `read_at`은 이와 독립적인 공유 작업공간 사용자 상태입니다. 사용자별 읽음 모델은 아닙니다.

## API

- `GET /api/state`: 작업공간 전체 snapshot. 인증 없음, localhost Host만 허용.
- `POST /api/action`: `{action, data, revision}`. 같은 Origin·JSON·현재 revision 필수. 최대 256 KiB.
- 브라우저 action은 node/comment/followup/read만 허용합니다. author는 서버가 user로 설정합니다.
- agent/document/reply/run 기록은 로컬 CLI로 수행합니다. 웹에서 에이전트 사칭이나 셸 실행 action을 허용하지 않습니다.
- 충돌은 HTTP 409입니다. 웹은 저장 오류를 표시하고 입력을 자동 덮어쓰지 않습니다. 새로고침 후 현재 자료를 확인하고 다시 제출합니다.
- 정적 파일은 `/`, `/app.js`, `/style.css`만 허용합니다. 작업 데이터나 임의 파일을 URL 경로로 열지 않습니다.

로컬 CLI는 신뢰된 사용자 권한으로 실행되며 암호학적인 작성자 인증/변조 방지 장치가 아닙니다. state 파일에 접근 가능한 사용자는 내용을 바꿀 수 있습니다. 원자적 rename과 POSIX lock은 단일 호스트 로컬 디스크를 전제로 합니다. 전체 JSON 재작성 방식이라 대규모 이력/멀티 사용자 운영 전 별도 저장 계층이 필요합니다.
