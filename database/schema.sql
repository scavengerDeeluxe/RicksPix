PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS photos (
 id TEXT PRIMARY KEY,
 source_path TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 category TEXT NOT NULL DEFAULT 'Uncategorized',
 subcategory TEXT,
 captured_at TEXT,
 season TEXT,
 camera_make TEXT,
 camera_model TEXT,
 image_key TEXT NOT NULL,
 thumb_key TEXT NOT NULL,
 quality_score INTEGER CHECK(quality_score BETWEEN 1 AND 10),
 ai_metadata TEXT NOT NULL DEFAULT '{}',
 exif_metadata TEXT NOT NULL DEFAULT '{}',
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_photos_published_category ON photos(published, category);
CREATE INDEX IF NOT EXISTS idx_photos_captured ON photos(captured_at);
CREATE TABLE IF NOT EXISTS photo_likes (
 photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
 visitor_hash TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(photo_id, visitor_hash)
);
CREATE TABLE IF NOT EXISTS photo_views (
 photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
 day TEXT NOT NULL,
 views INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(photo_id, day)
);
