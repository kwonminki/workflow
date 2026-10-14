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
