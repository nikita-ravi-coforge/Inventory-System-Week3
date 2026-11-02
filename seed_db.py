"""Create the tables, load the sample catalog, and print each row count."""

from contextlib import closing

from inventory_db import connect, db_path, init_db, load_sample_data, table_counts


def main() -> None:
    with closing(connect(db_path())) as connection:
        init_db(connection)
        with connection:
            load_sample_data(connection)
        for table_name, count in table_counts(connection).items():
            print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
