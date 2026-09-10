from pathlib import Path

from google_photos_takeout_organizer.session import (
    WorkflowState,
    create_session,
    is_incomplete_session,
    load_session,
    safe_temp_target,
    save_session,
    sources_match,
)


def test_session_save_load_and_source_change_detection(tmp_path: Path) -> None:
    source = tmp_path / "takeout.zip"
    source.write_bytes(b"original")
    output = tmp_path / "output"
    session = create_session([source], output)
    save_session(output, session)
    assert is_incomplete_session(load_session(output))
    assert sources_match(session)
    source.write_bytes(b"changed")
    assert not sources_match(session)


def test_completed_session_is_not_offered_for_resume(tmp_path: Path) -> None:
    source = tmp_path / "takeout.zip"
    source.write_bytes(b"zip")
    session = create_session([source], tmp_path / "output")
    session.update({"status": WorkflowState.COMPLETED, "completed": True})
    assert not is_incomplete_session(session)


def test_temp_cleanup_target_is_strictly_limited_to_output_work_dir(tmp_path: Path) -> None:
    output = tmp_path / "output"
    assert safe_temp_target(output) == (output / ".gpto_work").resolve()
