// ProView docs: theme toggle, mermaid, search, table-of-contents highlight.
(function () {
  const root = document.documentElement;

  // ---- theme
  const isDark = () => (root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches);
  document.getElementById('theme').addEventListener('click', () => {
    root.dataset.theme = isDark() ? 'light' : 'dark';
    try { localStorage.setItem('pv-docs-theme', root.dataset.theme); } catch (e) { /* storage blocked */ }
    location.reload(); // re-render diagrams in the new theme
  });

  // ---- mermaid
  if (window.mermaid) {
    window.mermaid.initialize({
      startOnLoad: true, securityLevel: 'strict', theme: isDark() ? 'dark' : 'neutral',
      fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', flowchart: { htmlLabels: true, curve: 'basis' },
    });
  }

  // ---- search (index embedded as window.PV_SEARCH so it works from file://)
  const input = document.getElementById('q');
  const box = document.getElementById('results');
  const data = window.PV_SEARCH || [];
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let sel = -1;

  function search(q) {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    const hits = [];
    for (const d of data) {
      const t = d.t.toLowerCase();
      const s = d.s.toLowerCase();
      if (!terms.every((w) => t.includes(w) || s.includes(w))) continue;
      let score = 0;
      for (const w of terms) score += (t.includes(w) ? 10 : 0) + Math.min(5, s.split(w).length - 1);
      const i = s.indexOf(terms[0]);
      const from = Math.max(0, i - 60);
      hits.push({ d, score, snip: (from ? '…' : '') + d.s.slice(from, from + 170) + '…' });
    }
    return hits.sort((a, b) => b.score - a.score).slice(0, 12);
  }

  function highlight(text, q) {
    let out = esc(text);
    for (const w of q.split(/\s+/).filter((x) => x.length > 1)) {
      out = out.replace(new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), (m) => `<mark>${m}</mark>`);
    }
    return out;
  }

  function render() {
    const q = input.value.trim();
    if (!q) { box.hidden = true; return; }
    const hits = search(q);
    sel = -1;
    box.innerHTML = hits.length
      ? hits.map((h) => `<a href="${window.PV_ROOT}${h.d.u}"><div class="r-t">${highlight(h.d.t, q)}</div><div class="r-s">${highlight(h.snip, q)}</div></a>`).join('')
      : '<div class="none">Ничего не найдено</div>';
    box.hidden = false;
  }

  input.addEventListener('input', render);
  input.addEventListener('keydown', (e) => {
    const links = [...box.querySelectorAll('a')];
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
      links.forEach((a, i) => a.classList.toggle('sel', i === sel));
    } else if (e.key === 'Enter' && links.length) {
      location.href = links[Math.max(0, sel)].href;
    } else if (e.key === 'Escape') {
      box.hidden = true; input.blur();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== input) { e.preventDefault(); input.focus(); }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.search')) box.hidden = true; });

  // ---- table of contents: highlight the section in view
  const tocLinks = [...document.querySelectorAll('.toc a')];
  if (tocLinks.length && 'IntersectionObserver' in window) {
    const byId = new Map(tocLinks.map((a) => [decodeURIComponent(a.hash.slice(1)), a]));
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting && byId.has(en.target.id)) {
          tocLinks.forEach((a) => a.classList.remove('on'));
          byId.get(en.target.id).classList.add('on');
        }
      }
    }, { rootMargin: '-60px 0px -70% 0px' });
    document.querySelectorAll('.doc h2[id], .doc h3[id]').forEach((h) => io.observe(h));
  }
})();
