import sys

from ..core.config import Settings
from ..repositories.corpus import AppliedMigrationChangedError, apply_migrations


def _migrate(database_url: str) -> None:
    try:
        apply_migrations(database_url)
    except AppliedMigrationChangedError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


def main() -> None:
    _migrate(Settings().database_url)  # type: ignore[call-arg]
