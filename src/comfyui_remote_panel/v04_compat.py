from __future__ import annotations


def install() -> None:
    """Keep the v0.4 additive schema readable by v0.3/main.

    v0.4 only adds nullable/defaulted columns plus a side table.  SQLite readers
    from v0.3 safely ignore those additions, so the compatibility marker can
    remain at user_version=5.  This lets a tester switch back to main without
    deleting history.  Existing databases already marked as v6 are normalized
    back to 5 after verifying the v0.4 additions are present.
    """

    from . import db as db_module

    v04_initialize = db_module.Database.initialize
    required_columns = {
        "seed_policy",
        "seed_value",
        "actual_seed",
        "media_metadata_json",
    }

    def inspect(connection):
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        counter_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'seed_counters'"
        ).fetchone() is not None
        return version, columns, counter_table

    async def initialize_compat(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version, columns, counter_table = inspect(connection)

            # A database previously opened by the first v0.4 beta used marker 6.
            # Its physical schema is additive and v0.3-compatible, so normalize
            # only the marker; do not drop columns, tables, jobs, or artifacts.
            if version == 6:
                if not required_columns <= columns or not counter_table:
                    raise RuntimeError("incomplete v0.4 database schema")
                connection.execute("PRAGMA user_version = 5")
                return

            # Once v0.4 additions exist, marker 5 is intentional.  Calling the
            # original v0.4 migration again would try to ALTER duplicate columns.
            if version == 5 and required_columns <= columns and counter_table:
                return

            if version > 6:
                raise RuntimeError(f"unsupported database schema version: {version}")

        # Fresh/v1-v5 databases still use the normal migration path once.
        await v04_initialize(self)

        async with self._lock:
            with self._connect() as connection:
                version, columns, counter_table = inspect(connection)
                if version != 6 or not required_columns <= columns or not counter_table:
                    raise RuntimeError("v0.4 database migration did not complete")
                # Keep the additive physical schema, but preserve the v0.3/main
                # compatibility marker so branch rollback remains non-destructive.
                connection.execute("PRAGMA user_version = 5")

    db_module.Database.initialize = initialize_compat
