"""내가 만든 하네스(harness-design-kit/harness)를 이 벤치마크에 연결하는 어댑터.

examples/benchmark_agent.py의 계약을 그대로 따른다. 이 파일 자체는 채점 로직이 없다 —
harness.loop.run()을 그대로 호출하고, 실제로 일어난 일만 status/answer/metrics로 옮겨 담는다.

주의(정직하게 기록): 내 하네스의 도구는 D05 범위(read_file, search_text, write_file,
run_pytest)뿐이라 임의 파이썬 스크립트를 실행하는 도구가 없다. 이 벤치마크의 여러 문제는
"코드 작성 + 실제 실행해서 산출물 생성"을 요구하므로, 그 경우 내 하네스는 파일을 쓰는 것까지는
해도 실행까지는 못 한다. 이건 이 어댑터의 버그가 아니라 D05가 애초에 다른 도메인(자막 교정기
오교정 원인 찾기)에 맞춰 좁게 잡혀 있었기 때문이다 — 그 사실 자체를 이 실험으로 확인한다.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from pathlib import Path

# harness-design-kit 루트를 sys.path에 넣어 harness 패키지를 가져온다.
# bench.py가 실행 시점 소스를 jobs/<이름>/source/ 사본으로 복사해 돌리기 때문에
# 이 파일 기준 상대 경로(parents[N])로는 원래 위치를 찾을 수 없다 — 고정 경로를 쓴다.
HARNESS_ROOT = Path(r"C:\Users\user\Documents\harness-design-kit")
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from harness.approval import ScriptedApprover  # noqa: E402
from harness.loop import run as harness_run  # noqa: E402
from harness.paths import PathGuard, PathRejected  # noqa: E402
from harness.providers import build as build_adapter  # noqa: E402
from harness.session import SessionRecorder, new_session_id  # noqa: E402
from harness.tools import READ_WRITE_TOOLS  # noqa: E402

PATH_NOTE = (
    "이 작업 폴더 안에서는 절대경로 대신 작업 폴더 기준 상대경로만 써라. "
    "예: /app/puzzle.txt 대신 app/puzzle.txt, /home/user/x 대신 home/user/x. "
    "그 밖의 절대경로·상위 폴더 이동은 전부 거부된다.\n\n"
)


async def solve_task(instruction: str, workspace: Path, logs_dir: Path, options: dict) -> dict:
    logs_dir.mkdir(parents=True, exist_ok=True)

    request = PATH_NOTE + instruction
    if options.get("task_cwd") and options["task_cwd"] != ".":
        request += f"\n\n작업 폴더 기준 하위 위치: {options['task_cwd']}"

    def run_sync() -> dict:
        try:
            guard = PathGuard(str(workspace))
        except PathRejected as exc:
            return {"status": "failed", "answer": None, "metrics": {"error": exc.code}}

        adapter = build_adapter(options["provider"], options.get("model"))
        recorder = SessionRecorder(new_session_id(), directory=logs_dir / "sessions")
        # 평가용 작업 폴더 안의 쓰기는 사전 허용된 동작으로 다룬다(README "평가용 도구는
        # 새 작업 폴더의 수정을 자동 승인합니다"). 사람이 매번 확인하는 로컬 CLI의 기본
        # 거절 정책(D06)과는 의도적으로 다른, 이 벤치마크 연결에서만 쓰는 정책이다.
        approver = ScriptedApprover(answers=[], default=True)

        result = harness_run(
            request,
            guard=guard,
            adapter=adapter,
            registry=READ_WRITE_TOOLS,
            recorder=recorder,
            approver=approver,
            max_iterations=options["max_steps"],
            max_seconds=options["max_seconds"],
        )
        return {
            "status": result.status,
            "answer": result.final_text,
            "metrics": {
                "iterations": result.iterations,
                "elapsed_seconds": result.elapsed_seconds,
                "reason": result.reason,
            },
        }

    return await asyncio.to_thread(run_sync)
