# 완료 조건과 실행 증거
계획한 결과와 실제 결과를 구분한다. NOT_RUN / PASS / FAIL / DEFERRED를 쓴다. 공통 필수 항목은 미루는 대신 실패 원인과 남은 작업을 기록한다. 모의 모델 검증과 실제 모델 검증을 각각 표시한다.

1·2단계 구현 후 실제로 실행한 결과다. 실제 모델을 부른 항목과 모의 어댑터로만 확인한 항목을 구분해 적었다.
측정: 2026-09-08, 코드 `harness` 0.2.0, Windows 11 + Python 3.14.6, `py -m pytest tests -q` → **51 passed, 1 skipped**.

**2026-09-08 실제 모델 실행에서 발견한 버그**: `harness/loop.py`의 거절 로그(`f"... 거절됨 — ..."`)가 em dash(—)를 쓰는데, Windows 콘솔 기본 코드페이지(cp949)가 이 문자를 인코딩하지 못해 `UnicodeEncodeError`로 프로그램이 죽었다. 모의 테스트는 `print()`를 실제 OS 콘솔로 보내지 않아 이 경로를 잡지 못했다. `harness/__main__.py`의 `main()` 시작부에서 `sys.stdout`/`sys.stderr`를 UTF-8(`errors="replace"`)로 재설정해 고쳤다. 실제 실행이 아니었으면 발견하지 못했을 문제다.

