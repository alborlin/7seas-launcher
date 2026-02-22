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
        """Find setup.exe or similar installer in extracted files.

        FitGirl repacks use variants like setup-fitgirl.exe, setup-multi10.exe, etc.
        """
        exact_names = {"install.exe", "installer.exe"}
        best = None
        best_depth = float("inf")
        for root, _dirs, files in os.walk(directory):
            depth = root.replace(directory, "").count(os.sep)
            for f in files:
                low = f.lower()
                if not low.endswith(".exe"):
                    continue
                path = os.path.join(root, f)
                # Exact matches (install.exe, installer.exe)
                if low in exact_names:
                    if depth < best_depth:
                        best = path
                        best_depth = depth
                # setup*.exe — covers setup.exe, setup-fitgirl.exe, setup-multi10.exe, etc.
                elif low.startswith("setup") and not low.startswith("setup_redist"):
                    if depth < best_depth:
                        best = path
                        best_depth = depth
        return best
