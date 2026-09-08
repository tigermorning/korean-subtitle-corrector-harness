# 구현 계획
## 시작 조건
D01~D10 확정(D09는 DEFERRED). 계약은 INTERFACES.md, 완료 조건은 ACCEPTANCE.md. 학생이 1단계 구현을 요청하면 착수한다.

대상 저장소는 `~/Documents/korean-subtitle-corrector` **원본**이며 1단계에는 쓰기 도구가 없다. 하네스 소스는 이 저장소의 `harness/`에 둔다(D10).

## 0. 파일 배치와 실행 방법

```
harness-design-kit/
  harness/
    __init__.py
    __main__.py        # CLI 진입점: ask / show
    contracts.py       # Message, ToolSpec, ToolCall, ModelReply
    loop.py            # 반복 루프, 상한, 종료 조건
    paths.py           # 경로 검사기 (허용 루트 + 제외 패턴)
    approval.py        # 승인자 (콘솔 / 항상거절 / 테스트용)
    tools/
      __init__.py      # 도구 등록과 JSON Schema. preview 유무로 승인 대상 판단
      read_file.py
      search_text.py
      write_file.py    # 2단계
      run_pytest.py    # 2단계
    providers/
      __init__.py      # 어댑터 선택
      openai_adapter.py
      mock_adapter.py  # --dry-run
      ollama_adapter.py  # 3단계
    session.py         # JSONL 기록
    .sessions/         # 실행 기록 (git 추적 제외)
  fixtures/
    spacing_rules/     # 의도적 결함 코드 + 실패하는 테스트 (A03·A04용)
      rules.py
      test_rules.py
  tests/
    test_paths.py
    test_loop.py
    test_tools.py
    test_write_tools.py
  requirements.txt
```

의존성: `openai` (OpenAI 어댑터), `pytest` (하네스 자체 테스트). 그 외는 표준 라이브러리로 한다. 검색은 `re` + `pathlib.Path.rglob`으로 구현하고 외부 ripgrep에 의존하지 않는다.

실행: `python -m harness ask "<요청>" --root ~/Documents/korean-subtitle-corrector`
API 키: `OPENAI_API_KEY` 환경변수에서만 읽는다. 소스·문서·세션 기록 어디에도 값을 넣지 않는다.

## 1. 첫 수직 구현
사용자 요청 → 실제 모델 → 읽기 도구 → 모델에 실행 결과 전달 → 결과 표시를 가장 작은 입력으로 잇는다.

- 선택 작업/도구: 오교정 사례 1건의 원인 규칙 찾기. 도구는 `read_file`, `search_text` 둘
- 구현 순서 (각 단계가 끝나면 다음으로):

| 순서 | 내용 | 끝났다고 볼 근거 |
|---|---|---|
| 1-1 | `contracts.py` — 내부 타입 4개 | 타입만으로 어댑터 없이 import 성공 |
| 1-2 | `paths.py` — 경로 검사기 | `tests/test_paths.py`가 탈출·symlink·제외·대소문자 4종을 막는 것 확인 |
| 1-3 | `tools/` — 도구 2개 + JSON Schema | `tests/test_tools.py`가 정상 반환과 5종 오류 구조를 확인 |
| 1-4 | `session.py` — JSONL 기록 | 이벤트 8종이 나오고 키 값이 어디에도 없음 |
| 1-5 | `providers/mock_adapter.py` — 모의 어댑터 | 스크립트한 도구 요청 순서를 그대로 돌려줌 |
| 1-6 | `loop.py` — 반복 루프 | `tests/test_loop.py`가 정상 종료·상한 종료·bad_arguments 3종 확인 |
| 1-7 | `__main__.py` — CLI | `--dry-run`으로 끝까지 통과 (A02) |
| 1-8 | `providers/openai_adapter.py` — 실제 호출 | A01 실행, 실제 모델명·응답 기록 |

- 실제 모델 사용 전 모의 응답으로 확인할 부분: A02(도구 요청→실행→연결→종료), A05(경로 검사 3종 — 모의 어댑터가 금지 경로를 강제 호출), A06(반복 상한), A07(a) bad_arguments. 이 넷은 모델을 부르지 않고 검증한다. 모델 호출 전에 하네스 자체가 옳은지 먼저 못 박기 위해서다
- 완료 증거: ACCEPTANCE.md의 A01·A02·A05·A06·A07을 실제 상태(PASS/FAIL)로 갱신하고, 실제 모델 검증 기록 칸을 채운다. 세션 JSONL 파일 경로를 증거로 남긴다

