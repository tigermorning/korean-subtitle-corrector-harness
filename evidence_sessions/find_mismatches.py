"""korean-subtitle-corrector 원본 저장소 루트에서 실행: 라벨 71건(heldout.jsonl 41
+ 작업자자료.jsonl 30)을 실제 엔진에 통과시켜 현재 진짜로 틀리는 사례를 찾는다.
S01(ACCEPTANCE.md)에서 쓸 실제 오교정 사례를 정답 라벨을 넣지 않고 고르기 위한 용도.
결과는 real_mismatches_71cases.json에 저장된다(이 저장소에 그 결과를 커밋해 뒀다).
`.venv\\Scripts\\python.exe find_mismatches.py`
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import SubtitleEntry

items = [json.loads(l) for l in open("examples/eval/heldout.jsonl", encoding="utf-8")] + \
        [json.loads(l) for l in open("examples/eval/작업자자료.jsonl", encoding="utf-8")]

mismatches = []
for item in items:
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=item["input"], speaker=item.get("speaker"))
    dialect_map = {}
    dialect_modes = {}
    if item.get("speaker") and item.get("region"):
        dialect_map[item["speaker"]] = item["region"]
        if item.get("mode"):
            dialect_modes[item["speaker"]] = item["mode"]
    try:
        corrected, flags, _log = correct_entries([entry], dialect_map, dialect_modes)
        got = corrected[0].text
    except Exception as e:
        got = f"ERROR: {e}"
    gold_options = [item["gold"]] + item.get("gold_alt", [])
    if got not in gold_options:
        mismatches.append({"id": item["id"], "input": item["input"], "got": got, "gold": item["gold"], "basis": item.get("basis",""), "category": item.get("category","")})

with open("real_mismatches_71cases.json", "w", encoding="utf-8") as f:
    json.dump({"total": len(items), "mismatch_count": len(mismatches), "mismatches": mismatches}, f, ensure_ascii=False, indent=2)
print("done", len(items), len(mismatches))
