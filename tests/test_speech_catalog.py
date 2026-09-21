from app.catalogs import parse_icd_csv, search_icd_rows
from app.speech import transcribe_for_field
from app.rendering import replace_placeholders


def test_icd_csv_import_and_search():
    raw = "code,title\nI10,Эссенциальная гипертензия\nN80,Эндометриоз\n".encode("utf-8")
    rows = parse_icd_csv(raw)
    assert search_icd_rows(rows, "гипертенз") == [rows[0]]
    assert search_icd_rows(rows, "N80") == [rows[1]]


def test_speech_is_bound_to_requested_text_field():
    fields = [{"id": "complaints", "type": "textarea"}, {"id": "diagnosis", "type": "icd10"}]
    def fake_stt(audio: bytes, content_type: str) -> str:
        return "Боль внизу живота"
    assert transcribe_for_field(fields, "complaints", b"audio", "audio/webm", fake_stt) == {
        "field_id": "complaints", "transcript": "Боль внизу живота", "draft": True
    }
    try:
        transcribe_for_field(fields, "diagnosis", b"audio", "audio/webm", fake_stt)
    except ValueError:
        pass
    else:
        raise AssertionError("ICD field cannot receive direct dictation")


def test_placeholder_rendering():
    assert replace_placeholders("{{patient.full_name}} {{complaints}} {{unknown}}", {
        "patient.full_name": "Иванова А.А.", "complaints": "Боль"
    }) == "Иванова А.А. Боль {{unknown}}"
