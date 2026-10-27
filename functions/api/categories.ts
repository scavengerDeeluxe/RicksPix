import { GALLERY_CATEGORY_SQL } from './photos';

interface Env { DB: D1Database; }

// Return all categories in the published archive. Do not infer available
// categories from the first page of photos.
export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  const sql = `SELECT (${GALLERY_CATEGORY_SQL}) AS category, COUNT(*) AS total
    FROM photos p WHERE p.published = 1
    GROUP BY (${GALLERY_CATEGORY_SQL})
    ORDER BY total DESC, category ASC`;
  const result = await env.DB.prepare(sql).all<{ category: string; total: number }>();
  return Response.json({ categories: (result.results || []).filter(x => x.category) },
    { headers: { 'Cache-Control': 'public, max-age=120' } });
};
