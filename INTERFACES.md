# 인터페이스 계약
상태: 1단계(읽기 전용) 확정, 2단계(쓰기·pytest)와 3단계(Ollama) 예정. D01~D08·D10 선택에 맞춰 채웠다. API는 프로그램 사이의 약속이며 HTTP만 뜻하지 않는다.

확정된 전제: Python CLI(D02·D03), OpenAI 어댑터 우선 후 Ollama 추가(D04·D08), 작업 폴더는 `korean-subtitle-corrector` 원본 한 곳(D05), 쓰기·실행만 건별 승인(D06), 세션 JSONL 기록·재개 없음(D07), 하네스 소스는 이 저장소 `harness/`(D10).

## 제품의 작업 계약
| 동작 | 입력에서 정할 것 | 출력에서 정할 것 | 오류·경계 |
|---|---|---|---|
| 작업 시작 | 자연어 요청 문자열, 작업 폴더 경로, provider·모델, 반복 상한 | `task_id`, `session_id`, 최초 상태 `queued` | 빈 요청은 사용법 오류로 종료. 없는 폴더·파일이 아닌 경로는 시작 전에 거부. 1단계는 한 프로세스가 한 작업만 다루므로 중복 요청이 발생하지 않는다 |
| 상태 조회 | `task_id` | 현재 상태, 지금까지의 반복 횟수, 도구 호출 내역, 결과 또는 오류 | 없는 `task_id`는 조회 실패. 1단계는 세션이 프로세스 수명과 같아 다른 세션의 작업을 조회할 경로가 없다 |
| 변경 승인/거절 | `task_id`, `approval_id`, 표시한 변경의 해시, `approve`/`reject` | 결정 반영 결과와 실제 적용 여부 | 2단계에서 구현. 해시가 다르면 만료로 보고 재사용하지 않는다 |
| 결과 조회 | `task_id` | 모델 최종 답, 인용한 `파일:줄` 근거, 도구 실행 기록 | 반복 상한이나 오류로 끝난 작업은 `failed`로 표시하고 부분 결과에 미완료 표시를 붙인다 |
| 세션 이어가기 | — | — | 미지원(D07). 재시작하면 새 `session_id`를 만들고 "이전 세션을 복원하지 않았다"고 표시한다 |

작업 상태: `queued → running → completed` 또는 `queued → running → failed`. 승인이 필요한 도구에서는 `running → waiting_approval → running`을 거치며 `state` 이벤트로 기록한다(2단계 구현됨). `cancelled`는 D09와 함께 미룬다.
거절 이후 정책: 거절은 그 도구 호출 하나만 실패로 모델에 돌려주고 반복은 계속한다. 작업 전체를 실패로 끝내지 않는다.
승인은 특정 작업의 특정 도구 입력에 연결한다. 사용자가 본 내용이 바뀌면 그 승인을 재사용하지 않는다.

### 구체적 계약 한 개 — `read_file`
- 이름: `read_file`
- 입력 타입과 허용 범위: `path` 문자열(작업 폴더 기준 상대 경로), `start_line` 정수 1 이상 기본 1, `max_lines` 정수 1~500 기본 200
- 정상 입력 예: `{"path": "subtitle_corrector/engine/spacing.py", "start_line": 1, "max_lines": 80}`
- 정상 출력 예: `{"path": "subtitle_corrector/engine/spacing.py", "start_line": 1, "end_line": 80, "total_lines": 412, "truncated": true, "content": "..."}`
- 잘못된 입력과 오류 출력 예:
  - 경로 이탈 `{"path": "../../.ssh/id_rsa"}` → `{"error": "path_outside_root", "message": "작업 폴더 밖의 경로입니다", "root": "<작업 폴더>"}`
  - 제외 경로 `{"path": ".venv/lib/site-packages/x.py"}` → `{"error": "path_excluded", "message": "제외 패턴에 걸린 경로입니다", "pattern": ".venv"}`
  - 없는 파일 → `{"error": "not_found"}`
  - 디렉터리 지정 → `{"error": "not_a_file"}`
  - `max_lines` 범위 밖 → `{"error": "invalid_argument", "field": "max_lines"}`
- 상태 변화/부작용: 없음. 읽기 전용이며 파일을 수정하지 않는다
- 재시도·중복 요청 정책: 같은 인자를 다시 부르면 같은 결과를 돌려준다. 모델이 동일 인자를 3회 연속 호출하면 반복 없는 진행으로 보고 그 사실을 결과에 덧붙여 돌려준다

