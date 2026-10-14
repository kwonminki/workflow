"""Synthetic data only. Never copy a real workspace into a public template."""
def populate(store):
    store.change('agent', {'id': 'coordinator', 'role': 'Technical coordinator', 'session': 'example-session-001'})
    store.change('agent', {'id': 'worker', 'role': 'Implementation', 'session': 'example-session-002'})
    nodes = [
        {'id': 'contract', 'title': '입력 계약 정하기', 'group': '설계', 'status': 'done',
         'goal': '입출력 형식과 검증 범위를 합의한다.', 'owner': 'coordinator', 'depends_on': [],
         'completion': '합성 예제용 계약을 작성했다. 실제 프로젝트 승인을 뜻하지 않는다.', 'evidence': ['#document/example-design']},
        {'id': 'implementation', 'title': '샘플 변환 구현', 'group': '실행', 'status': 'planned',
         'goal': '입력 한 건을 변환하고 결과를 검증한다.', 'owner': 'worker', 'depends_on': ['contract'],
         'next_action': '작은 합성 입력으로 실행하고 명령과 결과를 남긴다.'},
        {'id': 'documentation', 'title': '사용 설명 정리', 'group': '실행', 'status': 'partial',
         'goal': '다른 작업자가 재현하도록 한다.', 'owner': 'coordinator', 'depends_on': ['contract'],
         'next_action': '실행 결과를 설명에 연결한다.'},
        {'id': 'review', 'title': '사용자 검토', 'group': '검토', 'status': 'review',
         'goal': '남은 판단만 사용자에게 묻는다.', 'owner': 'coordinator', 'depends_on': ['implementation', 'documentation'],
         'next_action': '결과, 질문 이유, 답변 후 행동을 함께 제시한다.'},
    ]
    for row in nodes:
        store.change('node', row, 'coordinator')
    store.change('document', {'id': 'example-design', 'title': '예제 프로젝트의 목표와 결과', 'body':
        '목표\n작은 입력을 변환한 뒤 검증 근거와 다음 행동을 한곳에서 찾습니다.\n\n'
        '시도\n입력 계약을 먼저 고정하고 구현과 설명 작업을 병렬로 진행합니다.\n\n'
        '결과\n이 문서는 합성 예시입니다. 아직 실제 변환 명령을 실행하지 않았습니다.\n\n'
        '사용자에게 확인할 내용\n문장을 드래그하고 + 메모를 누르거나 문단을 클릭해서 의견을 남겨 보세요.\n\n'
        '판단과 다음 행동\n댓글의 문맥을 읽은 에이전트가 실제 근거와 함께 답합니다. 미실행 작업은 계획에 남깁니다.'}, 'coordinator')
