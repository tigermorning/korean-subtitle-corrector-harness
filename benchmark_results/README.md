# 벤치마크 실행 근거 (R08)

`agent-terminal-benchmark-ref/`(외부 채점 도구, 원본 문제·정답이 들어 있어 `.gitignore` 처리됨)에서 실행한
결과 중 제출에 필요한 부분만 옮겨 왔다. 원본 upstream 문제·정답·채점 코드·워크스페이스 덤프는 제외했다.

- `my_agent.py` — 내 하네스(`../harness/`)를 벤치마크에 연결하는 어댑터
- `tasks.json` — 고정 10문항 manifest(원본 커밋·해시)
- `jobs/<실행이름>/run-metadata.json` — 모델·한도·환경 기록
- `jobs/<실행이름>/<문항이름>__1/result.json` — 문항별 실제 채점 결과(`verifier_result.rewards.reward`)
- `reports/<이름>/{trials.csv,report.json,index.html}` — 10문항 집계 리포트

실행 3종:
| 폴더 | 코드 버전 | 변경 내용 |
|---|---|---|
| `jobs/baseline-own` | v0.2.0 | 기준 |
| `jobs/improved` | v0.3.0 | write_file 새 파일 생성 허용 |
| `jobs/improved2-run-python` | v0.4.0 | run_python 도구 추가 |
| `jobs/provided-baseline` | (참고) | 벤치마크 기본 제공 참조 에이전트, 비교용 대조군 |

해석과 결론은 [../EXPERIMENT_REPORT.md](../EXPERIMENT_REPORT.md) 참고.