빈 파일과 못 찾은 파일은 구별된다: 빈 파일은 `content: ""`를 담은 성공 결과(최상위에 `error` 키 없음)이고, 없는 파일은 `{"error": "not_found"}`(최상위에 `content` 키 없음)다. 두 경우가 같은 모양으로 반환되지 않아 모델이 "빈 파일을 읽었다"와 "파일이 없다"를 혼동하지 않는다.

오류는 예외로 던지지 않고 위 구조로 모델에게 도구 결과로 돌려준다. 모델이 스스로 고쳐 다시 시도할 수 있어야 하기 때문이다. 단 경로 이탈·제외 경로는 별도로 세션 기록에 남긴다.
나머지 도구에도 같은 틀을 적용한다. API의 모든 필드를 모델의 자연어 판단에 맡기지 않는다.

## UI와 통신 매핑
- 선택한 방식: CLI (D02). 로컬 웹 서버는 추가하지 않는다
- 명령 또는 HTTP 경로와 계약의 대응:

| 명령 | 대응 계약 |
|---|---|
| `python -m harness ask "<요청>" --root <경로>` | 작업 시작 → 반복 → 결과 조회까지 한 번에 |
| `python -m harness ask ... --provider openai\|ollama --model <이름>` | provider 선택(D04·D08) |
| `python -m harness ask ... --max-iterations N --max-seconds S` | 반복·시간 상한(R02) |
| `python -m harness ask ... --dry-run` | 모의 어댑터로 실행, 실제 모델 호출 없음 |
| `python -m harness ask ... --allow-write` | `write_file`·`run_pytest`를 등록한다. 없으면 읽기 도구 둘만 등록된다 |
| `python -m harness show <session_id>` | 저장된 세션 기록 조회 |

- 진행 결과를 보여 줄 방식: 반복마다 한 줄로 `[3/20] read_file subtitle_corrector/engine/spacing.py:1-80 (412줄 중)`. 종료 시 최종 답과 근거 목록, 그리고 상태·반복 횟수·세션 파일 경로를 출력한다
- 종료 코드: `0` completed, `1` failed(반복 상한·모델 오류·도구 연속 실패), `2` 사용법 오류

## 모델 제공자 연결부
내부 계약(제공자와 무관한 타입):

| 타입 | 필드 |
|---|---|
| `Message` | `role` (`system`/`user`/`assistant`/`tool`), `content` (문자열 또는 없음), `tool_calls` (assistant일 때), `tool_call_id` (tool일 때) |
| `ToolSpec` | `name`, `description`, `parameters` (JSON Schema) |
| `ToolCall` | `id`, `name`, `arguments` (dict) |
| `ModelReply` | `text`, `tool_calls` (0개 이상), `finish_reason`, `usage` |

어댑터는 `complete(messages: list[Message], tools: list[ToolSpec]) -> ModelReply` 하나만 노출한다. 하네스 루프는 어떤 제공자인지 모른 채 이 함수만 부른다.

- 첫 제공자/모델: OpenAI. 구체 모델명은 첫 실행에서 실측해 ACCEPTANCE.md의 실제 모델 검증 기록에 적는다
- 사용 API와 공식 문서: OpenAI Chat Completions의 tools/tool_calls. 구현 직전에 현재 문서를 확인하고 확인 날짜를 기록한다
- 도구 호출·결과 연결에 필요한 식별자 처리: 제공자가 준 `tool_call.id`를 그대로 보관했다가 도구 결과 메시지의 `tool_call_id`로 되돌려 준다. 하네스가 새로 만들지 않는다. Ollama가 id를 주지 않으면 어댑터가 자체 id를 만들고 그 사실을 기록한다
- 일반 답과 도구 호출, 여러 도구 요청의 처리 순서: `tool_calls`가 비어 있으면 최종 답으로 보고 종료한다. 여러 개면 받은 순서대로 하나씩 실행하고, 각각의 결과를 별도 `tool` 메시지로 붙여 한 번에 다음 요청을 보낸다. 하나가 실패해도 나머지를 실행한다
- 지원하지 않는 기능, 파싱 실패, 네트워크 오류:
  - 모델이 도구 호출을 지원하지 않으면 시작 시 확인하고 `failed`로 끝낸다. 자연어에서 도구 요청을 추측해 실행하지 않는다
  - `arguments`가 JSON이 아니면 실행하지 않고 `{"error": "bad_arguments"}`를 도구 결과로 돌려준다. 이것은 반복 1회로 센다
  - 네트워크·5xx 오류는 지수 백오프로 최대 3회 재시도한다. 4xx와 인증 오류는 재시도하지 않는다
