# python3

from os.path import join, relpath, splitext, isdir, dirname

_MIGRATIONS_DIR = 'migrations'
_INIT_MIGRATION = 'meta.sql'
_INTERNAL_DB_FILE = 'monarch.sql'

def main():
    init_meta()

def init_meta():
    process_migration(_INIT_MIGRATION)

def process_migration(migration):
    migrations_to_run = [{'name': migration}]
    run_migrations(migrations_to_run)


def run_migrations(migrations,
                 apply_migration=True,
                 register_migration=True):
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
    with connection:
        # if autocommit:
        #     connection.set_session(autocommit=True)
        curs = connection.cursor()
        for migration in migrations:
            name = migration['name']
            script = migration['script']
            try:
                print('Applying {}'.format(name))
                curs.execute(script)
            except Error as error:
                raise RuntimeError('failed processing {}'.format(name))
        connection.commit()

def get_db_connection():
    import sqlite3
    try:
        conn = sqlite3.connect(_INTERNAL_DB_FILE)
    except Error as e:
        print(e)
    return conn


def get_sql_script(migration):
    """Get sql script from a migration

    :param migration: migration to extract content from
    :returns: a sql script
    :rtype: string

    """
    with open(join(_MIGRATIONS_DIR, migration), 'r') as f:
        sql = " ".join(f.readlines())
    return sql


def get_migrations_available(dir_=_MIGRATIONS_DIR):
    """Return a list of migrations available

    :returns: list of migrations available
    :rtype: string[]

    """
    migrations = []
    for root, directory, filenames in walk(dir_):
        for f in filenames:
            if splitext(f)[1] == '.sql':
                migrations.append(f)
    return migrations




if __name__ == '__main__':
    main()