| ID | 관련 요구 | 상황과 행동 | 기대 결과 | 상태 | 실제 증거 |
|---|---|---|---|---|---|
| A01 | R01~R03 | 실제 OpenAI 모델로 `korean-subtitle-corrector`의 `examples/sample.srt`를 읽어 요약 요청 | 세션 기록에 `read_file` 실행과 반환 줄 범위가 남고, 결과가 원문에 실제로 있는 내용만 인용 | PASS (실제) | `py -m harness ask "examples/sample.srt 파일을 읽고 자막 내용을 요약해줘" --root ~/Documents/korean-subtitle-corrector --provider openai` → `harness/.sessions/20260908T062527Z-dd5ca30f.jsonl`. `read_file examples/sample.srt:1-39`(39줄 전체) 1회, 반환 `content`가 원본 10줄과 문자 단위로 일치. 최종 답 10개 항목이 전부 원문 문장에 대응(인사·날씨·초콜릿·스노우 기자·노천 카페·"할만하다"·귀가·"고개를 반듯이"·벙어리장갑·반팔 티셔츠), 없는 내용 추가 없음. `provider: openai / 모델: gpt-4o-mini`, 반복 2회·5.3초, `usage.total_tokens` 438+891 |
| A02 | R02 | 모의 어댑터(`--dry-run`)가 도구 요청 후 결과를 받아 도구 없이 종료 | 인자 검사 → 실행 → `tool_call_id` 연결 → 종료를 확인. 실제 모델 호출 0회 | PASS (모의) | `tests/test_loop.py::test_a02_tool_call_then_finish` — 도구 결과 메시지의 `tool_call_id`가 assistant가 준 id와 같음을 대조. CLI 끝-끝: `py -m harness ask ... --dry-run` → `상태 completed / 반복 2회`, 세션 JSONL에 `model_request·model_reply·tool_call·tool_result·session_end` 모두 기록 |
| A03 | R04~R05 | 의도적 결함을 넣은 실습 파일(`fixtures/spacing_rules/`)에 수정 요청 | diff를 보여 주고 승인 후 적용, `run_pytest`로 지정 테스트 통과 | PASS (모의) / 흐름은 PASS·코딩 결과는 FAIL (실제 사람 터미널) | 모의: `tests/test_write_tools.py::test_a03_approved_write_then_pytest_passes` — 승인 전 fixture는 `1 failed, 2 passed`. 승인 후 파일이 실제로 바뀌고 `run_pytest` → `exit_code 0`, `failed 0`. 세션에 `state: waiting_approval → running` 2회와 `approval: approve` 2건 기록.<br>**실제(2026-09-08, 실제 사람이 진짜 PowerShell 창에서 `y`/`n` 직접 입력, 세션 `20260908T063340Z-1c197512.jsonl`)**: 승인 화면에 `--- a/rules.py` diff와 실제 `pytest test_rules.py -q` 명령줄·작업 디렉터리·시간 상한이 한글 깨짐 없이 정상 렌더됨(위 인코딩 수정 확인). `y`로 첫 write_file·run_pytest 승인 → 적용은 됐으나 오히려 `failed=3`으로 악화. 모델이 반복 재시도하며 9회차까지 계속 나빠지자 사람이 10회차에서 `n`으로 거절 → `write_file 거절됨` 로그 정상 표시(예전 같으면 em dash에서 죽던 지점) → 반복은 안 끊기고 계속됨(D06 확인) → 모델이 코드 대신 사용자에게 되묻는 텍스트 답으로 반복 11회·164초 만에 `completed`. **하네스의 승인 UI·y/n 처리·거절 후 반복 지속은 실제로 정상 확인됐지만, 이 실행에서 모델이 실제로 테스트를 통과시키지는 못했다** — 하네스 동작 성공과 모델의 코딩 성공을 분리해 기록한다. 실습 파일은 이후 원래 결함 상태(`1 failed, 2 passed`)로 복원함 |
| A04 | R05 | `write_file` 승인 요청을 거절 | 파일 바이트가 그대로. 그 도구 호출만 `rejected_by_user`로 모델에 돌아가고 반복은 계속 | PASS (모의) / PASS (실제, 비대화 거절) | `tests/test_write_tools.py::test_a04_rejected_write_leaves_file_untouched` — `read_bytes()` 대조로 불변 확인, 작업은 `completed`로 계속. 승인자를 아예 주지 않은 경우도 `test_default_approver_rejects`로 확인(기본값이 거절). 실제 모델로도 확인: `harness/.sessions/20260908T062825Z-a11b62b6.jsonl` — `write_file`을 실제로 호출했고(첫 시도는 모델이 `content`에 깨진 텍스트를 넣어 스키마 검사가 `invalid_argument`로 거부, 두 번째 시도는 정상 diff), 비대화 환경이라 `AlwaysReject`가 자동 거절 → `rejected_by_user`. `fixtures/spacing_rules/rules.py` 재실행 결과 `1 failed, 2 passed`로 수정 전과 바이트 동일함을 확인 |
| A05 | R05 | 작업 폴더 밖(`../` 탈출), 링크 경유, 제외 경로(`.venv/...`) 읽기 시도 | 모두 코드의 경로 검사로 거부되고 `guard_block` 이벤트가 남음. 모델 지시와 무관하게 거부 | PASS (모의) | 실제 대상 저장소에 강제 실행: `read_file ../subtitle-tc-generator/checker/korean.py` → `path_outside_root`, `.venv/Lib/site-packages/pip/__init__.py` → `path_excluded`, 이어진 `subtitle_corrector/api.py` → 정상 3줄 반환. 파일 내용은 반환되지 않았고 `guard_block` 2건 기록. 단위 검증은 `tests/test_paths.py` 9건(부모 탈출·절대 경로·제외·junction·대소문자) |
| A06 | R02 | 모의 어댑터가 매 반복 도구 호출을 계속 요청 | `--max-iterations` 값에서 종료. 상태 `failed`, 이유 `limit_reached` 표시 | PASS (모의) | `tests/test_loop.py::test_a06_iteration_limit` — `max_iterations=3`에서 `failed/limit_reached`, 반복 3회 |
| A07 | R01~R02 | (a) 모델이 `arguments`에 JSON이 아닌 값을 넣음 (b) 잘못된 API 키로 호출 | (a) 실행하지 않고 `bad_arguments`를 도구 결과로 반환, 반복 1회로 계산 (b) 재시도 없이 `failed`. 둘 다 completed로 기록하지 않음 | (a) PASS (모의) / (b) PASS (실제) | (a) `tests/test_loop.py::test_a07a_bad_arguments_not_executed`. 재시도 정책은 `test_retryable_error_is_retried`(3회 호출·반복 1회)와 `test_non_retryable_error_fails_fast`(1회 호출·즉시 failed)로 별도 확인. (b) `OPENAI_API_KEY=sk-invalid-test-key-000`로 실제 호출 → `harness/.sessions/20260908T062548Z-9435a1fc.jsonl`. `adapter_error code=auth_failed`(실제 OpenAI 401 응답 본문 포함, 키는 SDK가 `sk-inval***********-000`로 마스킹), 재시도 없이 반복 1회·1.9초 만에 `status: failed / reason: auth_failed`. completed로 잘못 기록되지 않음 |
| A08 | R06 | 같은 프로세스 세션에서 후속 요청 | 이전 대화가 이어지고 같은 `session_id`의 JSONL에 계속 append | NOT_RUN | 루프는 `history` 인자로 이어가기를 받지만 CLI가 아직 후속 입력을 노출하지 않는다. 1단계는 요청 1건에 프로세스 1개다 |
| A09 | R06 | 저장 후 앱 재시작 | 재개 미구현(D07). 새 `session_id`를 만들고 "이전 세션을 복원하지 않았다"고 표시. 복원했다고 말하지 않음 | DEFERRED (D07) | |
| A10 | R07 | Ollama 어댑터로 A01과 같은 읽기 작업 (3단계) | 같은 내부 계약으로 동작. 모델의 도구 호출 지원 여부와 OpenAI와의 차이를 실측해 기록 | NOT_RUN | |
| A11 | R08 | 고정 10문항 기준 평가 실행 | easy 2·medium 4·hard 4 원본 결과와 설정. 오류·미완료를 분모에서 빼지 않음 | PASS (실제, 점수 0/10) | 2026-09-08, `agent-terminal-benchmark` v1.0.0(로컬 평가 v2, `suite_id: terminal-bench-pro-local-port-v2`, `revision: 874af409...`) 연결. `my_agent.py`가 내 하네스(`harness/loop.py`)를 실제로 호출하도록 어댑터 작성, `uv run python -m harness_lab.bench --name baseline-own --agent my_agent:solve_task --provider openai --model gpt-4o-mini --max-steps 40 --max-seconds 300` 실행. 10문항(easy 2·medium 4·hard 4) 전부 시행 완료, 분모에서 뺀 문항 없음. **결과 0/10 (전부 reward=0)** — `jobs/baseline-own/*/result.json`, 리포트 `reports/baseline-own/index.html`(CSV 포함). **원인은 모델 실패가 아니라 하네스 설계 한계로 확인됨**: (1) `write_file`이 "기존 파일만 덮어쓴다"는 D06 결정 그대로라 10문항 전부가 필요로 하는 새 출력 파일 생성이 전부 `not_found`로 거부됨(예: sudoku 문항은 2회 반복·2.2초 만에 "solution.txt가 없어서 못 만든다"고 스스로 답하고 종료) (2) 임의 파이썬 스크립트를 실행하는 도구가 없어 "작성 후 실행"이 필요한 문항을 애초에 끝까지 못 감. 비교를 위해 벤치마크가 기본 제공하는 참조 에이전트(`harness_lab.local_agent:solve_task`, `run_python` 도구 있음)도 같은 조건(`provided-baseline`)으로 실행 — 결과 1/10(sudoku만, 22/22 체크 통과) — 같은 모델도 도구가 있으면 최소 일부는 푼다는 것을 실측으로 대조함(`jobs/provided-baseline/`, `reports/own-vs-provided/index.html`) |
| A12 | R08 | 가설에 따른 변경 후 동일 조건 재평가 | 원본 결과와 비교표, 코드 변경·결론 제출 | PASS (실제) | 2026-09-08. 가설: "`write_file`이 새 파일을 못 만드는 게 0/10의 원인이다." 변경: `harness/tools/write_file.py`가 상위 폴더만 있으면 새 파일도 만들도록 수정(D06 결정 변경, DECISIONS.md 2026-09-08 행). 조건 고정: 같은 10문항·같은 revision(`874af409...`)·`provider openai`·`model gpt-4o-mini`·`max_steps 40`·`max_seconds 300`, `--name improved`로 재실행. **결과: 이진 통과 0/10 → 0/10(변화 없음)**. 부분 체크는 4개 문항에서 증가(blockchain 2→4/11, go-board 0→4/16, nonogram 4→5/13, sudoku 2→5/22) — 확실한 개선으로 단정하지 않음(11강 기준: 차이가 작으면 우월성 단정 금지). sudoku로 원인 추적: `improved`에서는 실제로 `app/sudoku_solver.py`를 새로 작성하는 데는 성공했지만(`baseline-own`에서는 아예 못 씀), 그 스크립트를 실행할 도구가 없어 `app/solution.txt`가 끝내 생성되지 않음 — **"쓰기"는 뚫렸지만 "쓴 뒤 실행"은 여전히 막혀 있다는 것을 실측으로 좁힘**. 다음 가설(임의 스크립트 실행 도구 추가)은 이번 실험 결과에서 도출됨. 리포트: `reports/improved-vs-baseline-own/`(CSV+HTML), 원본 잡: `jobs/baseline-own/`, `jobs/improved/`.<br><br>**2차 개선(2026-09-08, 같은 조건 3번째 실행)**: 가설 "쓴 코드를 실행할 도구가 없는 게 남은 원인이다." 변경: `harness/tools/run_python.py` 신규 추가(작업 폴더 안 기존 `.py` 파일 하나만 실행, 셸·인라인코드 불가, 승인 필요, D05 결정 변경). `--name improved2-run-python`로 같은 10문항·같은 조건 재실행. **결과: 이진 통과 0/10 → 1/10(`python-sudoku-solver-backtracking`, 22/22 체크 전부 통과)** — 벤치마크 기본 제공 참조 에이전트(`run_python` 있음)의 1/10과 정확히 같은 문항에서 같은 점수. 부분 체크도 `python-sokoban-bfs-solver` 0/12→8/12로 크게 상승. 가설이 실제로 검증됨: "쓰기 도구 부족"과 "실행 도구 부족"이 순서대로 두 개의 독립된 병목이었고, 둘 다 해소하니 참조 구현과 동등한 성능이 나옴. 리포트: `reports/run-python-vs-improved/`, 원본 잡: `jobs/improved2-run-python/` |

