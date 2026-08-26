from __future__ import annotations

import pytest

from app.services.workspace import WorkspaceError, sanitize_filename, sanitize_output_filename


def test_filename_sanitization_removes_paths():
    assert sanitize_filename("../../日本語 sample.vi") == "日本語_sample.vi"


def test_output_filename_requires_rsrc_extension():
    assert sanitize_output_filename("result.VI") == "result.VI"
    with pytest.raises(WorkspaceError):
        sanitize_output_filename("result.exe")
