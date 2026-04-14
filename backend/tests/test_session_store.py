from backend.session_store import SessionStore


def test_session_store_upsert_and_get(tmp_path):
    database = tmp_path / "storybook.db"
    store = SessionStore(str(database))

    metadata = {"session_id": "s1", "name": "Ava", "character_profile": {"status": "ready"}}
    store.upsert("s1", metadata)

    loaded = store.get("s1")
    assert loaded["name"] == "Ava"

    metadata["name"] = "Aria"
    store.upsert("s1", metadata)
    loaded2 = store.get("s1")
    assert loaded2["name"] == "Aria"
