// Supabase Edge Function: daily study reminders via Web Push.
// GET  ?action=key  -> returns the VAPID public key (generated and stored on first use)
// POST (from pg_cron, header x-cron-secret) -> sends reminders to users whose local hour matches
// Deploy: Supabase Dashboard → Edge Functions → Deploy a new function → name "push-reminder" → paste this file.
// Then in the function's settings turn OFF "Enforce JWT verification" (the browser and the cron job call it without a login token).
import webpush from "npm:web-push@3.6.7";
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type, x-cron-secret", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { ...CORS, "Content-Type": "application/json" } });

async function getCfg(k: string) { const { data } = await sb.from("push_config").select("v").eq("k", k).maybeSingle(); return data?.v as string | undefined; }
async function vapid() {
  let pub = await getCfg("vapid_public"), priv = await getCfg("vapid_private");
  if (!pub || !priv) {
    const k = webpush.generateVAPIDKeys(); pub = k.publicKey; priv = k.privateKey;
    await sb.from("push_config").upsert([{ k: "vapid_public", v: pub }, { k: "vapid_private", v: priv }]);
  }
  return { pub, priv };
}
const MSG = {
  zh: [["📚 该学习了！", "今天的学习清单准备好了，花 10 分钟就能完成一项。"], ["🌱 每天进步一点点", "打开今日清单，继续你的投资学习计划。"], ["🔥 别让连续记录断掉", "今天还没打卡，来完成一项吧。"]],
  en: [["📚 Time to study!", "Today’s checklist is ready; one task takes about 10 minutes."], ["🌱 A little progress every day", "Open today’s list and keep your plan going."], ["🔥 Keep your streak alive", "You haven’t checked in today. Finish one task."]],
};
function localParts(tz: string) {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hour12: false, weekday: "short" });
  const p = Object.fromEntries(f.formatToParts(new Date()).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) % 24, wd: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(p.weekday) };
}
const okDay = (wd: number, dpw: number) => dpw === 7 || (dpw === 5 && wd >= 1 && wd <= 5) || (dpw === 3 && [1, 3, 5].includes(wd));

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(req.url);
  if (req.method === "GET" && url.searchParams.get("action") === "key") return json({ publicKey: (await vapid()).pub });
  if (req.method !== "POST") return json({ error: "not found" }, 404);
  if (req.headers.get("x-cron-secret") !== (await getCfg("cron_secret"))) return json({ error: "forbidden" }, 403);
  const { pub, priv } = await vapid();
  webpush.setVapidDetails("https://xinnying17-source.github.io/Investment/", pub, priv);
  const { data: subs } = await sb.from("push_subs").select("*");
  let sent = 0, removed = 0;
  for (const s of subs ?? []) {
    let lp; try { lp = localParts(s.tz || "Asia/Kuala_Lumpur"); } catch { lp = localParts("Asia/Kuala_Lumpur"); }
    if (lp.hour !== s.hour || !okDay(lp.wd, s.dpw) || s.last_sent === lp.date) continue;
    const list = (MSG as Record<string, string[][]>)[s.lang] ?? MSG.zh, m = list[new Date().getUTCDate() % list.length];
    try {
      await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } }, JSON.stringify({ title: m[0], body: m[1], url: "./#today" }));
      await sb.from("push_subs").update({ last_sent: lp.date }).eq("endpoint", s.endpoint); sent++;
    } catch (e) {
      const code = (e as { statusCode?: number }).statusCode;
      if (code === 404 || code === 410) { await sb.from("push_subs").delete().eq("endpoint", s.endpoint); removed++; }
    }
  }
  return json({ sent, removed });
});
