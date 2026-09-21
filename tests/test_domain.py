from app.domain import field_supports_dictation, template_is_eligible


def test_dictation_only_for_text_fields():
    assert field_supports_dictation({"type": "text"}) is True
    assert field_supports_dictation({"type": "textarea"}) is True
    assert field_supports_dictation({"type": "icd10"}) is False
    assert field_supports_dictation({"type": "select"}) is False


def test_template_eligibility_matches_specialty_branch_and_practitioner():
    assignments = [
        {"specialty_code": "GYNE", "branch_id": None, "practitioner_id": None, "visit_type": None},
        {"specialty_code": None, "branch_id": "b2", "practitioner_id": "p2", "visit_type": "follow_up"},
    ]
    assert template_is_eligible(assignments, specialty_code="GYNE", branch_id="b1", practitioner_id="p1", visit_type="consultation")
    assert template_is_eligible(assignments, specialty_code="CARD", branch_id="b2", practitioner_id="p2", visit_type="follow_up")
    assert not template_is_eligible(assignments, specialty_code="CARD", branch_id="b2", practitioner_id="p9", visit_type="follow_up")
