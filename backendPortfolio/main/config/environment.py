from pathlib import Path

from dotenv import load_dotenv

LOCAL_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_local_env(path: Path = LOCAL_ENV_FILE) -> bool:
    return load_dotenv(path, override=False)
