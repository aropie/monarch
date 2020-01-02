# Monarch

**M**igrati**ON** man**A**ge**R** with a bad a**C**ronym, du**H**

Over the last several projects I've worked, one of the main problems
I've encountered is managing databases throughout different
environments.  There are several migration managers out there, but all
of them are overly bloated as most of them rely on ORMs, and were an
overkill for what I really needed:
- Track the state of the DB in different environments.
- A DB-agnostic tool, providing flexibility to work on different DB engines.
- A simple way to transition from one DB state to another one.
- A sane way to manage in what order the migrations should be applied
  (other than the usual file-naming by numbers).

Hence, Monarch was created.


## Migrations
Migrations are single files that represent an atomic change to the DB's state.

  * **Migrations are always additive.** This means that once a migration is commited
  into Monarch, it shouldn't be modified, and changes can only be reverted through
  a new migration.

  * **Migrations can't contain BEGIN TRANSACTION/COMMIT statements.** Monarch takes care of
  each migration being a single transaction. If you think that something within a migration
  should be run as a single transaction, extract that bit as another migration.

  * **Dependencies must be declared at the header.** If a migration is not self-contained,
  i.e. it assumes a pre-existing state of the DB, all dependencies must be declared at the
  header. [More on this header later.](#header)

All migrations are looked for in the migrations dir, `migrations` by default.
This can be changed with the `-d` flag.


## Header
The header is where Monarch figures out how to handle the migration. A valid Monarch header
starts with `--!` and then the declaration which is json-formatted in the following manner:
`{command1: value, command2: value, ...}`.

The existing commands are all that follow:
  * **depends_on** Expects a list of srings, where each element is a migration that the current
  one depends on. Every dependency is listed as `path/to/migration/migration.sql`.

And that's all.

### Example migration
```sql
--! {"depends_on": ["start_up_db.sql", "delete_a_table.sql"]}

CREATE TABLE person(
   id INTEGER,
   name VARCHAR(80),
   PRIMARY KEY(id)
);
```

## Monarch.py

monarch.py is the actual migration manager. Run it
through `python3 monarch.py`. It automatically computes and processess
all needed migration dependencies.
``` usage:
usage: monarch.py [-h] [-m MIGRATE] [-n] [-y] [-f] [-r] [--show] [-c [CONFIG]]

Simple db migration manager

optional arguments:
  -h, --help            show this help message and exit
  -m MIGRATE, --migrate MIGRATE
                        Migration file to run
  -d MIGRATIONS_DIR, --migrations-dir MIGRATIONS_DIR
     		     	Migrations directory
  -n, --dry             Dry-run
  -y, --accept-all      Do not prompt before applying migrations
  -f, --fake            Skip migrations and register them as applied
  -r, --skip-register   Skip registering applied migrations
  --show                Show all migrations applied
  -c [CONFIG], --config [CONFIG]
                        Config file to use
  -t, --transactional   Run every migration as a single transaction
  --ignore_applied      Ignore previously applied migrations
```

Also, is important to note that Monarch runs all the migrations requested (be it a single migration
and its dependencies or a whole schema) as a single transaction. This means that if you are applying
migrations 1 through 5 and no. 3 breaks the DB state, all changes are rolled back and none of the 5 migrations
are applied. To override this behavior, run the migration with `-t`. With the `-t` flag, if migration
3 breaks the DB state, migrations 1 and 2 will already be applied and saved.

Monarch saves the current DB state through a `migrations` table, in order to know which migrations
are needed to be applied in order to move from one state to another. You can make Monarch ignore
previously applied migrations with `-ignore-applied`, and avoid new migrations being registered
into the DB with `-skip-register`, or only register migrations without actually applying them with
`--fake`.

## Database connection
Monarch functions on two different databases: an internal one to save the applied migrations, and
a target database, which is the one where the migrations will actually be applied.

One of the objectives of Monarch is to be database-agnostic.
Internally, Monarch uses SQLAlchemy to handle the connections with the databases.
This means that [all the databases supported by SQLAlchemy](https://docs.sqlalchemy.org/en/13/core/engines.html#supported-databases)
are supported by Monarch as well, which covers all of the most common DB choices
(MySQL, PostgreSQL, SQLite, Oracle, Microsoft SQL Server).

To configure the database connections, [a database url](https://docs.sqlalchemy.org/en/13/core/engines.html#database-urls)
is used,which is defined through environment variables.
Simply set `INTERNAL_DB_URL` and `TARGET_DB_URL` and you're ready to go:
```
# Both of these could point to the same db.
export INTERNAL_DB_URL='sqlite:///internal.db'
export TARGET_DB_URL='postgresql://postgres:@localhost'
```
