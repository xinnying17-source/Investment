// Automated smoke test for the investing guide. Used by the nightly maintenance task.
// Run: node tests/smoke.js            (uses the Playwright + Chromium preinstalled in the cloud session)
// Exit code 0 = pass, 1 = failures (printed).
const fs = require('fs'), path = require('path'), os = require('os');
const { chromium } = require('playwright');
const ROOT = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'investment-guide.html'), 'utf8');
const tmp = path.join(os.tmpdir(), 'ig-smoke.html');
fs.writeFileSync(tmp, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>[hidden]{display:none!important}</style>' + src + '</html>');
(async () => {
  const fails = [];
  const b = await chromium.launch();
  for (const vp of [{ width: 1280, height: 900 }, { width: 390, height: 800 }]) {
    const p = await b.newPage({ viewport: vp });
    p.on('pageerror', e => fails.push(`[${vp.width}] page error: ${e.message}`));
    await p.goto('file://' + tmp); await p.waitForTimeout(600);
    for (const L of ['zh', 'en']) {
      const r = await p.evaluate(lang => {
        const out = []; setLang(lang);
        for (const c of C) {
          if (!EXTRA[c[0]]) out.push('missing EXTRA ' + c[0]);
          if (!C_EN[c[0]] || !EXTRA_EN[c[0]]) out.push('missing English ' + c[0]);
          else if (EXTRA_EN[c[0]].cases.length !== EXTRA[c[0]].cases.length) out.push('case count mismatch ' + c[0]);
          try { openCard(c[0]); for (const t of ['intro', 'deep', 'cases', 'drills']) document.querySelector('.ltab[data-t="' + t + '"]').click(); } catch (e) { out.push('card ' + c[0] + ': ' + e.message); }
        }
        closeCard();
        for (const v of VIEWS) { try { show(v); } catch (e) { out.push('view ' + v + ': ' + e.message); } if (document.documentElement.scrollWidth > innerWidth + 1) out.push('horizontal overflow in ' + v); }
        for (const sc of [['classic', 60], ['random', 36], ['random', 120]]) {
          S.sim = null; newSim({ scen: sc[0], n: sc[1], start: 20000, contrib: 500, dca: true, tpl: 'balanced', goal: 'beat', coach: true, autoReb: true });
          for (let i = 0; i < 130; i++) advance(); renderSim();
          const s = S.sim; if (!s.done) out.push('sim not finished ' + sc); if (!isFinite(s.hn[s.n]) || s.cash < -1) out.push('sim numbers broken ' + sc);
          const etf = PATH.ETF.p[s.n] / PATH.ETF.p[0]; if (etf > 6 || etf < 0.2) out.push('unrealistic ETF path ' + etf.toFixed(2) + ' ' + sc);
        }
        try { buildPlan({ goal: 'basics', months: 3, dpw: 5 }); if (!S.plan2 || S.plan2.items.length < C.length) out.push('plan too short'); if (!todayItems().length) out.push('plan has nothing for today'); show('today'); if (!document.querySelector('#todayRoot .checklist')) out.push('today checklist missing'); show('me'); if (!document.querySelector('#meStats .kpis')) out.push('me stats missing'); openSettings(); if (!document.querySelector('#setBody [data-track]')) out.push('settings music missing'); closeSettings(); celebrate(); if (!icsText().includes('BEGIN:VEVENT')) out.push('calendar file broken'); } catch (e) { out.push('plan/today/me/settings: ' + e.message); }
        try { const id = C[0][0]; S.known[id] = true; S.marks = {}; toggleMark(id); if (!document.querySelector('.chip.marked[data-id="' + id + '"]')) out.push('bookmark not on map'); show('me'); if (!document.querySelector('#meMarks [data-mk="' + id + '"]')) out.push('bookmark not on me page'); todoMode = 'marked'; buildDeck(false); if (deck.length !== 1) out.push('bookmark deck wrong'); relearn(id); if (S.known[id] || !relearning(id)) out.push('relearn did not reset'); closeCard(); show('today'); if (!document.querySelector('#todayRoot [data-rl="' + id + '"]')) out.push('relearn not on today'); S.known[id] = true; updateProgress(); if (relearning(id)) out.push('relearn not cleared'); toggleMark(id); todoMode = 'all'; } catch (e) { out.push('marks/relearn: ' + e.message); }
        S.sim = null; return out;
      }, L);
      fails.push(...r.map(x => `[${vp.width} ${L}] ${x}`));
    }
    await p.close();
  }
  await b.close();
  const live = process.argv.includes('--live');
  if (live) {
    try { const r = await fetch('https://xinnying17-source.github.io/Investment/'); if (!r.ok) fails.push('live site HTTP ' + r.status); } catch (e) { fails.push('live site unreachable: ' + e.message); }
  }
  if (fails.length) { console.log('FAIL\n' + [...new Set(fails)].join('\n')); process.exit(1); }
  console.log('PASS: all lessons, views, languages and simulator modes OK');
})();
