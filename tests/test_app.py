from pathlib import Path
from io import BytesIO

from oniondrop.web import create_app


def app(tmp_path: Path):
    instance = create_app({"TESTING": True, "DATA_ROOT": tmp_path, "MOCK": True})
    return instance, instance.test_client()


def test_create_start_stop_and_delete(tmp_path):
    application, client = app(tmp_path)
    response = client.post("/api/inboxes", json={"name": "Test drop", "start_now": True})
    assert response.status_code == 201
    inbox = response.get_json()["inbox"]
    assert inbox["status"] == "online"
    assert inbox["url"].endswith(".onion")
    assert inbox["private_key"]
    assert client.post(f"/api/inboxes/{inbox['id']}/stop").status_code == 200
    assert client.delete(f"/api/inboxes/{inbox['id']}").status_code == 200
    assert client.get("/api/inboxes").get_json()["inboxes"] == []
    application.extensions["oniondrop_manager"].shutdown()


def test_reject_both_receive_types_disabled(tmp_path):
    application, client = app(tmp_path)
    response = client.post("/api/inboxes", json={"allow_files": False, "allow_text": False})
    assert response.status_code == 400
    application.extensions["oniondrop_manager"].shutdown()


def test_import_receive_config(tmp_path):
    application, client = app(tmp_path)
    config = b'{"persistent":{"mode":"receive","enabled":true},"general":{"title":"Portable","public":true},"receive":{"disable_files":false,"disable_text":true},"onion":{"private_key":"ED25519-V3:TEST"}}'
    response = client.post(
        "/api/import",
        data={"config": (BytesIO(config), "portable.json")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    inbox = response.get_json()["inbox"]
    assert inbox["name"] == "Portable"
    assert inbox["public"] is True
    assert inbox["allow_files"] is True
    assert inbox["allow_text"] is False
    application.extensions["oniondrop_manager"].shutdown()
