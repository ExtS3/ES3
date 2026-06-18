CREATE SCHEMA IF NOT EXISTS admin;

CREATE TABLE IF NOT EXISTS admin.schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin.users (
    id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    must_change_credentials BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'admin'
          AND table_name = 'users'
          AND column_name = 'password'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'admin'
          AND table_name = 'users'
          AND column_name = 'password_hash'
    ) THEN
        ALTER TABLE admin.users RENAME COLUMN password TO password_hash;
    END IF;
END $$;

ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS username TEXT;
UPDATE admin.users SET username = id WHERE username IS NULL;
ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS must_change_credentials BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE admin.users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE admin.users ALTER COLUMN password_hash SET NOT NULL;

CREATE TABLE IF NOT EXISTS admin.roles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin.permissions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin.user_roles (
    user_id TEXT NOT NULL REFERENCES admin.users(id) ON UPDATE CASCADE ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES admin.roles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS admin.role_permissions (
    role_id BIGINT NOT NULL REFERENCES admin.roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES admin.permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS admin.user_permissions (
    user_id TEXT NOT NULL REFERENCES admin.users(id) ON UPDATE CASCADE ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES admin.permissions(id) ON DELETE CASCADE,
    granted BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, permission_id)
);

ALTER TABLE admin.user_permissions ADD COLUMN IF NOT EXISTS granted BOOLEAN NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS admin.signup_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    requested_roles TEXT[] NOT NULL DEFAULT ARRAY['user']::TEXT[],
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    decided_by TEXT
);

INSERT INTO admin.permissions (name, description)
VALUES
    ('upload', 'Upload extension files'),
    ('delete_user', 'Delete users'),
    ('manage_extension_policy', 'Manage extension review policy'),
    ('request_extension', 'Request extension review'),
    ('bypass_holding', 'Bypass extension holding period'),
    ('install_extension', 'Install approved extensions'),
    ('approve_extension', 'Approve or reject reviewed extensions'),
    ('approve_signup', 'Approve signup requests')
ON CONFLICT (name) DO NOTHING;

INSERT INTO admin.roles (name, description)
VALUES
    ('admin', 'System administrator'),
    ('user', 'General user'),
    ('department_security', 'Security department user'),
    ('department_it', 'IT department user'),
    ('department_ops', 'Operations department user')
ON CONFLICT (name) DO NOTHING;

INSERT INTO admin.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM admin.roles r
CROSS JOIN admin.permissions p
WHERE r.name = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO admin.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM admin.roles r
JOIN admin.permissions p ON p.name = ANY(ARRAY['request_extension', 'upload', 'install_extension']::TEXT[])
WHERE r.name IN ('user', 'department_security', 'department_it', 'department_ops')
ON CONFLICT DO NOTHING;