## 2. 범용 작업의 품질
S01을 라벨 71건 중 5~10건으로 돌린다. 원문 대조, 인자 오류, 경로 이탈, 반복 한도를 검증한다.

- 근거 유효율 검사기: 최종 답에서 `파일:줄` 패턴을 뽑아 파일 존재와 줄 번호 범위를 대조하는 작은 스크립트. 하네스 동작 검증이며 모델 답의 정답 여부와 분리한다
- 자주 나오는 실패를 계약이나 도구 스키마 수정으로 고친다. 프롬프트만 고쳐 넘기지 않는다
- A/B 비교(ACCEPTANCE.md)를 여기서 1회 실행한다. A는 도구 없이 1회 호출, B는 하네스. 같은 모델·프롬프트·문항

## 3. 코딩 작업과 권한 (2단계)
- 실습용 결함: 대상 저장소를 고치지 않기 위해, `harness-design-kit/fixtures/`에 작은 결함 코드와 테스트를 따로 만든다. 대상 저장소에 대한 쓰기는 학생이 별도로 허용할 때만 연다
- `write_file` — 적용 전 통합 diff와 대상 경로를 보여 주고 y/n. 보여 준 내용의 해시를 승인에 묶어, 그 사이 파일이 바뀌면 승인을 무효로 한다
- `run_pytest` — 실행 파일 `pytest` 고정, 인자는 검사한 경로와 `-k` 표현식만, 셸 미경유, 시간 상한 120초. 실제 명령줄과 작업 디렉터리를 보여 주고 y/n
- 상태에 `waiting_approval` 추가. 거절은 그 호출만 실패 처리하고 반복 계속
- 검증: A03(승인 후 적용+테스트 통과), A04(거절 시 파일 바이트 불변)

## 4. 제품 기능 (3단계)
- `providers/ollama_adapter.py`. 같은 `complete()` 시그니처. Ollama가 `tool_call.id`를 주지 않으면 어댑터가 자체 id를 만들고 그 사실을 기록한다
- 시작 시 모델의 도구 호출 지원 여부를 확인하고, 지원하지 않으면 자연어에서 도구 요청을 추측하지 않고 `failed`로 끝낸다
- 검증: A10 — 같은 읽기 작업을 두 provider로 실행하고 지원 범위 차이를 실측 기록
- 세션 재개는 구현하지 않는다(D07). 재시작 시 "이전 세션을 복원하지 않았다" 표시만 확인한다(A09는 DEFERRED)
- D09(취소·진행 이벤트·동시 실행)는 이 단계가 끝난 뒤 다시 판단한다

## 5. 고정 10문항 비교 실험
- harness-lab을 내려받아 `benchmark/tasks.json`과 로컬 평가 연결 방식, 실제 실행 명령을 **문서로 확인한 뒤** 연결한다. 추정으로 연결하지 않는다
- 기준 측정: easy 2·medium 4·hard 4를 현재 하네스로 실행. 모델·예산·반복 수·코드 버전을 기록
- 가설 하나 선택 — 1단계 실패 기록에서 고른다. 예: 반복 상한 부족, `search_text`가 잘려서 필요한 파일을 못 찾음, 도구 결과가 너무 길어 문맥을 밀어냄
- 변경 후 같은 10문항 재측정. 모델·예산·반복 수·원본 버전 유지하고 차이가 있으면 기록
- 오류·미완료를 분모에서 빼지 않는다. 개발용 채점기 진단과 모델 성능 점수를 구분한다
- 공식 정답이나 채점 코드를 에이전트 입력에 넣지 않는다
- 제출: 원본 결과·CSV·HTML과 구현 소스

