# 원격 저장소에 게시하기

이 초기 전달본을 만든 환경에서는 GitHub DNS 연결과 HTTP socket이 제한되어 지정 원격의 기존 내용/기본 브랜치/라이선스를 조회하지 못했습니다. **로컬 커밋·패키지 준비와 원격 게시 완료는 다릅니다.** 아래는 연결이 가능한 환경에서 기존 저장소와 비교하여 게시하는 절차입니다.

## 기존 원격을 먼저 확인

```bash
git ls-remote https://github.com/kwonminki/workflow.git
git clone https://github.com/kwonminki/workflow.git workflow-remote
cd workflow-remote
git status --short
git branch --all
```

원격의 README·AGENTS·LICENSE·현재 코드를 먼저 읽습니다. 기존 작업과 충돌하면 원격 구조에 맞춰 이 전달본의 파일을 선택해서 통합합니다. 원격 기본 브랜치에 force push하거나 `--allow-unrelated-histories`로 무조건 합치지 않습니다.

## 비어 있거나 새 파일만 있는 저장소

로컬 전달본의 `workflow-starter.patch`를 검토하고 `--check`부터 실행합니다. 파일 충돌이 있으면 멈추고 수동 통합합니다.

```bash
git switch -c feat/reusable-workflow
# 실제 전달받은 patch 경로로 바꿉니다.
git apply --check /path/to/workflow-starter.patch
git apply /path/to/workflow-starter.patch
python3 -m unittest discover -s tests -v
node --check workflow/static/app.js

# 실제 서버 실행과 브라우저 검증도 수행합니다.
python3 -m workflow --data /tmp/workflow-publish-check init --title 'Publish check' --demo
python3 -m workflow --data /tmp/workflow-publish-check serve --port 8040
```

브라우저에서 계획 추가/의존 관계, Unicode 문서 선택 댓글, CLI inbox→답변, 알림 읽음/새답변, 원문 위치, 모바일 배치를 확인합니다. 임시 workspace는 기존 자료를 덮어쓰지 않도록 매번 새 폴더를 선택합니다.

```bash
git status --short
# 검토한 코드/문서 파일만 선택해 추가. 실제 데이터 폴더는 포함하지 않습니다.
git add README.md AGENTS.md .gitignore .env.example docs examples workflow tests
git diff --cached --check
git diff --cached --stat
git commit -m 'Add reusable local agent workflow workspace'
git push -u origin feat/reusable-workflow
```

그 후 저장소의 PR 절차를 사용합니다. 기본 브랜치가 비어 있는 경우에도 먼저 기능 브랜치로 푸시하고 소유자가 원하는 기본 브랜치 정책을 따릅니다. 별도 Git bundle은 전체 로컬 전달 이력을 확인할 때 사용하며 원격 이력을 대체하지 않습니다.

## 최종 보고에 남길 것

원격 commit/branch 또는 PR URL, 실제 실행한 테스트 수와 skip, 브라우저 확인 결과, 기존 원격 문서·라이선스를 어떻게 보존했는지 기록합니다. 네트워크 오류나 권한 부족으로 push가 실패하면 로컬 commit만 만든 상태임을 명시합니다.
