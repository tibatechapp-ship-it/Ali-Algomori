"""Concurrent job transition and cancellation race regression tests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from geologia_workspace import store


def _create_job(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOLOGIA_DB_PATH", str(tmp_path / "jobs.sqlite3"))
    monkeypatch.setenv("GEOLOGIA_UPLOAD_DIR", str(tmp_path / "uploads"))
    project = store.create_project("Concurrency", "", "en")
    return store.create_job(project["id"], "Race test", "en", {"required_inputs": []})


def test_concurrent_planned_cancellation_is_idempotent(tmp_path, monkeypatch):
    job = _create_job(tmp_path, monkeypatch)
    barrier = Barrier(2)

    def cancel():
        barrier.wait()
        return store.request_job_cancellation(job["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: cancel(), range(2)))

    assert [result["status"] for result in results] == ["cancelled", "cancelled"]
    events = store.list_job_events(job["id"])
    assert [event["to_status"] for event in events] == ["planned", "cancelled"]


def test_worker_completion_and_cancellation_race_has_one_winner(tmp_path, monkeypatch):
    job = _create_job(tmp_path, monkeypatch)
    store.transition_job(job["id"], "queued", actor="system")
    store.transition_job(job["id"], "running", actor="worker")
    barrier = Barrier(2)

    def complete():
        barrier.wait()
        try:
            return store.transition_job(job["id"], "succeeded", actor="worker")
        except ValueError:
            return None

    def cancel():
        barrier.wait()
        try:
            return store.request_job_cancellation(job["id"])
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        completion = executor.submit(complete)
        cancellation = executor.submit(cancel)
        completion_result = completion.result()
        cancellation_result = cancellation.result()

    current = store.get_job(job["id"])
    assert current["status"] in {"succeeded", "cancel_requested"}
    assert (completion_result is not None) != (cancellation_result is not None)
    events = store.list_job_events(job["id"])
    assert [event["to_status"] for event in events] == [
        "planned", "queued", "running", current["status"]
    ]

    if current["status"] == "cancel_requested":
        cancelled = store.transition_job(job["id"], "cancelled", actor="worker")
        assert cancelled["status"] == "cancelled"
