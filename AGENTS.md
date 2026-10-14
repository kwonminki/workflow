# Workflow 코드 기여 지침

- README.md와 docs/AGENT_PROTOCOL.md, docs/DATA_MODEL.md를 먼저 읽습니다.
- 사용자가 지정한 실제 프로젝트 데이터 경로를 확인합니다. 다른 프로젝트의 workspace를 추측해 쓰지 않습니다.
- 적용된 프로젝트에서는 시작/재개/다음 실행 전에 `python3 -m workflow --data <workspace> inbox --require-clear`로 사용자 의견과 전체 스레드를 확인합니다.
- 실제 반영에는 applied와 근거, 후속 작업에는 deferred와 존재하는 계획 노드를 연결합니다. seen은 처리 완료가 아닙니다.
- 사용자 알림을 대신 읽음 처리하지 않습니다. 원문 댓글·문서 버전·과거 작성 세션을 덮어쓰지 않습니다.
- 서비스에는 임의 셸 실행·파일 다운로드 API를 추가하지 않습니다. 외부 서비스 연동이 실제 제공되는지 문서와 코드를 맞춥니다.
- 새로운 데이터 폴더는 Git에서 제외합니다. 공개 파일에 토큰, 개인 댓글, 실제 프로젝트 데이터·호스트·경로·계정 ID를 복사하지 않습니다.
- 변경 검증은 `python3 -m unittest discover -s tests -v`와 `node --check workflow/static/app.js`를 사용합니다. 실제로 실행하지 못한 검사를 통과했다고 적지 않습니다.
