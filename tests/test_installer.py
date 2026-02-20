"""Tests for Bottles CLI integration."""

import os
import pytest
from unittest.mock import patch, MagicMock

from sevenseas.core.installer import BottlesInstaller, InstallError


@pytest.fixture
def installer():
    return BottlesInstaller(bottle_name="test-bottle")


def test_ensure_bottle_creates_if_missing(installer):
    with patch("sevenseas.core.installer.shutil.which", return_value="bottles-cli"), \
         patch("sevenseas.core.installer.subprocess.run") as mock_run:
        # First call: list bottles (bottle missing)
        # Second call: create bottle
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='[]'),
            MagicMock(returncode=0, stdout='Bottle created'),
        ]
        installer.ensure_bottle()
        assert mock_run.call_count == 2


def test_ensure_bottle_skips_if_exists(installer):
    with patch("sevenseas.core.installer.shutil.which", return_value="bottles-cli"), \
         patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"Name": "test-bottle"}]'
        )
        installer.ensure_bottle()
        assert mock_run.call_count == 1  # only list, no create


def test_run_installer_calls_bottles_cli(installer):
    with patch("sevenseas.core.installer.shutil.which", return_value="bottles-cli"), \
         patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Done")
        result = installer.run_installer("/tmp/setup.exe", ["/S"])
        assert result is True
        args = mock_run.call_args[0][0]
        assert "/tmp/setup.exe" in " ".join(args)


def test_run_installer_raises_on_failure(installer):
    with patch("sevenseas.core.installer.shutil.which", return_value="bottles-cli"), \
         patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Wine error")
        with pytest.raises(InstallError):
            installer.run_installer("/tmp/bad.exe")


def test_move_to_games_dir(installer, tmp_path):
    src = tmp_path / "installed"
    src.mkdir()
    (src / "game.exe").write_text("binary")
    (src / "data.pak").write_text("data")
    dest_base = tmp_path / "Games"
    result = installer.move_to_games_dir(str(src), "TestGame", str(dest_base))
    assert os.path.isfile(os.path.join(result, "game.exe"))
    assert os.path.isfile(os.path.join(result, "data.pak"))
    assert "TestGame" in result
