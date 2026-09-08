# 하네스 구현과 실험 보고서

## 제품과 구현
- 사용자 시나리오 / 완성한 PRD 위치: 한국어 자막 교정기(`korean-subtitle-corrector`) 개발자가 실사용 오교정 사례의 원인 규칙을 `파일:줄` 근거와 함께 분류. [PRD.md](PRD.md), D01(DECISIONS.md)
- 구현 언어와 실행 방법: Python 3.14(개발/테스트), CLI. `py -m pip install -r requirements.txt` 후 `py -m harness ask "<요청>" --root <작업폴더>` ([README.md](README.md) "실행 방법" 절)
- 직접 작성하거나 변경한 부분 / 참고한 부분: `harness/` 전체(계약·경로검사·도구 4종·반복루프·세션기록·OpenAI/모의 어댑터·CLI)를 직접 작성. 참고 구현(`agent-terminal-benchmark`의 `harness_lab/*`, `harness-lab`의 `harness_lab/*`)은 9강에서 파일 단위 비교 대상으로만 읽었고, 코드를 그대로 가져오지 않았다. 벤치마크 연결용 `my_agent.py`(`agent-terminal-benchmark-ref/agent-terminal-benchmark/my_agent.py`)만 그 저장소의 `examples/benchmark_agent.py` 계약에 맞춰 새로 작성.
- 모델·도구 반복, 오류·종료, 권한, 세션의 코드 위치: 반복 루프 [harness/loop.py](harness/loop.py), 내부 계약 [harness/contracts.py](harness/contracts.py), 경로 검사 [harness/paths.py](harness/paths.py), 승인 [harness/approval.py](harness/approval.py), 도구 [harness/tools/](harness/tools), 세션 기록 [harness/session.py](harness/session.py), CLI [harness/__main__.py](harness/__main__.py)
- Python 예시와 다른 설계 결정 및 이유: (1) 동기 실행 — 참고 구현은 `asyncio` 기반, 내 하네스는 동기 함수 하나(`loop.run`)로 반복을 구현(D02 CLI 범위에서 비동기가 필요하지 않다고 판단). (2) 도구는 D01의 실제 도메인(자막 교정기 오교정 원인 추적)에 필요한 만큼만 최소로 시작(`read_file`/`search_text`/`write_file`/`run_pytest`) — 범용 실행 도구는 처음부터 넣지 않았다. 이 선택이 R08 벤치마크에서 실제로 한계를 드러냈고(아래 실패 분석), 그 실측 결과에 따라 `run_python`(작업 폴더 안 기존 `.py` 파일 실행 전용, 셸 불가)을 나중에 추가했다.

## 사용자 요구 충족 검증
D01(PRD.md·DECISIONS.md)의 사용자 요구: "한국어 자막 교정기 개발자가 오교정 사례의 원인 규칙을 `파일:줄` 근거와 함께 찾고 싶다", "제안된 코드 변경을 승인·거절할 수 있고 거절하면 파일이 그대로여야 한다". 아래는 계획한 기능과 실제 실행 결과를 나란히 대조한 것이다(전체 근거는 [ACCEPTANCE.md](ACCEPTANCE.md)).

