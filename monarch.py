#!/usr/bin/env python3
import argparse
import json
from json.decoder import JSONDecodeError
from os import getenv, listdir
from os.path import join, splitext, isfile
from dotenv import load_dotenv
from sqlalchemy.sql import func
from sqlalchemy import (create_engine, MetaData, Table,
                        Column, Integer, String, DateTime)

if isfile('.env'):
    load_dotenv('.env')
_INTERNAL_DB_URL = getenv('INTERNAL_DB_URL')
_TARGET_DB_URL = getenv('TARGET_DB_URL')


def main():
    parser = argparse.ArgumentParser(description='Simple db migration manager')
    parser.add_argument('-m', '--migrate', help='Migration file to run')
    parser.add_argument('-a', '--all', action='store_true',
                        help='Run all available migrations')
    parser.add_argument('-d', '--migrations-dir', help='Migrations directory',
                        default='migrations')
    parser.add_argument('-n', '--dry', action='store_true', help='Dry-run')
    parser.add_argument('-y', '--accept-all', action='store_true',
                        help='Do not prompt before applying migrations')
    parser.add_argument('-f', '--fake', action='store_true',
                        help='Skip migrations and register them as applied')
    parser.add_argument('-r', '--skip-register', action='store_true',
                        help='Skip registering applied migrations')
    parser.add_argument('--show', action='store_true',
                        help='Show all migrations applied')
    parser.add_argument('-t', '--transactional', action='store_true',
                        help='Run every migration as a single transaction')
    parser.add_argument('--ignore-applied', action='store_true',
                        help='Ignore previously applied migrations')
    args = parser.parse_args()

    # TODO: Implement -t flag behavior
    if args.transactional:
        raise NotImplementedError('This feature has not been implemented yet')

    arg_dict = {
        'migrations_dir': args.migrations_dir,
        'apply_migrations': not args.fake,
        'register_migrations': not args.skip_register,
        'dry_run': args.dry,
        'accept_all': args.accept_all,
        'ignore_applied': args.ignore_applied,
    }

    manager = Monarch(**arg_dict)
    manager.init_meta()

    if args.show:
        manager.show_migrations()
    elif args.migrate:
        manager.process_migration(args.migrate)
    elif args.all:
        manager.process_all_migrations()
    else:
        parser.parse_args(['--help'])


