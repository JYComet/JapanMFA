import sqlite3
import subprocess
import threading
import time
from pathlib import Path

import pytest
from japanmfa.mfa.native_resident import sqlite_import_wait


def import_command(tmp_path):
    database = tmp_path / "corpus.db"
    owner = sqlite3.connect(database, check_same_thread=False)
    owner.execute("CREATE TABLE original(value)")
    owner.execute("INSERT INTO original VALUES (1)")
    owner.commit()
    owner.execute("BEGIN")
    owner.execute("SELECT * FROM original").fetchall()
    csv = tmp_path / "word_intervals.csv"
    csv.write_text("id,word\n1,jmfa_000001\n")
    command = ["sqlite3", str(database), "--cmd", ".mode csv", f'.import "{csv}" word_interval_temp']
    return database, owner, command


def test_real_import_waits_for_brief_reader_and_imports_exact_rows(tmp_path):
    database, owner, command = import_command(tmp_path)
    def release():
        time.sleep(.25)
        owner.commit()
    thread = threading.Thread(target=release)
    thread.start()
    try:
        with sqlite_import_wait(tmp_path):
            subprocess.check_call(command)
        with sqlite3.connect(database) as db:
            # CLI .import creates TEXT columns when the target table is absent.
            assert db.execute("SELECT * FROM word_interval_temp").fetchall() == [("1", "jmfa_000001")]
            assert db.execute("SELECT * FROM original").fetchall() == [(1,)]
    finally:
        thread.join()
        owner.close()


def test_persistent_lock_still_fails_within_bounded_wait(tmp_path):
    database, owner, command = import_command(tmp_path)
    begin = time.monotonic()
    try:
        with sqlite_import_wait(tmp_path), pytest.raises(subprocess.CalledProcessError):
            subprocess.check_call(command)
        assert 4.5 <= time.monotonic() - begin < 8
    finally:
        owner.rollback()
        owner.close()
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='word_interval_temp'").fetchall() == []


def test_foreign_database_not_changed_to_wait(tmp_path):
    own = tmp_path / "own"
    own.mkdir()
    database, owner, command = import_command(tmp_path)
    begin = time.monotonic()
    try:
        with sqlite_import_wait(own), pytest.raises(subprocess.CalledProcessError):
            subprocess.check_call(command)
        assert time.monotonic() - begin < 2
    finally:
        owner.rollback()
        owner.close()


def test_non_import_errors_and_original_function_are_preserved(tmp_path):
    original = subprocess.check_call
    with pytest.raises(RuntimeError):
        with sqlite_import_wait(tmp_path):
            with pytest.raises(subprocess.CalledProcessError):
                subprocess.check_call(["sqlite3", str(tmp_path / "bad.db"), "bad SQL"])
            raise RuntimeError("stop")
    assert subprocess.check_call is original