## 각 단계의 기록
| 단계 | 관련 요구·검증 ID | 구현할 변경 | 확인한 결과 | 남은 문제 |
|---|---|---|---|---|
| 1 | R01·R02·R03·R05·R06 / A01·A02·A05·A06·A07 | 경로 검사기, 읽기 도구 2개, 반복 루프, JSONL 기록, OpenAI·모의 어댑터, CLI | 구현 완료(2026-09-08). `py -m pytest tests -q` → 33 passed, 1 skipped(symlink 생성 권한 없음, junction 테스트로 대체 검증). 실제 대상 저장소 dry-run 끝-끝 통과, `search_text`가 `.venv`를 가지치기해 14,000여 파일 대신 73파일만 훑음. A02·A05·A06·A07(a) PASS(모의). **실제 모델로 A01·A07(b) 실행 완료(2026-09-08)** — `examples/sample.srt` 요약이 원문과 정확히 대조됐고, 잘못된 키는 재시도 없이 `failed`로 끝남 | CLI 후속 요청 미지원(A08) — 루프는 `history`를 받지만 CLI가 노출하지 않음 |
| 2 | R03 / S01·A/B 비교 | 근거 유효율 검사기, 사례 5~10건 실행 | NOT_RUN | |
| 3 | R04·R05 / A03·A04 | `write_file`, `run_pytest`, 승인 흐름(`approval.py`), `waiting_approval` 상태, `fixtures/spacing_rules/` 결함 코드 | 구현 완료(2026-09-08). `py -m pytest tests -q` → 51 passed, 1 skipped. A03·A04 PASS(모의). **실제 모델 + 비대화 거절(A04)과, 학생이 실제 PowerShell 창에서 직접 `y`/`n`을 입력한 실행(A03)까지 모두 완료.** 실제 터미널에서 diff·명령줄·거절 로그 전부 한글 깨짐 없이 정상 렌더 확인(cp949 인코딩 버그를 여기서 발견해 `harness/__main__.py`에서 UTF-8 재설정으로 수정). 다만 이 실제 시도에서는 모델이 결함을 끝내 못 고쳤고(반복할수록 악화, 11회·164초 만에 completed) 사람이 나빠지는 패치를 중간에 거절함 — 승인 UI·거절 흐름은 실제로 검증됐지만 코딩 성공 자체는 이번 실행에서 미달. 실습 파일은 원래 결함 상태로 복원함 | 대상 저장소에 대한 쓰기는 아직 열지 않음(D05 범위 밖) |
| 4 | R07 / A10 | Ollama 어댑터, provider 전환 | NOT_RUN | |
| 5 | R08 / A11·A12 | agent-terminal-benchmark 연결, 기준·변경 후 측정 | **A11 완료(2026-09-08)**. 준비: `agent-terminal-benchmark-ref/`에 학생용 채점 저장소(v1.0.0, 로컬 평가 v2) 내려받아 `uv sync`, `benchmark_source --prepare`로 원본 10문제 SHA256 대조 성공. 연결: `agent-terminal-benchmark-ref/agent-terminal-benchmark/my_agent.py`를 새로 작성해 `examples/benchmark_agent.py` 계약(`async def solve_task(instruction, workspace, logs_dir, options) -> dict`)대로 내 하네스(`harness/loop.py`의 `run()`)를 `asyncio.to_thread`로 감싸 실제 호출. 실행: `uv run python -m harness_lab.bench --name baseline-own --agent my_agent:solve_task --provider openai --model gpt-4o-mini --max-steps 40 --max-seconds 300` → **10문항 전부 시행, 0/10 통과**(`jobs/baseline-own/`, 리포트 `reports/baseline-own/`). 참조 에이전트(도구 더 많음) 같은 조건 실행은 1/10(`jobs/provided-baseline/`) — 도구가 있으면 최소 일부는 풀린다는 대조군 확보. 0점의 원인은 `write_file`이 새 파일을 만들지 않는다는 D06 그대로의 제약과, 임의 스크립트 실행 도구 부재 — 이 실험 자체가 목적한 "내 하네스가 자기 도메인 밖에서 얼마나 일반화되는가"를 정직하게 보여줌 **A12도 완료(2026-09-08, 2회 반복)**. 1차: 가설(새 파일 생성 허용) 적용 후 재실행(`improved`) → 이진 통과 0/10 그대로, 부분 체크는 4문항에서 증가. sudoku 추적 결과 "쓰기"는 뚫렸지만 "실행" 도구가 없어 산출물이 끝내 안 만들어짐을 확인. 2차: 그 발견에서 나온 다음 가설대로 `harness/tools/run_python.py` 추가(작업 폴더 안 기존 `.py` 파일만 실행, 셸 불가) 후 재실행(`improved2-run-python`) → **이진 통과 0/10 → 1/10**(sudoku 22/22 완전 통과), sokoban 부분 체크 0/12→8/12. 벤치마크 기본 참조 에이전트와 동일 문항·동일 점수 — 도구 격차가 원인이었다는 진단이 실측으로 확정됨 |

설계 변경은 PRD와 인터페이스, 완료 조건에도 반영한다. 코드가 먼저 바뀌어 명세와 충돌했다면 어느 쪽이 사용자 의도에 맞는지 판단한다.