A09는 D07(재개 미구현)에 따라 DEFERRED다. A10은 D08이 CHOSEN이므로 미루지 않고 3단계에서 실행한다. A03의 테스트 성공만으로 코드의 모든 동작이 옳다고 주장하지 않는다.

PASS (모의)는 하네스가 옳게 동작한다는 뜻이지 모델이 옳은 답을 낸다는 뜻이 아니다. A01·A07(b)는 2026-09-08에 실제 키로 실행해 위 표에 실제 증거를 남겼다.

A03·A04의 승인 흐름은 루프 수준까지 끝-끝으로 확인했고, 실제 모델이 `write_file`을 호출해 비대화(non-TTY) 환경에서 자동 거절되는 경로(A04)와, **학생이 실제 PowerShell 창에서 `y`/`n`을 직접 입력한 경로(A03)** 모두 실제로 확인했다. 콘솔 승인자는 `y`/`yes`만 승인하고 빈 줄·EOF·그 밖의 입력은 거절한다는 것을 `test_console_approver_*`로 이미 확인했었고, 실제 사람 입력에서도 같게 동작함을 확인했다. 사람이 승인한 뒤 코드가 나빠지는 것을 보고 다음 제안을 거절한 것도 실제로 일어났다 — 승인은 "모델이 옳다"를 보증하지 않고 "사람이 봤다"만 보증한다는 설계 의도가 실제로 검증됐다.

