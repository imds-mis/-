from speech.app.pipeline import SessionSpeakerMap, normalize_turns


def test_first_speaker_is_doctor_second_is_patient_and_mapping_is_stable():
    mapping = SessionSpeakerMap()

    first = normalize_turns(
        [
            {"speaker": "SPEAKER_01", "text": "Что вас беспокоит?", "start": 0.0, "end": 1.4},
            {"speaker": "SPEAKER_00", "text": "Болит живот.", "start": 1.5, "end": 2.8},
        ],
        mapping,
    )

    assert first[0]["speaker"] == "doctor"
    assert first[1]["speaker"] == "patient"

    second = normalize_turns(
        [
            {"speaker": "SPEAKER_00", "text": "Третий день.", "start": 0.0, "end": 1.0},
            {"speaker": "SPEAKER_01", "text": "Температура была?", "start": 1.1, "end": 2.0},
        ],
        mapping,
    )

    assert second[0]["speaker"] == "patient"
    assert second[1]["speaker"] == "doctor"


def test_empty_text_is_dropped():
    mapping = SessionSpeakerMap()
    result = normalize_turns([
        {"speaker": "SPEAKER_00", "text": "   ", "start": 0.0, "end": 1.0},
        {"speaker": "SPEAKER_00", "text": "Здравствуйте", "start": 1.0, "end": 2.0},
    ], mapping)

    assert len(result) == 1
    assert result[0]["speaker"] == "doctor"
    assert result[0]["text"] == "Здравствуйте"
