/* Linha do tempo política do Brasil: script comum das páginas filhas.
   Sozinha: só aplica ?tema=claro|escuro. Dentro da página única (iframe):
   - marca <html class="embutida"> (some a barra de volta e o rodapé próprios);
   - informa a altura do documento ao pai (sem rolagem interna);
   - recebe do pai o trecho visível (--emb-y, --emb-b, --emb-vh) e reescreve, no CSS da página,
     unidades vh e elementos sticky/fixed para usarem esse trecho em vez da altura do iframe;
   - leva links entre páginas para a âncora da página única e repassa rolagens ao pai. */
(function () {
  'use strict';
  var d = document, de = d.documentElement, W = window;
  function tema(t) {
    if (t === 'claro') de.setAttribute('data-theme', 'light');
    else if (t === 'escuro') de.setAttribute('data-theme', 'dark');
    else de.removeAttribute('data-theme');
  }
  var q = /[?&]tema=(claro|escuro|auto)\b/.exec(location.search);
  if (q) tema(q[1]);

  var emb = false;
  try { emb = W.self !== W.top; } catch (e) { emb = true; }
  if (!emb) return;
  de.classList.add('embutida');
  var P = W.parent;
  function post(m) { try { P.postMessage(m, '*'); } catch (e) {} }

  var SEC = { 'brasil-ano-a-ano.html': 'linha-do-tempo', 'pares.html': 'pares', 'violencia.html': 'violencia',
              'origens.html': 'origens', 'dossie.html': 'dossie', 'teia.html': 'teia',
              'pistas.html': 'pistas', 'dossie-faccoes.html': 'dossie-faccoes', 'teia-faccoes.html': 'teia-faccoes' };
  var SUB = { 'teia-3d': 1, 'teia-2d': 1 };

  /* ---- altura ---- */
  var last = -1, pend = 0;
  function medir() {
    pend = 0;
    var b = d.body; if (!b) return;
    var mb = parseFloat(getComputedStyle(b).marginBottom) || 0;
    var h = Math.ceil(Math.max(de.getBoundingClientRect().height, b.getBoundingClientRect().bottom + mb));
    if (Math.abs(h - last) > 1) { last = h; post({ pagina: 'altura', h: h }); }
  }
  function agendar() { if (!pend) pend = requestAnimationFrame(medir); }

  /* ---- CSS: vh -> altura visível do pai; sticky/fixed -> trecho visível do iframe ---- */
  var VH = /(-?\d*\.?\d+)[sld]?vh\b/g;
  var zerar = [];
  function patch(rules) {
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i];
      if (!r.selectorText) { if (r.cssRules) patch(r.cssRules); continue; }
      var st = r.style, k, n, v;
      for (k = 0; k < st.length; k++) {
        n = st[k]; v = st.getPropertyValue(n);
        if (v && v.indexOf('vh') >= 0 && v.indexOf('--emb-vh') < 0) {
          var nv = v.replace(VH, 'calc(var(--emb-vh, 1vh) * $1)');
          if (nv !== v) st.setProperty(n, nv, st.getPropertyPriority(n));
        }
      }
      var pos = st.getPropertyValue('position');
      if (pos === 'sticky' || pos === 'fixed') {
        ['top', 'bottom'].forEach(function (p) {
          var v2 = st.getPropertyValue(p);
          if (v2 && v2 !== 'auto' && v2.indexOf('--emb-') < 0)
            st.setProperty(p, 'calc(var(--emb-' + (p === 'top' ? 'y' : 'b') + ', 0px) + (' + v2 + '))', st.getPropertyPriority(p));
        });
      }
      /* dentro de camadas fixas e de caixas com rolagem própria, sticky volta ao normal */
      var ov = st.getPropertyValue('overflow') + ' ' + st.getPropertyValue('overflow-y');
      if (pos === 'fixed' || /auto|scroll/.test(ov))
        zerar.push(r.selectorText.split(',').map(function (s) { return s.trim() + ' *'; }).join(','));
    }
  }
  function patchAll() {
    for (var i = 0; i < d.styleSheets.length; i++) {
      var sh = d.styleSheets[i], rs = null;
      try { rs = sh.cssRules; } catch (e) { continue; } /* folhas de outra origem (Google Fonts) */
      if (rs && !sh.ownerNode.hasAttribute('data-emb')) patch(rs);
    }
    if (zerar.length) {
      var s = d.createElement('style'); s.setAttribute('data-emb', '');
      s.textContent = zerar.map(function (z) { return z + '{--emb-y:0px;--emb-b:0px}'; }).join('\n');
      d.head.appendChild(s);
    }
  }

  /* ---- trecho visível, tema e hash vindos do pai ---- */
  addEventListener('message', function (e) {
    if (e.source !== P || !e.data || typeof e.data !== 'object') return;
    var m = e.data;
    if (m.pagina === 'vista') {
      de.style.setProperty('--emb-y', m.y + 'px');
      de.style.setProperty('--emb-b', m.b + 'px');
      if (m.vh !== W.__embVh) {
        W.__embVh = m.vh;
        de.style.setProperty('--emb-vh', m.vh / 100 + 'px');
        dispatchEvent(new Event('vistaembutida'));
      }
    } else if (m.pagina === 'tema') {
      tema(m.tema);
    } else if (m.pagina === 'hash' && typeof m.hash === 'string') {
      try { history.replaceState(null, '', '#' + m.hash); } catch (er) {}
      dispatchEvent(new HashChangeEvent('hashchange'));
    }
  });

  /* ---- rolagens da página viram rolagens do pai ---- */
  W.scrollTo = W.scroll = function (a, b) {
    var y = (a && typeof a === 'object') ? a.top : b;
    if (y == null || isNaN(+y)) return;
    post({ pagina: 'rolar', y: +y, suave: !!(a && a.behavior === 'smooth') });
  };

  /* ---- links ---- */
  function destino(a) {
    var h = a.getAttribute('href');
    if (!h || h.charAt(0) === '#' || /^[a-z]+:/i.test(h) && h.indexOf(location.protocol) !== 0) return null;
    var u; try { u = new URL(h, location.href); } catch (e) { return null; }
    var f = u.pathname.split('/').pop();
    var dir = location.pathname.replace(/[^/]*$/, '');
    if (!SEC[f] || u.pathname !== dir + f) return null;
    var sub = u.hash.slice(1);
    if (SUB[sub]) return sub;
    /* teia.html?teia=faccoes é a seção da teia de facções; o resto do hash (#d=..., #r=..., filtros das pistas) segue para a filha */
    var s = f === 'teia.html' && /[?&]teia=faccoes\b/.test(u.search) ? 'teia-faccoes' : SEC[f];
    return sub ? s + '|' + sub : s;
  }
  function relinkar() {
    var as = d.querySelectorAll('a[href]');
    for (var i = 0; i < as.length; i++) {
      var a = as[i], s = destino(a);
      if (s) { a.setAttribute('href', '../index.html#' + s.split('|')[0]); a.setAttribute('target', '_top'); a.setAttribute('data-secao', s); }
    }
  }
  addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var s = a.getAttribute('data-secao') || destino(a);
    if (s) { e.preventDefault(); var p = s.split('|'); post({ pagina: 'ir', hash: p[0], frag: p.slice(1).join('|') || undefined }); return; }
    var h = a.getAttribute('href');
    if (h && h.charAt(0) === '#' && h.length > 1) {
      var el = d.getElementById(decodeURIComponent(h.slice(1)));
      if (el) { e.preventDefault(); post({ pagina: 'rolar', y: el.getBoundingClientRect().top - (parseFloat(getComputedStyle(el).scrollMarginTop) || 0), suave: true }); }
    }
  });

  function pronto() {
    patchAll();
    relinkar();
    if (W.ResizeObserver) { var ro = new ResizeObserver(agendar); ro.observe(de); ro.observe(d.body); }
    var rt = 0; new MutationObserver(function () { if (!rt) rt = setTimeout(function () { rt = 0; relinkar(); }, 400); }).observe(d.body, { childList: true, subtree: true });
    post({ pagina: 'pronta' });
    medir();
  }
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', pronto); else pronto();
  addEventListener('load', agendar);
  addEventListener('resize', agendar);
})();
