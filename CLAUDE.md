# CLAUDE.md

## Mandatory Session Start Protocol

이 protocol은 **모든 새로운 Claude Code session의 첫 번째 user turn**에 적용된다 — 그 turn의
내용, 중요도, substantive 여부를 판단해서 실행 여부를 결정하지 않는다.

첫 번째 user turn이 다음 중 무엇이든 — 목록 중 하나가 아니라고 해서 protocol을 건너뛸 근거가
되지 않으며, 아래에 없는 형태라도 마찬가지다:

- `hi`, `hello` 등 단순 인사
- casual message
- implementation / code modification
- architecture·design review
- planning
- repository 상태에 대한 질문
- documentation 작업
- 단순 discussion
- meta-level question (예: "이 프로젝트 뭐하는 거야?")

즉, **첫 user turn이 "substantive"한지 판단해서 protocol 실행 여부를 결정하지 않는다.**
"인사만 했으니 아직 읽지 않았다"거나 "아직 구현 작업을 시작하지 않았기 때문에 읽지 않았다"는
해석은 허용되지 않는다.

첫 번째 user turn에 **답하거나 행동하기 전에**, 반드시 다음 순서로 현재 repository
state를 실제로 복원한다 (memory나 이전 conversation context로 대체하지 않는다):

1. `README.md`를 읽는다 (상단 "Current Status" / "Next" 요약 포함).
2. `docs/dev-log/`에서 **파일명(날짜) 기준 가장 최신 dev-log 파일을 찾아서** 읽는다.
3. `git status`를 실행한다.
4. `git log --oneline --decorate -5`를 실행한다.

이 네 가지를 실제로 실행/열람하기 전에는 "확인했다"고 말하지 않는다 — README/dev-log를 읽었다고
주장하려면 **현재 session에서** 실제 내용을 확인한 상태여야 한다.

위 결과를 바탕으로 최소한 다음을 파악한다:

- current repository state
- latest completed work
- current FROZEN architecture/contracts
- unresolved / open items
- exact NEXT entry point
- uncommitted changes

### Invariants

- Repository state를 이전 conversation context나 memory만으로 추론하지 않는다.
- README와 최신 dev-log는 canonical project handoff로 취급한다.
- 단, documentation(README/dev-log)과 실제 git/repository state가 서로 일치하는지도 함께
  확인한다 — documentation만 믿고 넘어가지 않는다.
- README/dev-log와 실제 repository state 사이에 의미 있는 conflict가 발견되면, 임의로 해석하거나
  조용히 수정하지 말고 먼저 사용자에게 보고한다.
- 첫 user turn이 substantive가 아니라는 이유로(예: `hi`/`hello`뿐이라는 이유로) 이 protocol을
  skip하지 않는다.
- 이 protocol은 **사용자의 첫 user turn이 들어온 뒤**, 그 turn을 처리하는 과정의
  일부로 수행한다 — 세션이 시작되자마자 사용자 입력 없이 선제적으로 tool을 실행하라는 뜻이 아니다.
- Session Start Protocol 완료 후에만 사용자의 첫 user turn을 실제로 처리(답변/작업)한다.

```text
Claude Code 새 세션
        ↓
사용자의 첫 user turn (내용 무관 — hi 포함)
        ↓
CLAUDE.md Session Start Protocol
        ↓
README.md
latest dev-log
git status
git log
        ↓
현재 프로젝트 상태 복원
        ↓
사용자의 요청 처리
```