| 계획한 기능 | 사용자 요구 | 실제 실행 결과(실제 모델·실제 터미널) | 충족 여부 |
|---|---|---|---|
| `read_file`로 실제 자료를 읽고 답함 | "추측하지 말고 실제로 읽은 근거로 답해라" | A01: `examples/sample.srt`(10줄) 요약 요청 → `read_file` 1회 실행, 반환된 `content`가 원본과 문자 단위로 일치, 최종 답 10개 항목 전부 원문 문장에 대응, 없는 내용 추가 없음(`evidence_sessions/20260908T062527Z-dd5ca30f.jsonl`) | 충족 |
| 잘못된 요청·인증 실패를 성공으로 위장하지 않음 | "실패는 실패로, 완료로 잘못 표시하지 마라" | A07(b): 가짜 API 키로 호출 → 재시도 없이 1.9초 만에 `status: failed / reason: auth_failed`, `completed`로 오기록되지 않음 | 충족 |
| 승인 후 코드 변경·테스트 실행 | "제안을 보고 승인/거절을 사람이 직접 결정" | A03: **실제 PowerShell 창에서 사람이 직접 `y`/`n` 입력**. diff·실제 명령줄·시간 상한이 화면에 정상 렌더(한글 깨짐 없음), 승인 후 적용됨, 거절 후 반복은 계속되고 파일은 불변 확인 | 충족(승인 UI·거절 흐름 자체는 실증됨). 단, 이 특정 세션에서 모델이 실제로 결함을 다 고치지는 못함 — **하네스 동작과 모델의 코딩 성공을 분리해 기록**(ACCEPTANCE.md A03 실제 항목) |
| 재시작 시 이전 세션을 복원하지 않았다고 표시 | D07: 세션 재개는 범위 밖, 그렇다고 거짓 안내는 안 함 | 실행할 때마다 "이전 세션을 복원하지 않았습니다" 문구가 실제로 출력됨(CLI 실행 로그 확인) | 충족 |
| **핵심 요구 — 오교정 사례의 원인 규칙을 실제로 찾음(S01)** | D01: "오교정 사례가 어느 규칙 탓인지 `파일:줄` 근거와 함께 분류하고 싶다" | **제출 후 실제 실행(2026-09-08)**: 라벨 71건을 실제 엔진에 돌려 진짜 실패 사례(w02, "국어공부 했어"→"국어공부했어" 오교정) 11건 중 하나를 뽑아 그대로 물어봄. 하네스는 `search_text`·`read_file`로 실재하는 `tests/test_josa_affix.py:234`를 인용, 그 안의 설명은 진짜 원인(사전 신호로 못 가르는 명사쌍이라 자동화를 의도적으로 보류함, `docs/BACKLOG.md`·`docs/IMPLEMENTATION_LOG.md`에 문서화)과 **내용상 일치**했다. 다만 인용한 위치는 그 설명이 적힌 **테스트 파일**이었고, 실제로 그 판단을 수행하는 **엔진 코드**(`affix.py`)는 아니었다 | **부분 충족 — 엄격 기준으로는 미충족(FAIL)**. 근거: [ACCEPTANCE.md](ACCEPTANCE.md) S01, 세션 [evidence_sessions/20260908T083416Z-553a604d.jsonl](evidence_sessions/20260908T083416Z-553a604d.jsonl) |

한계로 남긴 것: A08(같은 세션 후속 요청, CLI 미노출), A10(Ollama 어댑터, D08 CHOSEN이지만 미실행)은 NOT_RUN으로 정직하게 남겼다. **위 S01 결과가 이 제품의 가장 중요한 검증이다** — A01(단순 읽기·요약)이 잘 됐다고 "오교정 원인 찾기"까지 잘 된다고 넘겨짚었던 것은 앞선 대화에서의 착오였고, 실제로 돌려 보니 하네스 동작은 정직했지만(지어낸 근거 없음) 모델이 문자열 그대로만 검색해 테스트 코드로 새는 한계가 드러났다. 벤치마크(R08) 결과는 이 제품 요구의 충족 여부와는 별개다.

