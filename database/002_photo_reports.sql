CREATE TABLE IF NOT EXISTS photo_reports (
  photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  visitor_hash TEXT NOT NULL,
  reason TEXT NOT NULL CHECK(reason IN ('family','sensitive','other')),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reviewed','dismissed','removed')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(photo_id, visitor_hash)
);
CREATE INDEX IF NOT EXISTS idx_photo_reports_status ON photo_reports(status, created_at);
