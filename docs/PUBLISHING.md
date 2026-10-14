# 변경 검토와 게시

2026-10-14: 초기 준비 환경의 네트워크 제한을 해제한 뒤 지정 GitHub 저장소에 연결했습니다. 기존 branch와 HEAD가 없는 빈 저장소임을 확인했고, 첫 배포는 `main`을 사용합니다. 이후 변경은 아래 기능 브랜치 절차를 따릅니다.

## 기존 원격과 작업 상태 확인

```bash
git fetch origin
git status --short
git branch --all
```

원격 README·AGENTS·LICENSE·현재 코드를 먼저 읽습니다. 개인 작업공간의 `state.json`, 댓글, 실행 로그, 인증 정보는 코드 게시 대상이 아닙니다. 기존 작업과 충돌하면 내용을 확인하고 통합하며 강제 push로 덮어쓰지 않습니다.

## 변경 구현과 검증

```bash
git switch main
git pull --ff-only
git switch -c feat/your-change

# 변경 뒤 실행
python3 -m unittest discover -s tests -v
node --check workflow/static/app.js
```

실제 서버와 브라우저도 합성 작업공간에서 확인합니다. 기존 서비스와 겹치지 않는 포트를 사용합니다.

```bash
# 같은 경로의 기존 자료를 덮어쓰지 않도록 매번 새 폴더를 선택합니다.
python3 -m workflow --data /tmp/workflow-publish-check init --title 'Publish check' --demo
python3 -m workflow --data /tmp/workflow-publish-check serve --port 8041
```

브라우저에서 계획 추가/의존 관계, Unicode 문서 선택 댓글, CLI inbox→답변, 알림 읽음/새답변, 정확한 원문 위치와 모바일 배치를 확인합니다. 실제 검증 범위와 결과는 `docs/VERIFICATION.md`에 기록합니다. 환경 때문에 건너뛴 검사를 통과로 표시하지 않습니다.

## 커밋과 원격 확인

```bash
git status --short
# 검토한 파일만 추가하며 실제 프로젝트 데이터는 제외합니다.
git add <reviewed-files>
git diff --cached --check
git diff --cached --stat
git commit -m 'Describe the concrete change'
git push -u origin feat/your-change
```

그 후 저장소의 PR 절차를 사용합니다. 승인된 기본 브랜치 게시에도 force push를 사용하지 않습니다. push 성공 이후 `git ls-remote origin <branch>`의 SHA가 로컬 커밋과 일치하는지 확인합니다.

최종 보고에는 원격 commit/branch 또는 PR URL, 테스트 수와 skip, 브라우저 확인 범위를 남깁니다. 연결·권한 오류로 게시하지 못했다면 로컬 커밋만 만든 상태임을 명시합니다. 소스 ZIP/patch/bundle은 전달 방식이며 원격 이력을 대체하지 않습니다.