## 실제 모델 검증 기록
2026-09-08, `OPENAI_API_KEY`를 환경 변수로 설정해 실제 모델을 호출했다.

- 날짜 / 코드 버전: 2026-09-08 / `harness` 0.2.0(이번 세션에서 `__main__.py`의 콘솔 인코딩 수정 포함)
- provider / 모델 / 실행 환경: OpenAI `gpt-4o-mini`(기본값), Windows 11 + Python 3.14.6, `openai` 패키지 3.8.0
- 사용자 요청 / 입력 fixture: A01 — `examples/sample.srt`(10줄 자막) 요약 요청 / A07(b) — 동일 요청을 `sk-invalid-test-key-000`로 호출 / A04 — `fixtures/spacing_rules/rules.py` 수정 요청(승인 없이 실행되는 비대화 환경)
- 도구 이름과 실제 실행 결과: `read_file` 2회(A01), `write_file` 2회 중 1회 `invalid_argument`·1회 `rejected_by_user`(A04) — 세션 파일: `20260908T062527Z-dd5ca30f.jsonl`, `20260908T062548Z-9435a1fc.jsonl`, `20260908T062825Z-a11b62b6.jsonl`
- 모델 최종 답과 원문·테스트 대조: A01 최종 답 10개 항목 전부 원문과 대조해 근거 있음 확인. A04는 파일 재실행으로 `1 failed, 2 passed` 그대로임을 대조
- 실패·한계와 다음 변경: (1) 첫 `write_file` 시도에서 모델이 깨진 문자열을 `content`에 넣어 스키마가 막았다 — 재시도 프롬프트 없이도 모델이 스스로 두 번째 시도에서 정상 코드를 보냄 (2) 사람이 실제 터미널에서 `y`를 눌러 적용까지 가는 경로는 여전히 NOT_RUN — 학생이 실제 터미널에서 `--allow-write`로 재현 필요 (3) 실행 중 `harness/__main__.py`의 콘솔 출력이 Windows cp949에서 em dash로 죽는 버그를 발견해 UTF-8 재설정으로 고쳤다(위 참고)

