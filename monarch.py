#!/usr/bin/env python3
from enum import Enum
from json.decoder import JSONDecodeError
from argparse import ArgumentParser
import json
import yaml


class DBEngine(Enum):
    SQLITE = 1
    POSTGRES = 2


# TODO: add config file
_INIT_MIGRATION = 'migrations/meta.sql'
_INTERNAL_DB_FILE = 'monarch.sql'
_INTERNAL_DB_ENGINE = DBEngine.SQLITE
_TARGET_DB_ENGINE = DBEngine.POSTGRES


def main():
    parser = ArgumentParser(description='Simple db migrations manager')
    parser.add_argument('-m', '--migrate', help='Migration file to run')
    parser.add_argument('-n', '--dry', action='store_true', help='Dry-run')
    parser.add_argument('-y', '--accept-all', action='store_true',
                        help='Do not prompt before applying migrations')
    parser.add_argument('-f', '--fake', action='store_true',
                        help='Skip migrations and register them as applied')
    parser.add_argument('-r', '--skip-register', action='store_true',
                        help='Skip registering applied migrations')
    parser.add_argument('--show', action='store_true',
                        help='Show all migrations applied')
    args = parser.parse_args()
    arg_dict = {
        'config_file': 'config.yaml',
        'apply_migrations': not args.fake,
        'register_migrations': not args.skip_register,
        'dry_run': args.dry,
        'accept_all': args.accept_all,
    }

    manager = Monarch(**arg_dict)
    manager.init_meta()

    if args.show:
        manager.show_migrations()
    elif args.migrate:
        manager.process_migration(args.migrate)
    else:
        parser.parse_args(['--help'])


class Monarch:
    def __init__(self, config_file, apply_migrations, register_migrations,
                 dry_run, accept_all):
        """ Initialize Monarch manager object.

        :param config_file: Yaml config file.
        :param apply_migrations: if True, apply migrations to db.
        :param register_migrations: If True, register migration to db.
        :param dry_run: If True, just show what would be run on the db.
        :param accept_all: If True, don't prompt for confirmation to migrate.


        """
        def parse_config():
            with open(config_file) as f:
                config = yaml.load(f, Loader=yaml.Loader)
            engines = config['engines']
            for db in ('internal_db', 'target_db'):
                db_dict = engines[config['config'][db]]
                if 'sqlite' in db_dict:
                    db_settings = {
                        'engine': DBEngine.SQLITE,
                        'connection': db_dict['sqlite'],
                    }
                elif'postgresql' in db_dict:
                    db_settings = {
                        'engine': DBEngine.POSTGRES,
                        'connection': db_dict['postgresql'],
                    }
                else:
                    raise ValueError('Db bad config')
                setattr(self, db, db_settings)

        self.apply_migrations = apply_migrations
        self.register_migrations = register_migrations
        self.dry_run = dry_run
        self.accept_all = accept_all
        parse_config()

    def init_meta(self):
        # TODO: add try-except
        connection = self.get_db_connection(internal=True)
        with connection:
            curs = connection.cursor()
            script = self.get_sql_script(_INIT_MIGRATION)
            curs.execute(script)
            connection.commit()

    def process_migration(self, migration):
        """Processes. a single migration.

      :param migration: migration to process.
      :returns: None
      :rtype: None

      """
        migrations_to_run = self.get_migrations_to_run(migration)
        self.run_migrations(migrations_to_run)

    def get_migrations_to_run(self, migration):
        """Returns a list of migrations to apply, solving dependencies.

      :param migration: migration to get dependencies from.
      :returns: list of migrations to run.
      :rtype: dict[]

      """
        migration_candidates = []
        self._solve_dependencies(migration, migration_candidates, seen=[])
        applied_migrations = self.get_applied_migrations()
        migrations_to_run = [
            m for m in migration_candidates if m['name'] not in applied_migrations
        ]
        return migrations_to_run

    def get_applied_migrations(self):
        """Fetches a list of applied migrations from db.

      :returns: list of applied migrations.
      :rtype: string[]

      """
        # TODO: add try-except
        connection = self.get_db_connection(internal=True)
        with connection:
            cursor = connection.cursor()
            sql = 'SELECT name from migration;'
            cursor.execute(sql)
            migrations = cursor.fetchall()
        return [m[0] for m in migrations]

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
                print(f'------------------ {migration["name"]} ------------------')
                print(migration['script'])
            return

        if not self.accept_all and not self.prompt_for_migrations(migrations):
            return

        connection = self.get_db_connection()
        applied_migrations = []
        with connection:
            curs = connection.cursor()
            for migration in migrations:
                name = migration['name']
                script = migration['script']
                print('Applying {}'.format(name))
                if self.apply_migrations:
                    curs.execute(script)
                self.applied_migrations.append(name)
            connection.commit()
        if self.register:
            self.register_migrations(applied_migrations)

    def register_migrations(self, migrations):
        """Registers a list of migrations on the db.

      :param migrations: List of migrations to register.
      :returns: None
      :rtype: None

      """
        # TODO: add try-except
        connection = self.get_db_connection(internal=True)
        with connection:
            cursor = connection.cursor()
            for migration in migrations:
                cursor.execute(
                    'INSERT INTO migration (name) ' 'VALUES ("%s");' % migration
                )
            connection.commit()

    def get_db_connection(self, internal=False):
        """
      Returns a connection to the required db.

      :param internal: Whether the connection is for the internal db.
      :returns: A connection object.
      :rtype: Connection

      """
        # TODO: Improve this to be more flexible
        db_settings = self.internal_db if internal else self.target_db
        print(db_settings)
        if db_settings['engine'] == DBEngine.SQLITE:
            import sqlite3
            engine_module = sqlite3
        elif db_settings['engine'] == DBEngine.POSTGRES:
            import psycopg2
            engine_module = psycopg2
        try:
            conn = engine_module.connect(**db_settings['connection'])
        except Error as e:
            print(e)
        return conn

    def get_sql_script(self, migration):
        """Gets sql script from a migration.

      :param migration: migration to extract content from.
      :returns: a sql script.
      :rtype: string

      """
        with open(migration, 'r') as f:
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
                        f'Circular dependency detected ' "{migration, dependency}"
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
            with open(migration, 'r') as f:
                line = f.readline()
                if self.is_valid_command(line):
                    line = line[3:].strip()
                    try:
                        commands = json.loads(line)
                    except JSONDecodeError as error:
                        raise ValueError(
                            f'"{line}" in {migration} is not a valid Monarch command'
                        ) from error
                    return commands
                return {}
        except Exception as error:
            raise RuntimeError(f'parsing headers for {migration} failed') from error

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
        print(f'About to run {len(migrations)} on blah')
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
        migrations = self.get_applied_migrations()
        print('        MIGRATIONS        ')
        print('--------------------------')
        for migration in migrations:
            status = "✓"
            print(f'{status} {migration}')
        print(f'\n{len(migrations)} migrations applied')


if __name__ == '__main__':
    main()
