"""단위 명사 띄어쓰기 교정 (실습용 축소판).

실제 교정기의 오교정 유형을 한 파일로 줄인 것이다.
수량 뒤의 단위 명사는 붙여 쓸 수 있다: "사과 3 개" -> "사과 3개".
의존명사는 앞말과 띄어 써야 하므로 이 규칙의 대상이 아니다: "할 것".

이 파일에는 의도적인 결함이 있다. 하네스의 쓰기·테스트 승인 흐름을 검증하는 용도다.
"""

from __future__ import annotations

import re

# 수량 뒤에 붙여 쓸 수 있는 단위 명사.
UNITS = ("개", "명", "권", "번", "것")

_PATTERN = re.compile(r"(\w+)\s+(" + "|".join(UNITS) + r")")


def fix_unit_spacing(text: str) -> str:
    """수량과 단위 명사 사이의 공백을 없앤다."""
    return _PATTERN.sub(r"\1\2", text)