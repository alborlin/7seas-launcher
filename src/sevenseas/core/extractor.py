"""Archive extraction using 7z CLI."""

import os
import subprocess
from pathlib import Path


class ExtractionError(Exception):
    """Raised when extraction fails."""


class Extractor:
    """Extracts archives using the 7z command-line tool."""

    def __init__(self, sevenz_bin: str = "7z") -> None:
        self._bin = sevenz_bin

    def extract(self, archive_path: str, dest_dir: str) -> None:
        """Extract an archive to the destination directory."""
        os.makedirs(dest_dir, exist_ok=True)
        result = subprocess.run(
            [self._bin, "x", archive_path, f"-o{dest_dir}", "-y"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ExtractionError(
                f"7z extraction failed (code {result.returncode}): {result.stderr}"
            )

    def find_setup_exe(self, directory: str) -> str | None:
        """Find setup.exe or similar installer in extracted files."""
        setup_names = {"setup.exe", "install.exe", "installer.exe"}
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.lower() in setup_names:
                    return os.path.join(root, f)
        return None