- 제한 횟수/시간과 재시도 대상: 반복 상한 기본 20회, 전체 시간 상한 기본 300초. 상한에 걸리면 `failed`와 함께 `limit_reached` 이유를 표시한다. 재시도 대상은 위의 네트워크·5xx뿐이며 재시도는 반복 횟수에 넣지 않는다

OpenAI와 Ollama에 같은 필드를 보내면 언제나 같은 기능이 동작한다고 가정하지 않는다. 모델 응답은 실행 전에 구조와 인자를 검사한다.

## 실행 도구 계약
| 도구 | 인자/반환 예 | 허용 범위 | 승인·오류 |
|---|---|---|---|
| `read_file` (1단계) | 위 "구체적 계약 한 개" 참조 | 작업 폴더 안, 제외 패턴 밖 | 승인 없음(D06). 경로 이탈·제외·없는 파일·디렉터리 |
| `search_text` (1단계) | `{"pattern": "보조용언", "glob": "**/*.py", "max_results": 50}` → `{"matches": [{"path": "...", "line": 128, "text": "..."}], "total": 73, "truncated": true}` | 같음. `glob`도 작업 폴더 기준 | 승인 없음. 잘못된 정규식은 `{"error": "invalid_pattern"}`. 결과가 `max_results`를 넘으면 잘라내고 `truncated: true` |
| `write_file` (2단계, 구현됨) | `{"path": "...", "content": "...", "why": "..."}` → `{"applied": true, "path": "...", "bytes": 1234, "created": false}` | 작업 폴더 안, 제외 패턴 밖. 기존 파일 덮어쓰기와 새 파일 생성 둘 다 가능(2026-09-08 결정 변경, DECISIONS.md). **상위 폴더는 미리 있어야 함** — 새 디렉터리는 만들지 않는다 | 적용 전 경로와 통합 diff(새 파일은 `/dev/null` 기준)를 보여 주고 건별 승인. 거절하면 `{"error": "rejected_by_user"}`이고 파일은 바뀌지 않는다. 내용이 같으면 `no_change`, 상위 폴더가 없으면 `parent_missing` |
| `run_pytest` (2단계, 구현됨) | `{"test_path": "test_rules.py", "test_name": "test_x"}` → `{"command": "...", "exit_code": 0, "passed": 12, "failed": 0, "stdout_tail": "..."}` | 작업 폴더에서 pytest만, 인자는 화이트리스트로 검사한 경로·`-k` 표현식뿐 | 실제 명령줄과 작업 디렉터리를 보여 주고 건별 승인. 시간 상한 120초, 초과 시 종료하고 `{"error": "timeout"}` |
| `run_python` (2026-09-08 추가, 구현됨) | `{"path": "solver.py", "args": ["a", "b"]}` → `{"command": "...", "exit_code": 0, "stdout_tail": "..."}` | 작업 폴더 안 이미 있는 `.py` 파일 하나만. 인라인 코드·셸 명령 불가, 인자는 문자열 배열로 셸 없이 그대로 argv에 전달 | 실제 명령줄과 작업 디렉터리를 보여 주고 건별 승인. 시간 상한 30초, 초과 시 종료하고 `{"error": "timeout"}` |

승인이 필요한 도구는 `preview(guard, arguments)`를 갖는다. 루프는 도구 이름이 아니라 preview의 유무로 승인 대상을 판단한다. 경로 이탈이나 없는 파일처럼 검사에서 걸린 호출은 **사용자에게 묻지도 않고** 거부한다. 물어볼 필요가 없는 것으로 승인 피로를 만들지 않기 위해서다.

승인 재사용 방지: preview는 사용자에게 보여 준 내용의 해시(`digest`)를 갖는다. `write_file`은 적용 직전에 파일을 다시 읽어 해시를 재계산하고, 다르면 `{"error": "stale_approval"}`로 거부한다. 새 파일 생성 승인 중에 다른 경로로 그 파일이 먼저 생겨도 같은 방식으로 걸린다 — "파일 없음"과 "빈 파일"을 다른 해시로 구별해서 가능해진 것이다.

