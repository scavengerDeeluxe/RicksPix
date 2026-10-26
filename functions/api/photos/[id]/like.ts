interface Env { DB: D1Database; LIKES_HASH_SECRET: string; }
async function hashVisitor(secret: string, visitor: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const sig = await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(visitor));
  return Array.from(new Uint8Array(sig)).map(n => n.toString(16).padStart(2,'0')).join('');
}
export const onRequestPost: PagesFunction<Env, 'id'> = async ({ request, env, params }) => {
  if (!env.LIKES_HASH_SECRET) return Response.json({error:'Voting not configured'},{status:503});
  const id = String(params.id);
  if (id.length > 128) return Response.json({error:'Invalid photo'},{status:400});
  let body: {visitor?:unknown};
  try { body = await request.json() as {visitor?:unknown}; }
  catch { return Response.json({error:'Invalid JSON'},{status:400}); }
  const visitor = body.visitor;
  if (typeof visitor !== 'string' || !/^[0-9a-f-]{36}$/i.test(visitor)) return Response.json({error:'Invalid visitor ID'},{status:400});
  const existing = await env.DB.prepare('SELECT id FROM photos WHERE id=? AND published=1').bind(id).first();
  if (!existing) return Response.json({error:'Photo not found'},{status:404});
  const visitorHash = await hashVisitor(env.LIKES_HASH_SECRET,visitor);
  await env.DB.prepare('INSERT OR IGNORE INTO photo_likes(photo_id,visitor_hash) VALUES (?,?)').bind(id,visitorHash).run();
  const result = await env.DB.prepare('SELECT COUNT(*) AS likes FROM photo_likes WHERE photo_id=?').bind(id).first<{likes:number}>();
  return Response.json({likes:result?.likes||0},{headers:{'Cache-Control':'no-store'}});
};