## 평가 조건
- 원본 commit / subset ID / manifest SHA256: `revision 874af409da6aafebccbf3bc5bb41a2fa4d78784d`, `suite_id terminal-bench-pro-local-port-v2`(로컬 평가 v2), `manifest_sha256 21f333a94929d6ce9cf0e184a8865ed5d5feca1cc33b3c6536b771ae2edb30a6` (기준·개선 두 실행 모두 동일 — `jobs/*/run-metadata.json`)
- 제공자와 모델의 실제 이름: OpenAI `gpt-4o-mini`
- 코드 commit 또는 소스 SHA256 (기준 / 개선1 / 개선2): **알려진 한계** — `run-metadata.json`의 `code_sha256`은 `my_agent.py`(연결 어댑터)만 해시하고, 실제로 반복을 수행하는 `harness/` 패키지는 이 벤치마크 프로젝트 밖에서 절대경로로 import돼 해시 추적 대상에 안 잡힌다. 그래서 세 실행의 `code_sha256`이 전부 같게 찍혀 있는데(`d1d2323f...`), 실제로는 그 사이에 `harness/tools/write_file.py`를 고치고 `harness/tools/run_python.py`를 새로 추가했다. 진짜 버전 구분은 `harness/__init__.py`의 `__version__`으로 남긴다 — 기준 `0.2.0`(기존 파일만 덮어씀), 개선1 `0.3.0`(새 파일 생성 허용), 개선2 `0.4.0`(`run_python` 추가, DECISIONS.md 2026-09-08 행 2개).
- 실행 환경 / 아키텍처 / Python 버전 / 로컬 이식판 버전: Windows-11-10.0.26200-SP0, `python_version 3.13.14`(agent-terminal-benchmark의 uv 가상환경 — 내 하네스 자체 개발·`pytest` 검증은 Python 3.14.6에서 함, 두 버전 모두에서 회귀 없음), `port_version 2.0.0`
- 의존성 잠금 파일, 로컬 실행 조건과 재현 제약: 하네스 자체는 `requirements.txt`(`openai>=1.40`, `pytest>=8.0`). 벤치마크 연결부는 `agent-terminal-benchmark-ref/agent-terminal-benchmark/uv.lock`(uv 관리). `my_agent.py`가 `harness` 패키지를 절대경로(`C:\Users\user\Documents\harness-design-kit`)로 import하므로 이 경로 그대로가 아니면 재현 시 그 경로를 맞춰야 한다.
- 문항 수 10 / easy 2 / medium 4 / hard 4 / 문항당 반복 수: 10개 전부, `--attempts 1`(반복 없음, pass@k 아님)
- 모델 호출·도구·시간·출력 한도: `max_steps 40`(내 하네스의 `--max-iterations`에 대응), `max_seconds 300`, `command_timeout 10`, `max_output_tokens 10000`
- 기준 실행 폴더 / 개선 실행 폴더: `agent-terminal-benchmark-ref/agent-terminal-benchmark/jobs/baseline-own/`, `.../jobs/improved/`, `.../jobs/improved2-run-python/` (참고용 대조군 `.../jobs/provided-baseline/` — 벤치마크 기본 제공 참조 에이전트, `run_python` 도구 있음)
- 설치·문제 준비·채점 경로 확인 결과 (개발 진단은 학생 점수에서 제외): `uv sync --locked` 성공. `benchmark_source --prepare`로 원본 10문제 SHA256 전부 대조 통과. 저장소 자체 개발용 단위테스트(`uv run python -m pytest -q`)는 69 passed·15 failed·10 error — 전부 Windows cp949 기본 인코딩(`Path.read_text()`에 encoding 미지정)과 symlink 생성 권한 문제로, 실제 채점에 쓰는 `harness_lab/grading.py`는 `encoding="utf-8"`을 명시해 이 문제와 무관함을 코드로 직접 확인. 이 개발 진단은 아래 학생 점수에 포함하지 않았다.

## 결과
이 저장소에 포함한 근거: [benchmark_results/](benchmark_results/)(문항별 `result.json`, 실행별 `run-metadata.json`, 집계 `trials.csv`·`report.json`·`index.html`). 전체 원본 실행 기록(에이전트 세션 로그, verifier 전체 출력, 워크스페이스 덤프)은 로컬의 `agent-terminal-benchmark-ref/agent-terminal-benchmark/jobs/`에 있으나, 원본 upstream 문제·정답·채점 코드가 섞여 있어 이 저장소에는 포함하지 않았다(`.gitignore` 처리, `benchmark_results/README.md`에 제외 이유 기록).

