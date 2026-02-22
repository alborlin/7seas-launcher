"""Tests for archive extractor."""

import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from sevenseas.core.extractor import Extractor, ExtractionError


def _mock_popen(returncode=0, stdout="", stderr=""):
    """Create a mock Popen that behaves like a real one."""
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    proc.poll.return_value = returncode
    return proc


def test_extract_calls_7z_with_correct_args():
    with patch("sevenseas.core.extractor.subprocess.Popen") as mock_popen_cls:
        mock_popen_cls.return_value = _mock_popen(returncode=0)
        ext = Extractor()
        ext.extract("/tmp/archive.7z", "/tmp/output")
        mock_popen_cls.assert_called_once()
        args = mock_popen_cls.call_args[0][0]
        assert "7z" in args[0]
        assert "x" in args
        assert "/tmp/archive.7z" in args
        assert any("/tmp/output" in a for a in args)


def test_extract_raises_on_failure():
    with patch("sevenseas.core.extractor.subprocess.Popen") as mock_popen_cls:
        mock_popen_cls.return_value = _mock_popen(returncode=2, stderr="Error: file not found")
        ext = Extractor()
        with pytest.raises(ExtractionError):
            ext.extract("/tmp/bad.7z", "/tmp/output")


def test_extract_creates_output_dir(tmp_path):
    dest = tmp_path / "output"
    with patch("sevenseas.core.extractor.subprocess.Popen") as mock_popen_cls:
        mock_popen_cls.return_value = _mock_popen(returncode=0)
        ext = Extractor()
        ext.extract("/tmp/archive.7z", str(dest))
        assert dest.exists()


def test_find_setup_exe(tmp_path):
    """Should find setup.exe in extracted directory."""
    (tmp_path / "setup.exe").touch()
    (tmp_path / "readme.txt").touch()
    (tmp_path / "data.bin").touch()
    ext = Extractor()
    setup = ext.find_setup_exe(str(tmp_path))
    assert setup is not None
    assert setup.endswith("setup.exe")


def test_find_setup_exe_case_insensitive(tmp_path):
    (tmp_path / "Setup.exe").touch()
    ext = Extractor()
    setup = ext.find_setup_exe(str(tmp_path))
    assert setup is not None


def test_find_setup_exe_returns_none_when_missing(tmp_path):
    (tmp_path / "readme.txt").touch()
    ext = Extractor()
    assert ext.find_setup_exe(str(tmp_path)) is None
