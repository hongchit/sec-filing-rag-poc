from ..core.config import Settings
from ..repositories.corpus import apply_migrations


def main() -> None:
    apply_migrations(Settings().database_url)  # type: ignore[call-arg]
