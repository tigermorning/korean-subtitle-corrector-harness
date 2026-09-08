"""fixtures/spacing_rules의 기대 동작.

하네스가 rules.py를 고친 뒤 run_pytest로 확인하는 대상이다.
현재 test_does_not_join_dependent_noun 이 실패한다.
"""

from rules import fix_unit_spacing


def test_joins_number_and_unit():
    assert fix_unit_spacing("사과 3 개") == "사과 3개"
    assert fix_unit_spacing("학생 12 명") == "학생 12명"


def test_does_not_join_dependent_noun():
    # '것'은 의존명사이므로 앞말과 띄어 써야 한다. 붙이면 오교정이다.
    assert fix_unit_spacing("할 것이다") == "할 것이다"
    assert fix_unit_spacing("먹을 것 같다") == "먹을 것 같다"


def test_leaves_unrelated_text_alone():
    assert fix_unit_spacing("자막 검토") == "자막 검토"
