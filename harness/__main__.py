"""CLI 진입점.

INTERFACES.md "UI와 통신 매핑"의 명령 표를 구현한다.
종료 코드: 0 completed / 1 failed / 2 사용법 오류.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .approval import AlwaysReject, ConsoleApprover
from .contracts import AdapterError
from .loop import DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_SECONDS, run
from .paths import DEFAULT_EXCLUDED, PathGuard, PathRejected
from .providers import AVAILABLE, build
from .session import DEFAULT_SESSION_DIR, SessionRecorder, new_session_id, read_session
from .tools import READ_ONLY_TOOLS, READ_WRITE_TOOLS

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 코드페이지(cp949 등)가 em dash 같은 문자를 인코딩하지 못해
    # 거절 메시지 출력 중 죽는 문제가 실제 실행에서 발견됐다. 표준출력을 UTF-8로 고정한다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except ValueError:
                pass

    parser = argparse.ArgumentParser(prog="harness", description="개인 에이전트 하네스")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="요청 하나를 실행한다")
    ask.add_argument("request", help="자연어 요청")
    ask.add_argument("--root", required=True, help="작업 폴더. 이 밖은 읽지 않는다")
    ask.add_argument("--provider", default="openai", choices=AVAILABLE)
    ask.add_argument("--model", default=None, help="제공자의 모델 이름")
    ask.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    ask.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    ask.add_argument("--dry-run", action="store_true", help="모의 어댑터로 실행. 실제 모델을 부르지 않는다")
    ask.add_argument(
        "--allow-write",
        action="store_true",
        help="write_file과 run_pytest를 연다. 적용 전에 매번 승인을 묻는다",
    )
    ask.add_argument("--session-dir", default=None)

    show = sub.add_parser("show", help="저장된 세션 기록을 본다")
    show.add_argument("session_id")
    show.add_argument("--session-dir", default=None)

    args = parser.parse_args(argv)
    if args.command == "ask":
        return _cmd_ask(args)
    return _cmd_show(args)


def _cmd_ask(args: argparse.Namespace) -> int:
    if not args.request.strip():
        print("요청이 비어 있습니다.", file=sys.stderr)
        return EXIT_USAGE
    if args.max_iterations < 1 or args.max_seconds <= 0:
        print("--max-iterations는 1 이상, --max-seconds는 0보다 커야 합니다.", file=sys.stderr)
        return EXIT_USAGE

    try:
        guard = PathGuard(args.root)
    except PathRejected as rejected:
        print(f"작업 폴더 오류: {rejected.message}", file=sys.stderr)
        return EXIT_USAGE

    provider = "mock" if args.dry_run else args.provider
    try:
        adapter = build(provider, args.model)
    except AdapterError as exc:
        print(f"provider 오류 [{exc.code}] {exc.message}", file=sys.stderr)
        return EXIT_USAGE

    model_name = getattr(adapter, "model", provider)
    session_dir = Path(args.session_dir) if args.session_dir else DEFAULT_SESSION_DIR
    recorder = SessionRecorder(new_session_id(), session_dir)

    registry = READ_WRITE_TOOLS if args.allow_write else READ_ONLY_TOOLS
    # 승인을 물을 수 없는 환경에서는 승인이 필요한 도구를 전부 거절한다.
    interactive = sys.stdin is not None and sys.stdin.isatty()
    approver = ConsoleApprover() if interactive else AlwaysReject()

    # 재개는 구현하지 않는다(D07). 매 실행이 새 세션임을 사용자에게 알린다.
    print(f"세션 {recorder.session_id} 시작 (이전 세션을 복원하지 않았습니다)")
    print(f"작업 폴더: {guard.root}")
    print(f"제외: {', '.join(DEFAULT_EXCLUDED)}")
    print(f"provider: {provider} / 모델: {model_name}")
    print(f"도구: {', '.join(sorted(registry))}")
    if args.allow_write:
        print("쓰기와 테스트 실행이 열렸습니다. 적용 전에 매번 승인을 묻습니다.")
        if not interactive:
            print("입력이 터미널이 아니어서 승인 요청은 모두 거절됩니다.")
    if args.dry_run:
        print("모의 어댑터입니다. 실제 모델을 부르지 않습니다.")
    print("-" * 60)

    recorder.record(
        "session_start",
        task_id=recorder.session_id,
        request=args.request,
        root=str(guard.root),
        excluded=list(DEFAULT_EXCLUDED),
        provider=provider,
        model=model_name,
        tools=sorted(registry),
        allow_write=bool(args.allow_write),
        approver=type(approver).__name__,
        max_iterations=args.max_iterations,
        max_seconds=args.max_seconds,
        code_version=__version__,
    )

    result = run(
        args.request,
        guard=guard,
        adapter=adapter,
        registry=registry,
        recorder=recorder,
        approver=approver,
        max_iterations=args.max_iterations,
        max_seconds=args.max_seconds,
        on_event=lambda line: print(line),
    )

    print("-" * 60)
    if result.status == "completed":
        print(result.final_text or "(최종 답이 비어 있습니다)")
    else:
        print(f"실패: {result.reason}", file=sys.stderr)
    print("-" * 60)
    print(f"상태 {result.status} / 반복 {result.iterations}회 / {result.elapsed_seconds:.1f}초")
    print(f"기록: {result.session_path}")
    return EXIT_OK if result.status == "completed" else EXIT_FAILED


def _cmd_show(args: argparse.Namespace) -> int:
    session_dir = Path(args.session_dir) if args.session_dir else DEFAULT_SESSION_DIR
    path = session_dir / f"{args.session_id}.jsonl"
    if not path.is_file():
        print(f"세션 기록이 없습니다: {path}", file=sys.stderr)
        return EXIT_USAGE

    for row in read_session(path):
        event = row.get("event")
        if event == "session_start":
            print(f"[시작] {row['request']}")
            print(f"       root={row['root']} provider={row['provider']} model={row['model']}")
        elif event == "tool_call":
            print(f"[도구] {row['name']} {row.get('arguments')}")
        elif event == "guard_block":
            print(f"[차단] {row['name']} — {row['reason']}")
        elif event == "approval":
            mark = "승인" if row["decision"] == "approve" else "거절"
            print(f"[{mark}] {row['approval_id']} hash={row['shown_hash'][:12]}")
        elif event == "adapter_error":
            print(f"[오류] {row['code']} — {row['message']}")
        elif event == "session_end":
            print(f"[종료] {row['status']} reason={row.get('reason')} 반복={row['iterations']}")
            if row.get("final_text"):
                print(row["final_text"])
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
