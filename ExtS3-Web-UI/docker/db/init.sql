CREATE SCHEMA IF NOT EXISTS admin;

CREATE TABLE IF NOT EXISTS admin.users (
    id TEXT PRIMARY KEY,
    password TEXT NOT NULL
);

INSERT INTO admin.users (id, password)
VALUES ('example_admin_user', 'example_admin_password')
ON CONFLICT (id) DO UPDATE
SET password = EXCLUDED.password;

CREATE TABLE IF NOT EXISTS admin.pending_files (
    id SERIAL PRIMARY KEY,
    name TEXT,
    browser TEXT,
    version TEXT,
    source_path TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