| 측정 | 통과/전체 시도 | 쉬움(2) | 중간(4) | 어려움(4) | 실패 | 실행 오류 | 미완료 | 시간(합) | 토큰 | 비용 |
|---|---|---|---|---|---|---|---|---|---|---|
| 기준(baseline-own, v0.2.0) | 0/10 | 0/2 | 0/4 | 0/4 | 10 | 0 | 0 | 53.4초 | 알 수 없음(하네스가 호출당 토큰을 상위 지표로 집계하지 않음) | 알 수 없음 |
| 개선1(improved, v0.3.0 — 새 파일 생성 허용) | 0/10 | 0/2 | 0/4 | 0/4 | 10 | 0 | 0 | 66.0초 | 알 수 없음 | 알 수 없음 |
| 개선2(improved2-run-python, v0.4.0 — `run_python` 추가) | **1/10** | 1/2(sudoku) | 0/4 | 0/4 | 9 | 0 | 0 | 82.8초 | 알 수 없음 | 알 수 없음 |
| (참고) provided-baseline — 벤치마크 기본 제공 참조 에이전트, `run_python` 있음 | 1/10 | 1/2(sudoku) | 0/4 | 0/4 | 9 | 0 | 0 | 437.0초 | 세션별 `usage.total_tokens` 기록됨(상위 집계는 별도 계산 필요) | 알 수 없음 |

개선1(새 파일 허용)은 이진 통과를 못 움직였지만(0/10 그대로), 부분 체크는 4개 문항에서 늘었다 — `detect-corrupted-blockchain-transaction` 2/11→4/11, `implement-go-board-analyzer` 0/16→4/16, `implement-nonogram-puzzle-solver` 4/13→5/13, `python-sudoku-solver-backtracking` 2/22→5/22.

개선2(`run_python` 추가)에서 처음으로 이진 통과가 나왔다 — `python-sudoku-solver-backtracking`이 **22/22 전부 통과**(참조 에이전트와 정확히 같은 문항, 같은 만점). `python-sokoban-bfs-solver`는 완전 통과는 아니지만 부분 체크가 0/12→8/12로 크게 올랐다. 나머지 8문항은 여전히 0점 — "쓰기+실행"만으로는 부족하고 알고리즘 정확성이나 출력 형식 같은 더 어려운 요구가 남아 있는 문항들이다.

세 실행 모두 오류(error)나 미완료(pending) 시행은 없었다 — 10문항 전부 하네스가 `completed` 상태로 끝냈고, 분모에서 뺀 문항도 없다.

