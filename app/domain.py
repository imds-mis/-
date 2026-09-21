from __future__ import annotations

from typing import Iterable, Mapping, Any


def field_supports_dictation(field: Mapping[str, Any]) -> bool:
    return field.get("type") in {"text", "textarea"}


def template_is_eligible(
    assignments: Iterable[Mapping[str, Any]],
    *,
    specialty_code: str | None,
    branch_id: str | None,
    practitioner_id: str | None,
    visit_type: str | None,
) -> bool:
    for assignment in assignments:
        checks = (
            (assignment.get("specialty_code"), specialty_code),
            (assignment.get("branch_id"), branch_id),
            (assignment.get("practitioner_id"), practitioner_id),
            (assignment.get("visit_type"), visit_type),
        )
        if all(expected is None or expected == actual for expected, actual in checks):
            return True
    return False
