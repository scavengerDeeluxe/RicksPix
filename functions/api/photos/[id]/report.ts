interface Env { DB: D1Database; LIKES_HASH_SECRET: string; }
const validReasons = new Set(['family','sensitive','other']);

async function hashVisitor(secret: string, visitor: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const sig = await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(visitor));
  return Array.from(new Uint8Array(sig)).map(n=>n.toString(16).padStart(2,'0')).join('');
}
export const onRequestPost: PagesFunction<Env, 'id'> = async ({request,env,params}) => {
  if (!env.LIKES_HASH_SECRET) return Response.json({error:'Reporting unavailable'},{status:503});
  const id = String(params.id);
  if (id.length > 128) return Response.json({error:'Invalid photo'},{status:400});
  let body: {visitor?:unknown;reason?:unknown};
  try { body=await request.json() as {visitor?:unknown;reason?:unknown}; }
  catch { return Response.json({error:'Invalid JSON'},{status:400}); }
  if (typeof body.visitor !== 'string' || !/^[0-9a-f-]{36}$/i.test(body.visitor))
    return Response.json({error:'Invalid visitor ID'},{status:400});
  if (typeof body.reason !== 'string' || !validReasons.has(body.reason))
    return Response.json({error:'Invalid reason'},{status:400});
  const exists=await env.DB.prepare('SELECT id FROM photos WHERE id=? AND published=1').bind(id).first();
  if (!exists) return Response.json({error:'Photo not found'},{status:404});
  const hash=await hashVisitor(env.LIKES_HASH_SECRET,body.visitor);
  await env.DB.prepare('INSERT OR IGNORE INTO photo_reports(photo_id,visitor_hash,reason) VALUES(?,?,?)')
    .bind(id,hash,body.reason).run();
  return Response.json({ok:true,message:'Thank you. This photograph has been flagged for review.'},
    {headers:{'Cache-Control':'no-store'}});
};
