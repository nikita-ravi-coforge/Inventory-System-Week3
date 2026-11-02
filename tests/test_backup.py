"""SQLite backup copies the open database and keeps it intact."""

from contextlib import closing

from inventory_db import backup_database, connect, load_sample_data, table_counts


def test_backup_passes_integrity_check_and_matches_counts(connection, tmp_path):
    with connection:
        load_sample_data(connection)
    destination = tmp_path / "inventory-backup.db"
    backup_database(connection, destination)
    with closing(connect(destination)) as copy:
        check = copy.execute("PRAGMA integrity_check").fetchone()
        assert check[0] == "ok"
        assert table_counts(copy) == table_counts(connection)
