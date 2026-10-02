import sqlite3
import tempfile
import unittest
from pathlib import Path
from wallet_database_colour import prepare_number_colour

class DatabaseColourTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name); self.source = self.root/'source.sqlite'; self.output = self.root/'output.sqlite'
        self.db = sqlite3.connect(self.source)
        self.db.execute('CREATE TABLE PASS (UNIQUE_ID TEXT, FOREGROUND_COLOR TEXT, LABEL_COLOR TEXT, PRIMARY_ACCOUNT_SUFFIX TEXT, EXTRA BLOB)')
        self.db.executemany('INSERT INTO PASS VALUES (?,?,?,?,?)', [('card=', 'rgb(255,255,255)', 'rgb(100,100,100)', '1234', b'keep'), ('other=', 'rgb(255,255,255)', 'rgb(90,90,90)', '5678', b'other')])
        self.db.execute('CREATE TABLE TRANSACTIONS (VALUE TEXT)'); self.db.execute("INSERT INTO TRANSACTIONS VALUES ('preserve')"); self.db.commit()
    def tearDown(self): self.db.close(); self.temp.cleanup()
    def apply(self): return prepare_number_colour(self.source, self.output, 'card=', 'black')
    def test_changes_only_one_colour_source_is_unchanged(self):
        original=self.source.read_bytes(); result=self.apply()
        with sqlite3.connect(self.output) as db:
            self.assertEqual(db.execute("SELECT * FROM PASS WHERE UNIQUE_ID='card='").fetchone(), ('card=', 'rgb(0,0,0)', 'rgb(100,100,100)', '1234', b'keep'))
            self.assertEqual(db.execute("SELECT * FROM PASS WHERE UNIQUE_ID='other='").fetchone(), self.db.execute("SELECT * FROM PASS WHERE UNIQUE_ID='other='").fetchone())
            self.assertEqual(db.execute('SELECT * FROM TRANSACTIONS').fetchall(), [('preserve',)])
        self.assertEqual(self.source.read_bytes(), original); self.assertFalse(result['applied_to_phone'])
    def test_missing_card_refused(self):
        with self.assertRaises(ValueError): prepare_number_colour(self.source,self.output,'missing','black')
        self.assertFalse(self.output.exists())
    def test_duplicate_card_refused(self):
        self.db.execute("INSERT INTO PASS SELECT * FROM PASS WHERE UNIQUE_ID='card='"); self.db.commit()
        with self.assertRaises(ValueError): self.apply()
        self.assertFalse(self.output.exists())
    def test_unknown_encoding_refused(self):
        self.db.execute("UPDATE PASS SET FOREGROUND_COLOR='encoded' WHERE UNIQUE_ID='card='"); self.db.commit()
        with self.assertRaises(ValueError): self.apply()
    def test_trigger_other_field_change_rolls_back(self):
        self.db.execute("CREATE TRIGGER bad AFTER UPDATE ON PASS BEGIN UPDATE PASS SET PRIMARY_ACCOUNT_SUFFIX='0000' WHERE UNIQUE_ID=NEW.UNIQUE_ID; END;"); self.db.commit()
        with self.assertRaisesRegex(ValueError,'other data'): self.apply()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.db.execute("SELECT PRIMARY_ACCOUNT_SUFFIX FROM PASS WHERE UNIQUE_ID='card='").fetchone(),('1234',))
    def test_trigger_other_table_change_refused(self):
        self.db.execute("CREATE TRIGGER bad AFTER UPDATE ON PASS BEGIN INSERT INTO TRANSACTIONS VALUES ('bad'); END;"); self.db.commit()
        with self.assertRaises(ValueError): self.apply()
        self.assertFalse(self.output.exists())
    def test_existing_output_preserved(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.output.read_bytes(),b'keep')
    def test_live_local_wal_snapshot(self):
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute("UPDATE PASS SET EXTRA=X'0102' WHERE UNIQUE_ID='card='"); self.db.commit()
        self.apply()
        with sqlite3.connect(self.output) as db: self.assertEqual(db.execute("SELECT EXTRA FROM PASS WHERE UNIQUE_ID='card='").fetchone(),(b'\x01\x02',))
    def test_wrong_schema_refused(self):
        self.db.execute('ALTER TABLE PASS RENAME COLUMN FOREGROUND_COLOR TO UNKNOWN'); self.db.commit()
        with self.assertRaises(ValueError): self.apply()
