from app.qr_tokens import create_signed_token, verify_signed_token


def test_qr_token_roundtrip_and_tamper_rejection():
    token = create_signed_token("secret", {"document_public_id": "doc-1", "document_version_id": "v1"})
    payload = verify_signed_token("secret", token)
    assert payload["document_public_id"] == "doc-1"
    assert payload["document_version_id"] == "v1"
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    try:
        verify_signed_token("secret", bad)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered token must be rejected")