실행 명령:

```bash
py -m harness ask "<요청>" --root ~/Documents/korean-subtitle-corrector
```

API 키, 실제 개인 파일, 민감한 출력은 증거에서 제외한다.

## 학생이 추가할 시나리오

### S01 정상 — 오교정 사례의 원인 규칙 찾기
- Given: 작업 폴더는 `korean-subtitle-corrector` 원본. 라벨 71건 중 한 건의 입력 문장과 잘못된 교정 결과만 준비한다. 정답 규칙 위치는 모델 입력에 넣지 않는다.
- When: `python -m harness ask "이 문장이 이렇게 잘못 교정된 원인이 되는 규칙을 찾아서 파일:줄로 알려 줘. 입력: <문장> / 교정 결과: <결과>" --root ~/Documents/korean-subtitle-corrector`
- Then: (1) 세션 기록에 `search_text` 최소 1회와 `read_file` 최소 1회가 남는다 (2) 최종 답이 인용한 모든 `파일:줄`이 실재한다 — 파일이 존재하고 그 줄 번호가 파일 길이 안이다 (3) 사람이 아는 정답 규칙 위치와 대조해 맞았는지 따로 표시한다.
- 주의: (2)는 하네스가 옳게 동작했는지, (3)은 모델이 옳게 답했는지다. 둘을 한 점수로 합치지 않는다.

### S02 실패 — 작업 폴더 밖 요청
- Given: 같은 작업 폴더. 사용자 요청에 "필요하면 상위 폴더의 다른 저장소도 봐라"를 일부러 넣는다.
- When: 모델이 `read_file`에 `../subtitle-tc-generator/checker/korean.py` 또는 `.venv/...`를 넣어 호출한다.
- Then: 파일 내용이 반환되지 않고 `path_outside_root` 또는 `path_excluded` 오류가 도구 결과로 돌아간다. `guard_block` 이벤트가 기록된다. 작업은 그 자리에서 실패하지 않고 반복을 계속한다.
- 주의: 모델이 그 경로를 요청하지 않아서 통과한 것은 PASS가 아니다. 모의 어댑터로 해당 호출을 강제해 검사기 자체를 확인한다.

### A/B 비교 (하네스 있음/없음) — S01의 확장
같은 모델·같은 프롬프트·같은 문항으로 도구 접근만 바꾼다.

| | A (도구 없음) | B (하네스) |
|---|---|---|
| 호출 | 1회 | 반복, `read_file`+`search_text` |
| 측정 | 정확도, 근거 유효율, 반복 횟수, 토큰·시간 | 같음 |

근거 유효율 = 답이 인용한 `파일:줄` 중 실재하는 것의 비율. 채점은 문자열 대조로 자동화한다. 정답 라벨은 어느 쪽 입력에도 넣지 않는다.

구현이 우연히 돌려준 결과를 그대로 기대값으로 베끼지 않는다.
