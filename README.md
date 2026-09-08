# 내 에이전트 하네스 설계 키트
완성 소스를 복제하는 자료가 아니라, 제품 명세를 채우고 AI와 구현하는 출발점입니다. 하네스는 모델 호출, 도구 실행, 권한, 상태와 종료를 관리하는 프로그램입니다.

## 시작
압축을 풀고 이 README.md가 있는 폴더를 Claude Code 또는 OpenCode에서 엽니다. 다음처럼 요청합니다.

> 이 PRD를 읽고 같이 구체화하자. 결정이 필요한 것부터 물어봐 줘.

첫 응답에서 AI가 이미 정해진 목표와 미결정 사항을 구분하고 질문하는지 봅니다. 바로 코드를 만들거나 임의로 언어를 정하면 다음처럼 요청합니다.

> AGENTS.md와 PRD.md를 읽고, 내가 결정할 부분부터 질문해 줘.

답변은 짧게 해도 됩니다. AI가 문서를 고친 뒤 중요한 선택이 내 답과 맞는지 확인합니다. PRD 자체가 질문을 강제하는 기능은 아닙니다. 프로젝트 지침과 시작 요청으로 이 협업 방식을 안내합니다.

## 문서 역할
| 파일 | 읽거나 채우는 내용 |
|---|---|
| PRD.md | 사용자 문제, 제품 요구사항, 범위와 미결정 사항 |
| DECISIONS.md | 내가 선택한 내용과 이유, 미룬 사항 |
| INTERFACES.md | 입력·출력·오류·상태의 약속 |
| ACCEPTANCE.md | 완성 여부를 판정할 시나리오와 실제 증거 |
| TROUBLESHOOTING.md | 실패 증상별 확인 순서와 AI에게 전달할 최소 재현 기록 |
| IMPLEMENTATION_PLAN.md | 가장 작은 첫 연결부터 기능을 쌓는 순서 |
| AGENTS.md / CLAUDE.md | AI가 질문하고 합의를 기록하는 프로젝트 지침 |
| examples/spec-example.md | 모호한 문장을 검증 가능한 요구로 바꾸는 예 |

D01~D07의 최초 범위를 정하면 “합의한 명세로 첫 작업부터 구현해 줘”라고 요청합니다. 이후 범용 자료 작업과 코드 수정·테스트를 모두 검증합니다. D08/D09는 나중으로 미뤄도 됩니다. 파일 이름은 바꾸어도 되지만 지침의 참조도 함께 고쳐야 합니다.

## 지침을 읽는 방식
OpenCode는 프로젝트 AGENTS.md를 읽습니다. Claude Code는 CLAUDE.md에서 AGENTS.md를 가져오도록 구성했습니다. 제공 지침을 새로 생성할 필요는 없습니다. 전역 설정이나 도구 버전에 따라 동작이 달라질 수 있으므로 실제 첫 응답도 확인합니다.

