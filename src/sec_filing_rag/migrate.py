from .config import Settings
from .store import apply_migrations


def main() -> None:
    apply_migrations(Settings().database_url)  # type: ignore[call-arg]
