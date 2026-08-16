from pathlib import Path


def test_corpus_status_groups_correlated_company_key() -> None:
    migration = Path("migrations/versions/0001_medallion.sql").read_text(encoding="utf-8")
    view = migration.split("CREATE VIEW gold.corpus_status AS", 1)[1]
    assert "ir.company_id = c.id" in view
    assert "GROUP BY c.id, c.ticker" in view
