"""Prepare a single-card number-colour change in a local Wallet database copy.

Never transfers or replaces a live device database. A transport must provide
an on-device SQLite transaction before this change can safely be applied.
"""
from __future__ import annotations
import hashlib
import os
import re
import sqlite3
from pathlib import Path

COLOURS = {'black': 'rgb(0,0,0)', 'white': 'rgb(255,255,255)'}


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def contents(db):
    """Full logical snapshot including unrelated tables, used to catch triggers."""
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name: sorted(db.execute('SELECT * FROM ' + quote(name)).fetchall(), key=repr) for name in tables}


def prepare_number_colour(source, output, card_id, colour):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_+=-]{1,128}', card_id):
        raise ValueError('Invalid card identifier.')
    if colour not in COLOURS:
        raise ValueError('Choose black or white.')
    if not source.is_file() or source == output or output.exists():
        raise ValueError('Choose an existing source and a new, separate output file.')
    if source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Database is larger than the supported limit.')
    # The backup API handles a local WAL snapshot through SQLite itself.
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)
    created = False
    db = None
    try:
        if src.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Source database integrity check failed.')
        tables = {r[0].upper(): r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        table = tables.get('PASS')
        if not table:
            raise ValueError('Unsupported schema: PASS table missing.')
        columns = {r[1].upper(): r[1] for r in src.execute('PRAGMA table_info(' + quote(table) + ')')}
        required = ('UNIQUE_ID', 'FOREGROUND_COLOR', 'PRIMARY_ACCOUNT_SUFFIX')
        if any(key not in columns for key in required):
            raise ValueError('Unsupported schema: card ID, foreground colour, or number suffix missing.')
        ident, foreground = columns['UNIQUE_ID'], columns['FOREGROUND_COLOR']
        rows = src.execute('SELECT * FROM ' + quote(table) + ' WHERE ' + quote(ident) + '=?', (card_id,)).fetchall()
        if len(rows) != 1:
            raise ValueError('Card identifier must match exactly one database row.')
        column_order = [r[1] for r in src.execute('PRAGMA table_info(' + quote(table) + ')')]
        index = column_order.index(foreground)
        old = rows[0][index]
        if not isinstance(old, str) or not re.fullmatch(r'rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)', old):
            raise ValueError('Unsupported colour encoding. No update made.')
        # Exclusive creation prevents accidentally replacing an existing deliverable.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd); created = True
        db = sqlite3.connect(output)
        src.backup(db)
        before = contents(db)
        schema = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        db.execute('BEGIN IMMEDIATE')
        sql = 'UPDATE ' + quote(table) + ' SET ' + quote(foreground) + '=? WHERE ' + quote(ident) + '=?'
        cursor = db.execute(sql, (COLOURS[colour], card_id))
        if cursor.rowcount != 1:
            raise ValueError('Unexpected number of updated rows.')
        expected_row = list(rows[0]); expected_row[index] = COLOURS[colour]
        expected = {name: list(values) for name, values in before.items()}
        expected[table].remove(rows[0]); expected[table].append(tuple(expected_row))
        expected[table].sort(key=repr)
        if contents(db) != expected:
            raise ValueError('Update changed other data (possibly a trigger). Aborting.')
        if db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall() != schema:
            raise ValueError('Schema changed unexpectedly.')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Output integrity check failed.')
        db.commit(); db.close(); db = None
        return {'ok': True, 'applied_to_phone': False, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'message': 'Prepared a local database copy changing only the matched card foreground colour. Not applied to the iPhone; a live database transaction is required.'}
    except Exception:
        if db is not None:
            db.rollback(); db.close(); db = None
        if created:
            output.unlink(missing_ok=True)
            for suffix in ('-wal','-shm','-journal'):
                Path(str(output)+suffix).unlink(missing_ok=True)
        raise
    finally:
        src.close()
