import sys

from pathlib import Path


def get_app_root() -> Path:

    if getattr(sys, 'frozen', False):

        if hasattr(sys, '_MEIPASS'):

            return Path(sys._MEIPASS)

        else:

            return Path(sys.executable).parent

    current_path = Path(__file__).resolve().parent

    markers = ["requirements.txt"]

    for parent in [current_path] + list(current_path.parents):

        if any((parent / marker).exists() for marker in markers):

            return parent

    raise RuntimeError("Could not find the app root")


def get_resource_path(relative: str) -> Path:

    try:

        root = get_app_root()

        full_path = root / relative

        if not full_path.exists():

            raise FileNotFoundError(f"Could not find {full_path}")

        return full_path

    except RuntimeError as e:

        raise RuntimeError(f"Resource loading error: {e}") from e
