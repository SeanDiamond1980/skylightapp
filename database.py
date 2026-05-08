import sqlite3
import os

# DATA_DIR env var lets cloud platforms point this at a persistent volume mount
_data_dir = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
DB_PATH = os.path.join(_data_dir, 'events.db')

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_subject TEXT,
            email_from TEXT,
            email_body TEXT,
            parsed_title TEXT,
            parsed_start TEXT,
            parsed_end TEXT,
            parsed_location TEXT,
            parsed_description TEXT,
            calendar_event_id TEXT,
            calendar_event_link TEXT,
            status TEXT DEFAULT 'pending',
            error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            source TEXT DEFAULT 'manual'
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    ''')
    conn.commit()
    return conn

def insert_event(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute('''
            INSERT INTO events
              (email_subject, email_from, email_body, parsed_title, parsed_start,
               parsed_end, parsed_location, parsed_description, calendar_event_id,
               calendar_event_link, status, error, source)
            VALUES
              (:email_subject, :email_from, :email_body, :parsed_title, :parsed_start,
               :parsed_end, :parsed_location, :parsed_description, :calendar_event_id,
               :calendar_event_link, :status, :error, :source)
        ''', data)
        return cur.lastrowid

def update_event(row_id: int, data: dict):
    set_clause = ', '.join(f'{k} = :{k}' for k in data)
    data['_id'] = row_id
    with get_conn() as conn:
        conn.execute(f'UPDATE events SET {set_clause} WHERE id = :_id', data)

def get_events(limit: int = 100) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM events ORDER BY created_at DESC LIMIT ?', (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

def get_event(row_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM events WHERE id = ?', (row_id,)).fetchone()
    return dict(row) if row else None

def get_setting(key: str, fallback=None) -> str | None:
    with get_conn() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else fallback

def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value)
        )
