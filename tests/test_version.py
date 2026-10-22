from pathlib import Path
import tomllib

from google_photos_takeout_organizer import __version__
from google_photos_takeout_organizer.report import write_report
from google_photos_takeout_organizer.service import analyze


def test_package_manifest_and_report_version_match(tmp_path):
    metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == __version__
    manifest = analyze([], tmp_path / "work")
    assert manifest["app_version"] == __version__
    report = tmp_path / "fallback.html"
    write_report({}, report)
    assert f"(v{__version__})" in report.read_text(encoding="utf-8")


def test_historical_report_preserves_recorded_version(tmp_path):
    report = tmp_path / "historical.html"
    write_report({"app_version": "1.2.0"}, report)
    assert "(v1.2.0)" in report.read_text(encoding="utf-8")