승인자 기본값은 **거절**이다. 승인자를 주지 않고 승인 필요 도구를 등록하면 모든 요청이 `rejected_by_user`가 된다. 콘솔 승인자는 `y`/`yes`만 승인으로 보고, 빈 줄·EOF·그 밖의 입력은 거절로 본다.

같은 승인 재전송: CLI(D02)의 승인은 `input()`으로 막혀 있는 동기 호출 한 번뿐이라, 같은 `approval_id`에 응답이 두 번 도착하는 경로 자체가 없다(웹처럼 버튼을 두 번 누르거나 요청이 중복 전송될 통신 계층이 없다). 그래도 자동화나 재시도 코드가 같은 승인을 프로그램적으로 두 번 부르는 경우를 대비해, `write_file`은 매번 적용 직전 `digest`를 재계산하므로 두 번째 호출도 내용이 같으면 같은 결과를 한 번 더 쓸 뿐 부작용이 늘지 않고, 그 사이 내용이 달라졌으면 `stale_approval`로 막는다. `run_pytest`는 같은 인자로 두 번 실행돼도 테스트를 다시 도는 것 외 부작용이 없다.

구현이 이 문서보다 엄격해진 곳 한 군데를 기록한다.
1. 실행 파일은 `pytest`가 아니라 `sys.executable -m pytest`다. Windows에서 `pytest`가 PATH에 없거나 다른 파이썬의 것이 잡히는 것을 막기 위해서다. 여전히 고정된 실행 파일이며 셸을 거치지 않는다.

`write_file`의 새 파일 생성 제한은 2026-09-08에 완화했다(원래는 기존 파일만 바꿨다) — R08 벤치마크 A11에서 고정 10문항 전부가 새 출력 파일을 요구해 0/10이 나온 것을 실측하고 내린 결정이다. 새 디렉터리 생성까지는 아직 열지 않았다: 상위 폴더가 없으면 여전히 `parent_missing`으로 거부한다.

경로 검사 규칙(모델 지시와 무관하게 코드에서 적용):
1. 작업 폴더를 실제 경로(symlink 해석)로 정규화해 기준으로 삼는다
2. 대상 경로도 실제 경로로 정규화한 뒤 기준의 하위인지 확인한다. `..`과 절대 경로, symlink를 통한 탈출을 모두 이 단계에서 막는다
3. 경로의 어느 구성요소든 제외 목록(`.venv`, `.git`, `__pycache__`, `.pytest_cache`)에 걸리면 거부한다
4. Windows 경로는 대소문자를 구분하지 않고 비교한다

`run_pytest`는 임의 셸 명령이 아니다. 실행 파일은 `pytest`로 고정하고 인자는 검사한 값만 배열로 전달하며 셸을 거치지 않는다. 임의 셸 명령을 허용하는 것은 별도의 권한 확대이며 이번 범위가 아니다.

## 세션 기록 형식
`harness/.sessions/{session_id}.jsonl`. 한 줄이 이벤트 하나이며 모두 `ts`, `session_id`, `event`를 가진다.

| `event` | 추가 필드 |
|---|---|
| `session_start` | `task_id`, `request`, `root`, `provider`, `model`, `max_iterations`, `max_seconds`, `code_version` |
| `model_request` | `iteration`, `message_count`, `tool_names` |
| `model_reply` | `iteration`, `text`, `tool_calls`, `finish_reason`, `usage` |
| `tool_call` | `iteration`, `tool_call_id`, `name`, `arguments` |
| `tool_result` | `iteration`, `tool_call_id`, `ok`, `result` 또는 `error` |
| `guard_block` | `iteration`, `name`, `arguments`, `reason` (경로 이탈·제외 등 검사가 막은 경우) |
| `state` | `iteration`, `value` (`waiting_approval` / `running`), `approval_id` |
| `approval_request` | `iteration`, `approval_id`, `tool_call_id`, `kind`, `summary`, `detail`(보여 준 diff 또는 명령줄 전문), `shown_hash` |
| `approval` | `iteration`, `approval_id`, `tool_call_id`, `decision` (`approve`/`reject`), `shown_hash` |
| `adapter_error` | `iteration`, `code`, `message` |
| `session_end` | `status`, `iterations`, `elapsed_seconds`, `final_text`, `reason` |

API 키와 키가 담긴 환경변수 값은 어떤 이벤트에도 기록하지 않는다. 어댑터는 키를 `os.environ`에서 읽고 그 값을 `session_start`의 어떤 필드에도 넣지 않는다.
