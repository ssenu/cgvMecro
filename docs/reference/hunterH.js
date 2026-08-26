(() => {
  if (window.top !== window.self) return;
  if (location.pathname !== '/cnm/selectVisitorCnt') return;
  if (window.__huntHRunning) return;
  window.__huntHRunning = 1;
  var KEY = '__huntH';
  function S() { try { return JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } }
  function save(o) { try { sessionStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  function bump(fn) { var s = S(); fn(s); save(s); return s; }
  if (S().done || S().held) return;
  ['__hunt', '__hunt2', '__hunt3', '__hunt4', '__hunt5', '__hunt6', '__hunt7', '__hunt8', '__hunt9', '__huntA', '__huntB', '__huntC', '__huntD', '__huntE', '__huntF', '__huntG'].forEach(function (k) {
    try { sessionStorage.setItem(k, JSON.stringify({ done: 1, retired: 1 })); } catch (e) {}
  });

  var LIGHT = '/api/v1/booking/searchMovScnInfo?coCd=A420&custNo=289044670&siteNo=0013&scnYmd=20260823&scnsNo=018&scnSseq=6&rtctlScopCd=08';
  var PATH = '/cnm/selectVisitorCnt';
  var POLL = 1000;
  var STOP = false;
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var now = function () { return new Date().toTimeString().slice(0, 8); };
  var score = function (row, num) { return Math.abs((row.charCodeAt(0) - 65) - 8) * 2 + Math.abs(num - 23); };
  var tc = function (b) { return (b.textContent || '').replace(/\s+/g, ''); };
  var btns = function () { return [].slice.call(document.querySelectorAll('button')); };
  var modals = function () { return [].slice.call(document.querySelectorAll('.cgv-modal.active')); };

  function seatHeld() {
    try { return document.body.innerText.indexOf('선택하신 좌석') >= 0; } catch (e) { return false; }
  }
  function halt(reason, extra) {
    STOP = true;
    window.__huntHRunning = 2;
    bump(function (s) {
      s.done = 1; s.held = 1; s.haltReason = reason; s.haltAt = now();
      if (extra) Object.keys(extra).forEach(function (k) { s[k] = extra[k]; });
    });
  }
  function dead() { return STOP || S().done || S().held; }
  function closeModals() {
    modals().forEach(function (m) {
      [].slice.call(m.querySelectorAll('button')).filter(function (x) { return /확인|닫기/.test(x.textContent); }).forEach(function (x) { x.click(); });
    });
  }
  var SEED = ['K16','K17','K18','K19'];
  function bl() { var b = {}; SEED.concat(S().black || []).forEach(function (x) { b[x] = 1; }); return b; }
  function cta() { return btns().filter(function (x) { return !x.disabled && /선택완료/.test(tc(x)); }); }

  function setCount() {
    var w = document.querySelector('div.numberChoice_NumberWrap__JKTv1');
    if (!w) return false;
    var b = w.querySelector('button[aria-label="1 선택"]');
    if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
    return true;
  }

  function scan() {
    var b = bl(), map = {};
    [].slice.call(document.querySelectorAll('button[data-seatlocno]')).forEach(function (x) {
      if (x.disabled) return;
      var t = x.textContent.trim();
      if (!/^[A-P]\d{1,2}$/.test(t) || b[t] || map[t]) return;
      if (x.getBoundingClientRect().width <= 0) return;
      map[t] = x;
    });
    var free = Object.keys(map), out = [];
    free.forEach(function (t) {
      if (/^[ABC]/.test(t)) return;
      var row = t[0], n = parseInt(t.slice(1), 10);
      out.push({ a: t, el: map[t], sc: score(row, n) });
    });
    out.sort(function (x, y) { return x.sc - y.sc; });
    return { cands: out, free: free };
  }

  // returns 'won' | 'held' | 'lost' | 'skip'
  async function book(p) {
    var t0 = Date.now();
    setCount(); await sleep(40);
    p.el.click();

    var clicked = false;
    for (var k = 0; k < 70; k++) {
      if (modals().length) {
        if (/휠체어|장애인/.test(modals()[0].textContent)) bump(function (s) { s.black = (s.black || []).concat([p.a]); });
        closeModals(); await sleep(200);
        return 'skip';
      }
      var c = cta();
      if (c.length) { c[0].click(); clicked = true; bump(function (s) { s.ctaMs = Date.now() - t0; }); break; }
      await sleep(40);
    }

    for (var m = 0; m < 90; m++) {
      await sleep(100);
      if (location.pathname !== PATH) {
        halt('arrived-payment', { picked: [p.a], pickedAt: now(), dest: location.pathname, totalMs: Date.now() - t0 });
        return 'won';
      }
    }

    var stable = 0;
    for (var q = 0; q < 50; q++) {
      if (!seatHeld()) { stable = 0; break; }
      stable++;
      if (stable >= 40) break;
      await sleep(300);
    }
    if (stable >= 40) {
      halt('seat-held-no-nav', { picked: [p.a], pickedAt: now(), totalMs: Date.now() - t0 });
      return 'held';
    }
    bump(function (s) {
      s.lost = (s.lost || []).concat([now() + ' ' + p.a + (clicked ? ' cta' : ' nocta') + ' ' + (Date.now() - t0) + 'ms']).slice(-10);
    });
    closeModals();
    return 'lost';
  }

  async function attempt() {
    var sc = scan();
    bump(function (s) { s.free = sc.free; s.seen = (s.seen || []).concat([now() + ' [' + sc.free.join(',') + ']']).slice(-25); });
    for (var i = 0; i < sc.cands.length; i++) {
      if (dead()) return 'stop';
      bump(function (s) { s.hits = (s.hits || []).concat([now() + ' ' + sc.cands[i].a]).slice(-12); });
      var r = await book(sc.cands[i]);
      if (r === 'won' || r === 'held') return r;
    }
    return 'none';
  }

  async function main() {
    for (var i = 0; i < 500; i++) {
      if (document.querySelector('div.numberChoice_NumberWrap__JKTv1') && document.querySelectorAll('button[data-seatlocno]').length > 100) break;
      await sleep(40);
    }
    await sleep(60);
    if (seatHeld()) { halt('already-held-on-load'); return; }

    setCount(); await sleep(90);
    bump(function (s) { s.loads = (s.loads || 0) + 1; s.at = Date.now(); });

    var r = await attempt();
    if (r === 'won' || r === 'held' || dead()) return;

    var lastFr = -1, e429 = 0;
    while (!dead()) {
      if (seatHeld()) { halt('held-detected-in-loop'); return; }
      try {
        var resp = await fetch(LIGHT, { headers: { accept: 'application/json' } });
        if (resp.status === 429) {
          e429++;
          bump(function (s) { s.blocked = (s.blocked || 0) + 1; s.at = Date.now(); });
          await sleep(5000 + e429 * 2000);
          continue;
        }
        e429 = 0;
        var j = await resp.json();
        var d = j && j.data; if (Array.isArray(d)) d = d[0];
        var fr = d ? parseInt(d.frSeatCnt, 10) : NaN;
        bump(function (s) { s.polls = (s.polls || 0) + 1; s.fr = fr; s.at = Date.now(); });
        if (!isNaN(fr)) {
          if (lastFr >= 0 && fr > lastFr) {
            if (dead() || seatHeld()) { halt('held-guard-before-reload'); return; }
            bump(function (s) { s.trig = (s.trig || []).concat([now() + ' fr ' + lastFr + '->' + fr]).slice(-12); });
            location.reload();
            return;
          }
          lastFr = fr;
        }
      } catch (e) { bump(function (s) { s.err = String(e).slice(0, 80); }); }
      await sleep(POLL);
    }
  }

  if (document.readyState === 'complete') main();
  else window.addEventListener('load', function () { setTimeout(main, 200); });
})();
