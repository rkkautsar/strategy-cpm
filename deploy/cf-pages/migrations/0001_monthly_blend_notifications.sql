CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  blend_json TEXT,
  pending_blend_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'unsubscribed')),
  confirm_token_hash TEXT,
  confirmation_sent_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS subscriptions_status_idx ON subscriptions(status);

CREATE TABLE IF NOT EXISTS deliveries (
  subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
  month TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  resend_id TEXT,
  PRIMARY KEY (subscription_id, month)
);
