CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    bio             TEXT DEFAULT '',
    avatar_id       TEXT DEFAULT 'default',
    is_anonymous    INTEGER NOT NULL DEFAULT 0,
    is_dev          INTEGER NOT NULL DEFAULT 0,
    last_seen       REAL,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identity_pubkey     TEXT NOT NULL,
    identity_ed25519_pubkey TEXT NOT NULL,
    signed_prekey       TEXT NOT NULL,
    signed_prekey_sig   TEXT NOT NULL,
    registered_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS one_time_prekeys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    pubkey          TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_queue (
    id                      TEXT PRIMARY KEY,
    sender_id               TEXT NOT NULL,
    recipient_id            TEXT NOT NULL,
    sender_device_id        TEXT NOT NULL,
    recipient_device_id     TEXT NOT NULL,
    ciphertext              TEXT NOT NULL,
    header                  TEXT NOT NULL,
    is_prekey_message       INTEGER NOT NULL DEFAULT 0,
    group_id                TEXT,
    created_at              REAL NOT NULL,
    delivered               INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contacts (
    owner_id        TEXT NOT NULL,
    contact_id      TEXT NOT NULL,
    added_at        REAL NOT NULL,
    PRIMARY KEY (owner_id, contact_id)
);

CREATE TABLE IF NOT EXISTS groups (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    owner_id        TEXT NOT NULL,
    invite_token    TEXT UNIQUE NOT NULL,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id        TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    joined_at       REAL NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_queue_recipient ON message_queue(recipient_id, delivered);
CREATE INDEX IF NOT EXISTS idx_queue_group ON message_queue(group_id, delivered);
CREATE INDEX IF NOT EXISTS idx_prekeys_device ON one_time_prekeys(device_id, used);
CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);