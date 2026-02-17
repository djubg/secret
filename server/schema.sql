CREATE TABLE IF NOT EXISTS license_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    full_key TEXT UNIQUE,
    display_key TEXT NOT NULL UNIQUE,
    duration TEXT NOT NULL,
    status TEXT NOT NULL,
    hwid_hash TEXT,
    expires_at DATETIME,
    activated_at DATETIME,
    last_validated_at DATETIME,
    patreon_user_id TEXT,
    activation_count INTEGER NOT NULL DEFAULT 0,
    temporary_from_patreon BOOLEAN NOT NULL DEFAULT 0,
    notes TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_license_key_hash ON license_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_license_full_key ON license_keys (full_key);
CREATE INDEX IF NOT EXISTS idx_license_hwid_hash ON license_keys (hwid_hash);
CREATE INDEX IF NOT EXISTS idx_license_patreon_user_id ON license_keys (patreon_user_id);

CREATE TABLE IF NOT EXISTS patreon_subscriptions (
    id TEXT PRIMARY KEY,
    patreon_user_id TEXT NOT NULL UNIQUE,
    tier_name TEXT,
    patron_status TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 0,
    last_charge_status TEXT,
    last_checked_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_patreon_user_id ON patreon_subscriptions (patreon_user_id);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    avatar_preset TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    auth_token_hash TEXT,
    auth_token_expires_at DATETIME,
    last_login_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_auth_token_hash ON users (auth_token_hash);

CREATE TABLE IF NOT EXISTS user_license_links (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    license_id TEXT NOT NULL UNIQUE,
    linked_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_license_links_user_id ON user_license_links (user_id);
CREATE INDEX IF NOT EXISTS idx_user_license_links_license_id ON user_license_links (license_id);
