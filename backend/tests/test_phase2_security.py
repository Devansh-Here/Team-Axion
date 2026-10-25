import pytest

from app.phase2_eval import ATTACK_QUESTIONS, run_attack_boundary_evaluation, run_follow_up_evaluation
from app.security import is_boundary_attack


def test_phase2_has_30_plus_attack_questions_and_zero_boundary_leaks():
    report = run_attack_boundary_evaluation()
    assert report["case_count"] >= 30
    assert report["blocked_before_model"] == report["case_count"]
    assert report["zero_leaks"] is True


@pytest.mark.parametrize("question", ATTACK_QUESTIONS)
def test_attack_question_is_classified_as_untrusted(question):
    assert is_boundary_attack(question)


def test_follow_up_evaluation_has_50_conversations():
    report = run_follow_up_evaluation()
    assert report["case_count"] == 50
    assert report["passed"] == 50
    assert report["context_resolution_accuracy"] == 1.0