class Monarch:
    def __init__(self, migrations_dir, apply_migrations, register_migrations,
                 dry_run, accept_all, ignore_applied):
        """ Initialize Monarch manager object.

        :param migrations_dir: Directory to look into for migrations.
        :param apply_migrations: if True, apply migrations to db.
        :param register_migrations: If True, register migration to db.
        :param dry_run: If True, just show what would be run on the db.
        :param accept_all: If True, don't prompt for confirmation to migrate.
        :param ignore_applied: Ignore previously applied migrations.

        """
        self.migrations_dir = migrations_dir
        self.apply_migrations = apply_migrations
        self.register = register_migrations
        self.dry_run = dry_run
        self.accept_all = accept_all
        self.ignore_applied = ignore_applied
        if not all((_INTERNAL_DB_URL, _TARGET_DB_URL)):
            raise RuntimeError('Both INTERNAL_DB_URL and TARGET_DB_URL need '
                               'to be defined as var envs.')
        self.internal_db = create_engine(_INTERNAL_DB_URL)
        self.target_db = create_engine(_TARGET_DB_URL)

    def init_meta(self):
        # We use SQL Expression Language to initialize the internal db
        # in order to avoid problems with different type names across
        # different engines.
        metadata = MetaData()
        Table('migration', metadata,
              Column('id', Integer, primary_key=True),
              Column('name', String),
              Column('applied_on', DateTime, server_default=func.now()))
        metadata.create_all(self.internal_db)

    def process_migration(self, migration):
        """Processes a single migration.

      :param migration: migration to process.
      :returns: None
      :rtype: None

      """
        migrations_to_run = self.get_migrations_to_run(migration)
        self.run_migrations(migrations_to_run)

    def process_all_migrations(self):
        """Processes all available migrations.

            :returns:  None
            :rtype: None

            """
        available_migrations = self.get_available_migrations()
        candidates = []
        for migration in available_migrations:
            candidates += self.get_migrations_to_run(migration)
        # Remove duplicates after all the migrations have been processed
        # to lower time complexity.
        migrations_to_run = list(dict.fromkeys(candidates))
        self.run_migrations(migrations_to_run)

    def get_migrations_to_run(self, migration):
        """Returns a list of migrations to apply, solving dependencies.

        :param migration: migration to get dependencies from.
        :returns: list of migrations to run.
        :rtype: dict[]

        """
        migration_candidates = []
        self._solve_dependencies(migration, migration_candidates, seen=[])
        applied_migrations = (self.get_applied_migrations()
                                if not self.ignore_applied else [])
        migrations_to_run = [
            m for m in migration_candidates
            if m['name'] not in applied_migrations
        ]
        return migrations_to_run

    def get_applied_migrations(self):
        """Fetches a list of applied migrations from db.

      :returns: list of applied migrations.
      :rtype: string[]

      """
        with self.internal_db.begin() as conn:
            sql = 'SELECT name from migration;'
            migrations = conn.execute(sql).fetchall()
        return [m[0] for m in migrations]

    def get_available_migrations(self):
        """Returns a set of migrations available.

        :returns: list of migrations available
        :rtype: string[]

        """
        migrations = set()
        for f in listdir(self.migrations_dir):
            if (isfile(
                    join(self.migrations_dir, f)
            ) and splitext(f)[-1]) == '.sql':
                migrations.add(f)
        return migrations

    def run_migrations(self, migrations):
        """Applies a list of migrations to db.

      :param migration: migration to process.
      :returns: None
      :rtype: None

      """
        for migration in migrations:
            name = migration['name']
            migration['script'] = self.get_sql_script(name)

        if self.dry_run:
            for migration in migrations:
                print(f'---------------- {migration["name"]} ----------------')
                print(migration['script'])
            return

        if not self.accept_all and not self.prompt_for_migrations(migrations):
            return

        applied_migrations = []
        with self.target_db.begin() as conn:
            for migration in migrations:
                name = migration['name']
                script = migration['script']
                if self.apply_migrations:
                    print(f'Applying {name}')
                    conn.execute(script)
                applied_migrations.append(name)
            if self.register:
                self.register_migrations(applied_migrations)

    def register_migrations(self, migrations):
        """Registers a list of migrations on the db.

      :param migrations: List of migrations to register.
      :returns: None
      :rtype: None

      """
        with self.internal_db.begin() as conn:
            for migration in migrations:
                conn.execute(
                    'INSERT INTO migration (name) '
                    'VALUES (\'%s\');' % migration
                )

    def get_sql_script(self, migration):
        """Gets sql script from a migration.

      :param migration: migration to extract content from.
      :returns: a sql script.
      :rtype: string

      """
        with open(join(self.migrations_dir, migration), 'r') as f:
            sql = " ".join(f.readlines())
        return sql

    def _solve_dependencies(self, migration, resolved, seen=None):
        """Recursively solves dependency tree.

      We use two auxiliary
      accumulators: resolved and seen. A migration is considered
      resolved when all its dependencies have been solved. A
      circular dependency is discovered when a a migration has
      already been walked through but its still not resolved

      :param migration: migration to solve dependencies for.
      :param resolved: aux accumulator. Traces solved dependencies.
      :param seen: aux accumulator. Traces traversed depenencies.
      :returns: None
      :rtype: None
      """
        if seen is None:
            seen = []
        seen.append({'name': migration})
        commands = self.parse_header(migration)
        for dependency in commands.get('depends_on', []):
            if dependency not in {m['name'] for m in resolved}:
                if dependency in {m['name'] for m in seen}:
                    raise ValueError(
                        f'Circular dependency detected '
                        '"{migration, dependency}"'
                    )
                self._solve_dependencies(dependency, resolved, seen)
        resolved.append({'name': migration, **commands})

    def parse_header(self, migration):
        """Parses a migration header to be able to apply monarch's commands.

      :param migration: migration to parse header from.
      :returns: dictionary with commands
      :rtype: dict

      """
        try:
            with open(join(self.migrations_dir, migration), 'r') as f:
                line = f.readline()
                if self.is_valid_command(line):
                    line = line[3:].strip()
                    try:
                        commands = json.loads(line)
                    except JSONDecodeError as error:
                        raise ValueError(
                            f'"{line}" in {migration} is not a '
                            'valid Monarch command'
                        ) from error
                    return commands
                return {}
        except Exception as error:
            raise RuntimeError(f'parsing headers for {migration} '
                               'failed') from error

    def is_valid_command(self, string):
        """Checks if a string is a valid Monarch command.

      :param string: string to verify.
      :returns: true or false
      :rtype: bool

      """
        return string[:3] == "--!"

    def prompt_for_migrations(self, migrations):
        """Asks for confirmation to apply the pending migrations.

      :param migrations: List of migrations to ask on.
      :returns: Whether to apply the migrations or not
      :rtype: bool

      """
        print(f'About to run {len(migrations)} on {_TARGET_DB_URL}')
        for m in migrations:
            print(m['name'])
        response = input('Proceed? (Y/n) ').strip().lower()
        print()
        return (not response) or (response[0] == 'y')

    def show_migrations(self):
        """Prints applied migrations.

      :returns: None
      :rtype: None

      """
        migrations = set(self.get_available_migrations())
        applied_migrations = self.get_applied_migrations()
        print('        MIGRATIONS        ')
        print('--------------------------')
        for migration in migrations:
            status = '✓' if migration in applied_migrations else '⨯'
            print(f'{status} {migration}')
        print(f'\n{len(applied_migrations)}/{len(migrations)} '
              'migrations applied')


if __name__ == '__main__':
    main()
