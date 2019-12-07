# python3

from os.path import join, relpath, splitext, isdir, dirname
from enum import Enum
from json.decoder import JSONDecodeError
from argparse import ArgumentParser
import json


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
    parser = ArgumentParser(description='Simple db migrations manager')
    parser.add_argument('--show', action='store_true',
                        help='Show all migrations applied')
    args = parser.parse_args()
    init_meta()

    if args.show:
        show_migrations()
    process_migration('migrations/some_test_3.sql')


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
    migration_candidates = []
    _solve_dependencies(migration, migration_candidates, seen=[])
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
            print('Applying {}'.format(name))
            curs.execute(script)
            applied_migrations.append(name)
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


def _solve_dependencies(migration, resolved, seen=None):
    """Recursively solves dependency tree. We use two auxiliary
    accumulators: resolved and seen. A migration is considered
    resolved when all its dependencies have been solved. A
    circular dependency is discovered when a a migration has
    already been walked through but its still not resolved

    :param migration: migration to solve dependencies for
    :param resolved: aux accumulator. Traces solved dependencies
    :param seen: aux accumulator. Traces traversed depenencies
    :returns: None
    :rtype: None
    """
    if seen is None:
        seen = []
    seen.append({'name': migration})
    commands = parse_header(migration)
    for dependency in commands.get('depends_on', []):
        if dependency not in {m['name'] for m in resolved}:
            if dependency in {m['name'] for m in seen}:
                raise ValueError(f'Circular dependency detected '
                                 '{migration, dependency}')
            _solve_dependencies(dependency, resolved, seen)
    resolved.append({'name': migration, **commands})


def parse_header(migration):
    """Parse a migration header to be able to apply monarch's commands

    :param migration: migration to parse header from
    :returns: dictionary with commands
    :rtype: dict

    """
    try:
        with open(migration, 'r') as f:
            line = f.readline()
            if is_valid_command(line):
                line = line[3:].strip()
                try:
                    commands = json.loads(line)
                except JSONDecodeError as error:
                    raise ValueError(
                        f'"{line}" in {migration} '
                        'is not a valid Monarch command'
                    ) from error
                return commands
            return {}
    except Exception as error:
        raise RuntimeError(
            f'parsing headers for {migration} failed'
        ) from error


def is_valid_command(string):
    """Checks if a string is a valid Monarch command

    :param string: string to verify
    :returns: true or false
    :rtype: bool

    """
    return string[:3] == '--!'


def show_migrations():
    migrations = get_applied_migrations()
    print('        MIGRATIONS        ')
    print('--------------------------')
    for migration in migrations:
        status = '✓'
        print(f'{status} {migration}')
    print(f'\n{len(migrations)} migrations applied')



if __name__ == '__main__':
    main()
