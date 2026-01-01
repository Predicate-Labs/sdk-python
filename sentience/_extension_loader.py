"""
Shared extension loading logic for sync and async implementations
"""

from pathlib import Path


def find_extension_path() -> Path:
    """
    Find Sentience extension directory (shared logic for sync and async).

    Checks multiple locations:
    1. sentience/extension/ (installed package)
    2. ../sentience-chrome (development/monorepo)

    Returns:
        Path to extension directory

    Raises:
        FileNotFoundError: If extension not found in any location
    """
    # 1. Try relative to this file (installed package structure)
    # sentience/_extension_loader.py -> sentience/extension/
    package_ext_path = Path(__file__).parent / "extension"

    # 2. Try development root (if running from source repo)
    # sentience/_extension_loader.py -> ../sentience-chrome
    dev_ext_path = Path(__file__).parent.parent.parent / "sentience-chrome"

    if package_ext_path.exists() and (package_ext_path / "manifest.json").exists():
        return package_ext_path
    elif dev_ext_path.exists() and (dev_ext_path / "manifest.json").exists():
        return dev_ext_path
    else:
        raise FileNotFoundError(
            f"Extension not found. Checked:\n"
            f"1. {package_ext_path}\n"
            f"2. {dev_ext_path}\n"
            "Make sure the extension is built and 'sentience/extension' directory exists."
        )

