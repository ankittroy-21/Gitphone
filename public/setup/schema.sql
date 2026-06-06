-- ============================================================
-- GITPHONE MVP SCHEMA
-- Run this in your Supabase SQL editor (one time setup)
-- Database: YOUR central Supabase instance
-- All users share this DB, isolated by telegram_id
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TABLE: users
-- One row per registered developer
-- ============================================================
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  telegram_id     TEXT NOT NULL UNIQUE,
  github_token    TEXT NOT NULL,          -- plain text in MVP (AES-256 post MVP)
  default_repo    TEXT NOT NULL,          -- format: "username/repo-name"
  branch          TEXT NOT NULL DEFAULT 'main',
  timezone        TEXT NOT NULL DEFAULT 'UTC',
  schema_version  INT NOT NULL DEFAULT 1,
  last_active     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status          TEXT NOT NULL DEFAULT 'active',
                  -- values: active | inactive_7d | dormant
  ping_count      INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_last_active ON users(last_active);

-- ============================================================
-- TABLE: staged_files
-- Stores diffs waiting to be committed via Telegram bot
-- ============================================================
CREATE TABLE staged_files (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  telegram_id   TEXT NOT NULL,             -- denormalized for fast bot queries
  filepath      TEXT NOT NULL,             -- relative path from workspace root
  diff          TEXT,                      -- unified diff patch (NULL if binary)
  full_content  TEXT,                      -- base64 content (binary/new files)
  base_sha      TEXT NOT NULL,             -- git SHA diff was computed against
  is_binary     BOOLEAN NOT NULL DEFAULT FALSE,
  file_size     INT NOT NULL DEFAULT 0,    -- bytes
  status        TEXT NOT NULL DEFAULT 'pending',
                -- values: pending | committed | expired | conflict
  staged_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One pending diff per file per user (new save overwrites old diff)
CREATE UNIQUE INDEX idx_staged_files_unique_pending
  ON staged_files(user_id, filepath)
  WHERE status = 'pending';

CREATE INDEX idx_staged_files_user_status
  ON staged_files(user_id, status);

CREATE INDEX idx_staged_files_telegram_pending
  ON staged_files(telegram_id, status);

-- ============================================================
-- TABLE: commit_log
-- Audit trail of every successful commit via GitPhone
-- ============================================================
CREATE TABLE commit_log (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  telegram_id   TEXT NOT NULL,
  commit_sha    TEXT NOT NULL,
  message       TEXT NOT NULL,
  files         TEXT[] NOT NULL,           -- array of committed filepaths
  repo          TEXT NOT NULL,
  branch        TEXT NOT NULL DEFAULT 'main',
  was_scheduled BOOLEAN NOT NULL DEFAULT FALSE,
  committed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_commit_log_user ON commit_log(user_id, committed_at DESC);
CREATE INDEX idx_commit_log_telegram ON commit_log(telegram_id, committed_at DESC);
