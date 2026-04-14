from backend.job_store import JobStore


def test_job_store_create_get_update(tmp_path):
    database = tmp_path / "storybook.db"
    store = JobStore(str(database))

    created = store.create({"job_type": "train-character", "session_id": "abc"})
    assert created["status"] == "queued"

    loaded = store.get(created["job_id"])
    assert loaded is not None
    assert loaded["payload"]["job_type"] == "train-character"

    updated = store.update(created["job_id"], status="completed", result={"ok": True})
    assert updated is not None
    assert updated["status"] == "completed"


def test_job_store_paginated(tmp_path):
    database = tmp_path / "storybook.db"
    store = JobStore(str(database))

    for _ in range(6):
        store.create({"job_type": "train-character"})

    first_page, cursor = store.list_recent_paginated(limit=3, job_type="train-character")
    assert len(first_page) == 3
    assert cursor

    second_page, _ = store.list_recent_paginated(limit=3, job_type="train-character", cursor=cursor)
    assert len(second_page) >= 1
