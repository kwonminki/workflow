# 게시 전 재검증 · 2026-10-14

접근 제한 해제 후 별도 임시 작업공간에서 다시 확인했습니다. 아래 초기 전달본의 skip/미검증 기록은 당시 이력이며 현재 검증 결과는 다음과 같습니다.

- Python unittest **26개 모두 통과, skip 0**. 실제 TCP 서버를 통한 HTTP 통합 검사 4개 포함.
- JavaScript 구문 검사 통과.
- 실제 Chromium 브라우저 **17개 검사 통과**, runtime exception 0.
- 데스크톱 1440px / 모바일 390px에서 그래프 표시·확대·연결 강조, 문단 댓글, 이모지 포함 드래그 인용, 형광 표시, CLI 답변을 확인했습니다.
- 답변 하나의 읽음 처리, 새 답변의 독립된 안 읽음 상태, 이전 알림 다시 열기, 여러 인용 중 정확한 두 번째 인용으로 이동, 새 사용자 의견의 pending 전환을 확인했습니다.
- 모바일 그래프/문서의 화면 너비 초과가 없음을 검사하고 실제 스크린샷도 검토했습니다.
- 모든 브라우저 쓰기는 합성 임시 작업공간에서 수행했습니다. 기존 운영 서비스·사용자 댓글·읽음 상태는 사용하지 않았습니다.
- GitHub 원격 연결 성공. 최초 게시 전 기존 branch/HEAD가 없는 빈 저장소임을 확인했습니다.

재현: `python3 -m unittest discover -s tests -v`, `node --check workflow/static/app.js`. 선택적인 실제 브라우저 검사는 Node 22 이상과 `CHROME_BINARY`를 지정하여 `node tests/browser-smoke.mjs`로 실행합니다. `WORKFLOW_BROWSER_OUTPUT`을 지정하면 JSON 결과와 스크린샷을 해당 폴더에 남깁니다.

---

# 초기 전달본 검증 · 2026-10-14

- Python unittest: 26개 중 **22개 통과, 4개 skip**.
- 통과: 계획 DAG/긴 3,000노드 체인·순환·누락 참조, revision 충돌, 동시 기록, 독립 workspace, 실제 명령 성공/exit7 실패/기동 실패 기록, 출력 bytes/SHA, 댓글 gate, seen/applied/deferred, 후속 의견, 사용자 읽음 분리, 과거 작성 세션, 이모지 인용과 문서 이력.
- socket을 만들지 않는 실제 HTTP handler 검사 5개 통과: 정적 allowlist, 경로 경계, Host/Origin/Content-Type, 저장 revision 충돌, 웹 실행/작성자 사칭 action 거부, CSP.
- 실제 TCP HTTP 통합검사 4개는 환경의 `Operation not permitted`로 skip. 서버 결함 판정이나 HTTP 통과로 세지 않음.
- JavaScript `node --check workflow/static/app.js` 통과.
- 전체 화면의 실제 브라우저 상호작용은 이 환경에서 미검증. 연결 가능한 환경에서 `docs/PUBLISHING.md`의 브라우저 확인 절차가 필요함.
- 공개 소스는 합성 예제만 포함. 실제 사용자 댓글/실험 데이터/개인 서비스 식별자/비밀 값/내부 주소를 복사하지 않음.
- 원격 저장소 조회/게시: GitHub DNS 연결 제한으로 **미완료**. 원격 기존 내용과 라이선스를 확인하지 못했으므로 강제 push/덮어쓰기를 하지 않음.

이 기록은 초기 전달 시점의 결과입니다. 후속 코드 변경 뒤에는 관련 검사를 다시 실행하고 실제 검증 범위를 갱신합니다.