## 실패 분석과 개선 가설
- 대표 실패의 요청 / 관찰한 도구 실행 / 채점 결과: `python-sudoku-solver-backtracking` — "app/puzzle.txt의 스도쿠를 풀어 app/solution.txt에 써라." 기준 실행에서는 `write_file`이 `{"path": "app/solution.txt", ...}`를 `not_found`로 거부, 모델이 2회 반복·2.2초 만에 "solution.txt가 없어서 못 만든다"고 답하고 종료(`jobs/baseline-own/python-sudoku-solver-backtracking__1/agent.../trial.json`). 채점 결과 22개 검사 중 2개만 통과.
- 추정 원인과 이를 뒷받침하는 기록: `harness/tools/write_file.py`의 "기존 파일만 덮어쓴다"는 제약(D06)이 원인. 이 저장소의 10문항 전부가 새 산출물 파일(솔루션·변환 결과·복구된 자격증명 등)을 만들어야 하는데, 그 첫 걸음부터 막히므로 반복이 길게 이어지지 못하고 짧게(대부분 2~4회) 끝남 — `jobs/baseline-own/*/agent/sessions/trial.json`에서 공통적으로 관찰됨.
- 변경한 한 가지 요소: `harness/tools/write_file.py`가 "상위 폴더만 있으면 새 파일도 생성"하도록 수정(파일 없음/빈 파일을 다른 해시로 구별해 `stale_approval` 판정도 함께 갱신). 새 디렉터리 생성은 여전히 막음(`parent_missing`). 그 외 프롬프트·모델·한도·문제 목록은 전혀 바꾸지 않음.
- 예상한 영향: 최소 일부 문항(특히 sudoku처럼 "스크립트 작성만으로 부분 점수가 있는" 유형)에서 이진 통과 또는 부분 점수가 오를 것으로 예상.
- 실제 변화 (좋아진 문제와 나빠진 문제 모두): 이진 통과는 0/10 그대로. 부분 체크는 4개 문항에서 상승(위 표), 6개 문항은 변화 없음, **나빠진 문항은 없음**. sudoku를 세션 기록으로 추적한 결과, 개선 실행에서는 실제로 `app/sudoku_solver.py`를 새로 작성하는 데 성공했지만(기준 실행에서는 시도조차 못함), 그 스크립트를 실행해 `app/solution.txt`를 만들 도구가 없어 최종 산출물은 끝내 생성되지 않았다 — "쓰기"라는 병목은 풀렸고 "실행"이라는 다음 병목이 남아 있음을 확인했다.
- 동일하게 유지한 조건 / 바뀐 조건: 동일 — 10문항 목록·`revision`·`provider`·`model`·`max_steps`·`max_seconds`·`command_timeout`·`max_output_tokens`. 바뀐 것은 `harness/tools/write_file.py`의 새 파일 생성 허용 여부 하나뿐(`__version__ 0.2.0→0.3.0`).
- 결론과 다음 실험(1차): 가설은 부분적으로 뒷받침됐다(쓰기 병목은 실제로 풀림) but 이진 점수를 움직이기엔 불충분했다 — 원인은 "쓴 코드를 실행할 도구 부재"라는 두 번째, 더 근본적인 병목이다.

### 2차 개선: run_python 추가
- 변경한 한 가지 요소: `harness/tools/run_python.py` 신규 추가 — 작업 폴더 안에 이미 있는 `.py` 파일 하나만, 인자는 문자열 배열로, 셸을 거치지 않고 실행. 인라인 코드나 임의 명령은 받지 않음(D05 결정 변경). 그 외 조건(10문항·`revision`·`provider`·`model`·`max_steps`·`max_seconds`)은 1차와 완전히 동일.
- 예상한 영향: 최소 sudoku처럼 "스크립트 작성→실행→파일 출력"이 전부인 단순한 문항에서 이진 통과가 나올 것으로 예상.
- 실제 변화(좋아진 점과 나빠진 점 모두): 예상대로 sudoku가 **처음으로 완전 통과**(22/22, 개선1의 5/22에서 큰 폭 상승)했고, sokoban도 부분 체크가 크게 올랐다(0/12→8/12). 반면 **`implement-go-board-analyzer`는 4/16→3/16**, **`implement-nonogram-puzzle-solver`는 5/13→4/13**로 각각 1개씩 부분 체크가 줄었다 — 나빠진 점도 실제로 있었다. 다만 이 두 문항은 `run_python`을 아예 안 쓰거나 거의 안 썼고(반복 횟수·소요 시간이 개선1 대비 크게 다름 — go-board는 4회→2회로 줄고, nonogram은 3회→12회로 늘었다), 코드 변경과 직접 연결되는 증거가 없다. `--attempts 1`(한 번씩만 실행)이라 gpt-4o-mini의 응답 편차(같은 프롬프트에도 매번 다르게 답하는 것)와 실제 코드 변경의 효과를 이 두 문항에서는 분리할 수 없다는 한계로 남긴다 — 반복 시행(`--attempts 3` 이상)을 안 하면 원래 못 가르는 차이다. 나머지 6문항은 변화 없음. run_python 하나로는 "복잡한 알고리즘 정확성"이나 "엄격한 출력 형식" 같은 남은 요구까지 해결하지 못한다는 것도 함께 드러났다.
- 결론과 다음 실험: 이번 가설은 완전히 검증됐다 — "쓰기 부재"와 "실행 부재"가 순서대로 두 개의 독립된 병목이었고, 참조 에이전트(1/10, 같은 문항 sudoku)와 정확히 같은 지점까지 따라잡았다. 다음 실험 가설(이번 제출 범위 밖으로 남김): 알고리즘이 복잡한 문항(depgraph, lz77, csv-converter)의 세션 기록을 보고 "출력 형식 검증"이나 "다단계 계획" 쪽의 병목을 새로 찾는 것. 이 10문항은 개선 판단에 이미 쓰인 개발용 집합이므로, 이번에 관찰한 개선을 처음 보는 문제로 일반화하지 않는다.

