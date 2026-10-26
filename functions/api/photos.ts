interface Env { DB: D1Database; IMAGE_BASE_URL: string; }
export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);
  const limit = Math.min(60, Math.max(1, Number(url.searchParams.get('limit')) || 24));
  const offset = Math.max(0, Number(url.searchParams.get('offset')) || 0);
  const category = url.searchParams.get('category')?.trim() || '';
  const where = "p.published = 1" + (category ? " AND p.category = ?" : "");
  const countSql = "SELECT COUNT(*) AS total FROM photos p WHERE " + where;
  const dataSql = "SELECT p.id,p.title,p.description,p.category,p.subcategory,p.captured_at,p.season,p.camera_model,p.quality_score,p.thumb_key,p.image_key,(SELECT COUNT(*) FROM photo_likes l WHERE l.photo_id=p.id) AS likes FROM photos p WHERE " + where + " ORDER BY COALESCE(p.quality_score,0) DESC,p.captured_at DESC,p.id LIMIT ? OFFSET ?";
  const countQuery = env.DB.prepare(countSql);
  const dataQuery = env.DB.prepare(dataSql);
  const total = await (category ? countQuery.bind(category) : countQuery).first<{ total: number }>();
  const rows = await (category ? dataQuery.bind(category,limit,offset) : dataQuery.bind(limit,offset)).all<Record<string, unknown>>();
  const base = (env.IMAGE_BASE_URL || 'https://images.rickspix.com').replace(/\/$/,'');
  const photos = rows.results.map(row => ({
    ...row,
    thumb_url: base + '/' + String(row.thumb_key).split('/').map(encodeURIComponent).join('/'),
    image_url: base + '/' + String(row.image_key).split('/').map(encodeURIComponent).join('/')
  }));
  return Response.json({ photos, total: total?.total || 0 }, {headers:{'Cache-Control':'public, max-age=30'}});
};
