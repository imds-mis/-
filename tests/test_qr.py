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


def test_public_verification_requires_registered_token_hash(tmp_path):
    import json
    from docx import Document
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.qr_tokens import create_signed_token

    app = create_app(database_url=f"sqlite:///{tmp_path/'db.sqlite'}", storage_root=tmp_path/"storage", qr_secret="secret", public_base_url="http://testserver", stt_url=None)
    client = TestClient(app)
    h = {"X-Tenant-ID":"t1","X-User-ID":"u1","X-Branch-ID":"b1","X-Practitioner-ID":"p1","X-Specialty-Code":"GYNE"}
    source = tmp_path/"t.docx"
    d = Document()
    d.add_paragraph("{{complaints}}")
    d.save(source)
    t = client.post("/v1/admin/templates", headers=h,
        files={"file":("t.docx",source.read_bytes(),"application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"name":"T","fields_json":json.dumps([{"id":"complaints","type":"textarea"}]),"assignments_json":"[]"}
    ).json()["data"]["id"]
    client.post(f"/v1/admin/templates/{t}/publish", headers=h)
    doc = client.post("/v1/doctor/documents", headers=h, json={"template_id":t,"patient_id":"p"}).json()["data"]
    final = client.post(f"/v1/doctor/documents/{doc['id']}/finalize", headers=h).json()["data"]
    assert client.get(final["verification_url"].replace("http://testserver","")).status_code == 200

    forged = create_signed_token("secret", {
        "document_public_id": doc["public_id"],
        "document_version_id": doc["id"],
        "iat": 123,
        "nonce": "different"
    })
    assert client.get(f"/v1/public/documents/{forged}").status_code == 404