- [OpenCode 프로젝트 규칙](https://opencode.ai/docs/rules/)
- [Claude Code 메모리와 파일 가져오기](https://code.claude.com/docs/en/memory)

이 키트는 실행 프로그램이나 API 키를 포함하지 않습니다. 구현 중 막히면 [실패 진단 안내](TROUBLESHOOTING.md)의 증상 표와 기록 양식을 사용합니다.

## 실행 방법 (구현한 하네스)
언어: Python 3.14. 표준 라이브러리만으로 반복 루프·경로 검사·읽기 도구를 짰고, 외부 패키지는 모델 제공자 연결(`openai`)과 자체 테스트(`pytest`)에만 쓴다.

```bash
py -m pip install -r requirements.txt
```

- `openai` — OpenAI 모델 제공자 어댑터(`harness/providers/openai_adapter.py`)가 쓴다. 없으면 `--provider openai`가 `missing_dependency` 오류로 바로 실패한다.
- `pytest` — 하네스 자체 단위 테스트(`tests/`)와, 실습용 결함 코드 검증 도구(`run_pytest`)가 대상으로 실행하는 것도 `pytest`다.

API 키는 소스에 넣지 않고 환경 변수 `OPENAI_API_KEY`로만 읽는다. 이 저장소의 `openai_key.env`(`.gitignore` 처리됨)에 `OPENAI_API_KEY=...` 한 줄로 넣어 두고, 그 값을 실행하는 프로세스의 환경 변수로 넘긴 뒤 실행한다. 다른 터미널에서 값을 export해도 이미 켜져 있는 프로세스는 모른다 — 매번 같은 프로세스에서 값을 읽게 해야 한다.

```bash
# bash/git-bash
set -a && source openai_key.env && set +a
py -m harness ask "examples/sample.srt 파일을 읽고 요약해줘" --root ~/Documents/korean-subtitle-corrector
```

```powershell
# PowerShell
Get-Content openai_key.env | ForEach-Object { if ($_ -match '^(.+?)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }
py -m harness ask "examples/sample.srt 파일을 읽고 요약해줘" --root ~/Documents/korean-subtitle-corrector
```

주요 플래그:
- `--dry-run` — 모의 어댑터로 실행, 실제 모델을 부르지 않는다. 하네스 자체 동작만 볼 때 쓴다.
- `--allow-write` — `write_file`·`run_pytest`를 연다. 켜지 않으면 읽기·검색만 가능하다(1단계 기본값).
- `--root` — 작업 폴더. 이 밖의 경로는 코드가 거부한다.

설치만으로 끝내지 말고 `--dry-run`으로 먼저 끝까지 통과하는지 확인한 뒤 실제 provider로 넘어간다. 환경 문제와 모델 문제를 나눠서 보기 위해서다.

주의: 파이프나 자동화 도구로 표준입력을 주는 환경(TTY가 아님)에서는 `--allow-write` 승인이 항상 자동 거절된다(안전 기본값). 실제 사람이 `y`/`n`을 직접 누르는 경로를 보려면 실제로 열려 있는 터미널 창에 위 명령을 그대로 입력해야 한다 — 2026-09-08에 실제 PowerShell 창에서 이 경로를 확인했다(ACCEPTANCE.md A03).

## Python 예시와 평가 도구
[Python 하네스·10문항 평가 자료](https://github.com/SunCreation/agent-building-practice/releases/download/v4.0.0/harness-lab.zip)는 직접 구현한 반복, 제공자 어댑터, 승인, 세션, 로컬 평가 연결, 점수 모니터를 포함합니다. 예시의 설계와 자기 PRD를 비교한 뒤 실제 기준/변경 후 실험을 수행하고 결과와 소스를 제출합니다.

`harness-lab-ref/harness-lab/`에 내려받아 두었다(이 디렉터리는 `.gitignore` 대상). 실행 위치는 `pyproject.toml`이 보이는 그 폴더이고, `uv sync --locked` → `uv run run.py --provider openai --workspace my-workspace --session ... --prompt "..."` 순서다. 자체 단위 테스트는 `uv sync --locked --extra dev` 후 `uv run python -m pytest -q`.

### 내 하네스와 실제로 비교한 결과 (2026-09-08)
| harness-lab 파일 | 책임 | 내 하네스 대응 | 실제로 돌려보고 확인한 차이 |
|---|---|---|---|
| `harness_lab/agent.py` | 모델→도구→결과 반복, 한도·세션 | [harness/loop.py](harness/loop.py) + [harness/contracts.py](harness/contracts.py) | 역할은 같음(요청→모델→도구→결과 연결을 한 곳에서 관리). harness-lab은 `asyncio`로 비동기 실행, 내 하네스는 동기 실행 — 둘 다 "반복을 직접 구현"한다는 원칙은 같음 |
| `harness_lab/providers.py` | OpenAI Responses / Ollama 변환 | [harness/providers/](harness/providers) | harness-lab은 Responses API(`store=False`)로 이전 대화 항목을 보존, 내 어댑터는 Chat Completions 방식. 둘 다 "제공자 응답을 내부 공통 형태로 맞추는 어댑터" 경계는 동일 |
| `harness_lab/tools.py` | 파일 도구, 승인, 명령 실행 | [harness/tools/](harness/tools) + [harness/approval.py](harness/approval.py) | **실제로 발견한 설계 차이**: harness-lab의 콘솔 승인(`cli.py`)은 `sys.stdin.readline()`만 확인하고 터미널인지(TTY)는 검사하지 않는다 — 그래서 파이프로 `y`를 흘려보내도 실제로 승인되고 파일이 바뀌었다(직접 재현함). 내 하네스는 `sys.stdin.isatty()`를 확인해 비대화 환경이면 무조건 `AlwaysReject`로 막는다(D06) — 자동화 파이프에서 의도치 않게 쓰기가 통과되는 경로를 원천 차단한다는 점에서 더 보수적 |
| `harness_lab/cli.py` | 입력·설정·세션 | [harness/__main__.py](harness/__main__.py) | harness-lab은 `--session` 이름으로 실제 대화 이어가기가 구현돼 있다. 내 하네스는 `loop.py`가 `history`는 받지만 CLI가 아직 노출 안 함(A08 NOT_RUN) — 이 부분은 아직 못 미친 지점으로 남겨 둠 |
| `harness_lab/local_agent.py`·`benchmark_source.py`·`grading.py`·`bench.py`·`report.py` | 벤치마크 10문항 연결·원본 채점·집계 | 없음(5단계 예정) | 10강에서 내 하네스를 직접 연결하는 대신, 이 참조 구현의 `bench.py`를 그대로 써서 10문항을 실행하는 경로. 내 코드가 아니라는 점을 실험 보고서에도 그대로 남겨야 함 |

그 밖에 실제 실행 중 발견한 것:
- **콘솔 인코딩**: harness-lab도 내 하네스가 겪었던 것과 같은 문제가 있다 — Windows 콘솔(cp949)에서 한글 출력이 깨진다(크래시는 안 남, 표시만 깨짐). 내 하네스는 이미 `sys.stdout.reconfigure(encoding="utf-8")`로 고쳤지만 harness-lab 자체는 고치지 않은 채로 왔다. 실제 파일(`my-workspace/meeting.txt`)과 대조해서 내용은 맞았음을 확인
- **Windows 플랫폼 실패**: `uv run python -m pytest -q` → 77개 중 9개 실패, 전부 symlink 생성 권한(WinError 1314)과 개행 문자(`\r\n` vs `\n`) 차이 — 내 하네스 테스트에서도 이미 symlink 하나를 skip 처리했던 것과 같은 종류의 플랫폼 한계이지 코드 결함은 아님
- **`run_command`에서 `python3` 실패**: receipt.py 수정 실습 중 모델이 `["python3", ...]`로 테스트를 돌리려 했는데 Windows의 `python3`는 Microsoft Store 연결용 스텁이라 정상 실행이 안 됨(`tool_errors: 1`). 파일 수정 자체는 승인·적용 성공, 별도로 `uv run python -m unittest discover -s my-workspace -p test_receipt.py`로 실제 3/3 통과 확인함