## 제출 확인
- [x] 실행 가능한 소스와 잠금 파일, 실행 안내 — `harness/`, `requirements.txt`, [README.md](README.md)
- [x] PRD·결정 기록·인터페이스·완료 조건 — [PRD.md](PRD.md), [DECISIONS.md](DECISIONS.md), [INTERFACES.md](INTERFACES.md), [ACCEPTANCE.md](ACCEPTANCE.md)
- [x] 기준/개선의 설정, run-metadata.json, 문항별 result.json — [benchmark_results/jobs/](benchmark_results/jobs)
- [x] 실행들의 10문항 결과 CSV·JSON·HTML — [benchmark_results/reports/](benchmark_results/reports)
- [x] 개선 가설, 구현 변경과 관찰 결과 — 위 "실패 분석과 개선 가설", [DECISIONS.md](DECISIONS.md) 2026-09-08 행
- [x] 키·토큰·개인 자료 제외 — `openai_key.env`는 `.gitignore` 처리, 세션 기록에 키 값 기록 안 함(코드로 보장, `tests/`로 검증)

## 로컬 이식과 검증 범위

- 난이도 출처: 고정 upstream `task.toml`(`benchmark/tasks.json`, easy 2 / medium 4 / hard 4) — 수업이나 내가 임의로 붙인 난도가 아니다.
- 실행 방식: local-port(`terminal-bench-pro-local-port-v2`, `port_version 2.0.0`), Docker 미사용
- OS·CPU·메모리와 동시 실행 프로그램: Windows 11(10.0.26200), CPU/메모리 제한 없음(`hostlimits: unrestricted` — 이건 OS 자원 제한을 걸었다는 뜻이 아니라 안 걸었다는 뜻). 실행 중 다른 무거운 프로그램 동시 실행 여부는 별도로 통제하지 않음.
- 원본 대비 변경: 원본 컨테이너의 `/app`, `/protected` 등 절대경로를 시행별 작업 폴더 상대경로로 치환. 현재 Python 실행 파일 사용. 스도쿠 I/O 계약 공개, 블록체인 원본 입력 기반 정답 검증 등 로컬 평가 v2의 정정 사항 그대로 적용됨(`local_corrections` 필드).
- 채점기 제약 또는 원본 검사 오류가 결과에 미친 영향: 관찰된 바 없음 — 채점 실행 자체(exit_code, verifier 실행)는 10개 시행 모두 정상 완료됐고, 낮은 점수는 에이전트가 산출물을 못 만든 것이지 채점기 실행 실패가 아니었다.
- 다른 운영체제에서 실제 실행했는지: 아니오. Windows 11 한 환경에서만 실행했다.

공식 컨테이너 점수나 전체 벤치마크 점수로 표현하지 않는다. 기준·개선의 소스 사본과 환경 조건은 위에 기록한 대로다.
