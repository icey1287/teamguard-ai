"""Local course workspace. SQL submitted for review is stored, never executed."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from contracts import Decision, ReviewReport, Rulebook


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get(
            "TEAMGUARD_DB", str(Path(__file__).parent / "data" / "workspace.sqlite3")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rulebooks (
                    project_id TEXT NOT NULL, version INTEGER NOT NULL,
                    name TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (project_id, version));
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
                    created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM rulebooks ORDER BY name, version").fetchall()
        result = {}
        for row in rows:
            book = Rulebook.model_validate_json(row[0])
            result.setdefault(book.project_id, []).append(book)
        return result

    def save_rulebook(self, book):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM rulebooks WHERE project_id != ? AND name = ? COLLATE NOCASE",
                          (book.project_id, book.project_name)).fetchone():
                raise ValueError("A project with this name already exists.")
            latest = db.execute("SELECT MAX(version) FROM rulebooks WHERE project_id = ?",
                                (book.project_id,)).fetchone()[0] or 0
            if book.version != latest + 1:
                raise ValueError("This project changed in another session. Reload before saving.")
            db.execute("INSERT INTO rulebooks VALUES (?, ?, ?, ?)",
                       (book.project_id, book.version, book.project_name, book.model_dump_json()))

    def reports(self):
        with self.connection() as db:
            return [ReviewReport.model_validate_json(r[0]) for r in db.execute(
                "SELECT payload FROM reports ORDER BY created_at")]

    def save_report(self, report):
        with self.connection() as db:
            db.execute("INSERT INTO reports VALUES (?, ?, ?)",
                       (report.id, report.created_at.isoformat(), report.model_dump_json()))

    def decisions(self):
        with self.connection() as db:
            return [Decision.model_validate_json(r[0]) for r in db.execute(
                "SELECT payload FROM decisions ORDER BY created_at")]

    def save_decision(self, decision):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM reports WHERE id = ?", (decision.report_id,)).fetchone()
            if not row:
                raise ValueError("The report no longer exists.")
            report = ReviewReport.model_validate_json(row[0])
            if report.semantic_status != "completed" or not report.issues:
                raise ValueError("Only completed reports with findings can receive a decision.")
            db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?)",
                       (decision.id, decision.report_id, decision.created_at.isoformat(), decision.model_dump_json()))

    def save_evaluation(self, run):
        with self.connection() as db:
            db.execute("INSERT INTO evaluations VALUES (?, ?, ?)",
                       (run["id"], run["created_at"], json.dumps(run)))

    def evaluations(self):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM evaluations ORDER BY created_at DESC")]

    def update_evaluation(self, run):
        with self.connection() as db:
            db.execute("UPDATE evaluations SET payload = ? WHERE id = ?", (json.dumps(run), run["id"]))
