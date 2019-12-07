# python3

from os.path import join, relpath, splitext, isdir, dirname
from enum import Enum


class DBEngine(Enum):
    SQLITE = 1
    POSTGRES = 2


# TODO: add config file
_INIT_MIGRATION = 'migrations/meta.sql'
_INTERNAL_DB_FILE = 'monarch.sql'
_INTERNAL_DB_ENGINE = DBEngine.SQLITE
_TARGET_DB_ENGINE = DBEngine.POSTGRES


def main():
    # TODO: add argparse
    init_meta()
    process_migration('migrations/some_test_1.sql')


def init_meta():
    # TODO: add try-except
    connection = get_db_connection(internal=True)
    with connection:
        curs = connection.cursor()
        script = get_sql_script(_INIT_MIGRATION)
        curs.execute(script)
        connection.commit()


def process_migration(migration):
    migrations_to_run = get_migrations_to_run(migration)
    run_migrations(migrations_to_run)


def get_migrations_to_run(migration):
    migration_candidates = [{'name': migration}]
    # _solve_dependencies(migration, migrations_to_run, seen=[])
    applied_migrations = get_applied_migrations()
    migrations_to_run = [m for m in migration_candidates
                         if m['name'] not in applied_migrations]
    return migrations_to_run


def get_applied_migrations():
    # TODO: add try-except
    connection = get_db_connection(internal=True)
    with connection:
        cursor = connection.cursor()
        sql = 'SELECT name from migration;'
        cursor.execute(sql)
        migrations = cursor.fetchall()
    return [m[0] for m in migrations]


def run_migrations(migrations,
                   apply_migration=True,
                   register=True):
    """Apply a list of migrations to db

    :param migrations: list of migrations to apply
    :param apply_migration: if true, apply migrations to db
    :param register_migration: if true, register applied migrations to db
    :returns: None
    :rtype: None

    """
    for migration in migrations:
        name = migration['name']
        migration['script'] = get_sql_script(name)

    connection = get_db_connection()
    # When exiting context manager, everything executed through the
    # connection is commited in a single transaction, unless we force
    # it through commit()
    applied_migrations = []
    with connection:
        curs = connection.cursor()
        for migration in migrations:
            name = migration['name']
            script = migration['script']
            try:
                print('Applying {}'.format(name))
                curs.execute(script)
                applied_migrations.append(name)
            except Error as error:
                raise RuntimeError('failed processing {}'.format(name))
        connection.commit()
    if register:
        register_migrations(applied_migrations)


def register_migrations(migrations):
    # TODO: add try-except
    connection = get_db_connection(internal=True)
    with connection:
        cursor = connection.cursor()
        for migration in migrations:
            cursor.execute("INSERT INTO migration (name) "
                           "VALUES ('%s');" % migration)
        connection.commit()


def get_db_connection(internal=False):
    # TODO: Improve this to be more flexible
    if internal:
        import sqlite3
        engine_module = sqlite3
        connection_params = {'database': _INTERNAL_DB_FILE}
    else:
        import psycopg2
        engine_module = psycopg2
        connection_params = {
            'user': 'postgres',
            'host': 'localhost',
            'port': '5432',
        }
    try:
        conn = engine_module.connect(**connection_params)
    except Error as e:
        print(e)
    return conn


def get_sql_script(migration):
    """Get sql script from a migration

    :param migration: migration to extract content from
    :returns: a sql script
    :rtype: string

    """
    with open(migration, 'r') as f:
        sql = " ".join(f.readlines())
    return sql


if __name__ == '__main__':
    main()
