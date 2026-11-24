CREATE TABLE IF NOT EXISTS review_record (
 id TEXT PRIMARY KEY NOT NULL, kind TEXT NOT NULL, target_id TEXT NOT NULL,
 author TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(kind,target_id)
);
CREATE TABLE IF NOT EXISTS render_job (
 id TEXT PRIMARY KEY NOT NULL, author TEXT NOT NULL, status TEXT NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS article_status ON article(status);
CREATE INDEX IF NOT EXISTS snapshot_mode ON snapshot(mode);
CREATE INDEX IF NOT EXISTS review_status ON review_record(status);
CREATE INDEX IF NOT EXISTS render_status ON render_job(status);
