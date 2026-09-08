# 인용된 세션 증거

ACCEPTANCE.md·EXPERIMENT_REPORT.md에서 `harness/.sessions/*.jsonl`로 인용한 세션 중,
평가 근거로 직접 참조되는 4개만 여기 복사해 뒀다. 나머지 세션은 `harness/.sessions/`에
남아 있지만 `.gitignore` 대상이라(실사용 텍스트가 그대로 들어있는 것도 있어 기본적으로
제외한다) 이 저장소에는 포함하지 않았다.

| 파일 | 대응 항목 |
|---|---|
| `20260908T062527Z-dd5ca30f.jsonl` | A01 — 실제 모델로 `sample.srt` 읽고 요약 |
| `20260908T062548Z-9435a1fc.jsonl` | A07(b) — 잘못된 키로 실제 호출, 재시도 없이 `failed` |
| `20260908T062825Z-a11b62b6.jsonl` | A04 — 실제 모델이 `write_file` 호출, 비대화 환경이라 자동 거절 |
| `20260908T063340Z-1c197512.jsonl` | A03 — 실제 사람이 PowerShell에서 `y`/`n` 직접 입력한 승인 세션 |

API 키는 어떤 이벤트에도 값 그대로 들어가지 않는다(코드가 보장, `tests/test_loop.py`로 검증).
`20260908T062548Z-9435a1fc.jsonl`의 `sk-inval***********-000`는 OpenAI SDK가 마스킹한
문자열이며 애초에 테스트용으로 심은 가짜 키(`sk-invalid-test-key-000`)다.
