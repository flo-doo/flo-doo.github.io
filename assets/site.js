const PUB_DATA = 'data/publications.json';
const EVENTS_DATA = 'data/events.json';
const THEME_KEY = 'florence-doo-theme';

function esc(value = '') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function setTheme(theme) {
  const resolved = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = resolved;
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    button.textContent = resolved === 'dark' ? 'View in light mode' : 'View in dark mode';
    button.setAttribute('aria-label', resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  });
}

function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch (_) {}
  setTheme(stored === 'light' ? 'light' : 'dark');
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      try { localStorage.setItem(THEME_KEY, next); } catch (_) {}
      setTheme(next);
    });
  });
}

function paperLink(p) {
  if (p.doi) return `https://doi.org/${encodeURI(p.doi)}`;
  if (p.url) return p.url;
  return '';
}

function renderLatest(publications, target) {
  const items = publications.slice(0, 4);
  target.innerHTML = items.map(p => {
    const href = paperLink(p);
    return `<article class="latest-item">
      <span class="year">${esc(p.year || '')}</span>
      <div><h4>${esc(p.title)}</h4></div>
      <p>${esc(p.journal || p.type || '')}</p>
      ${href ? `<a href="${esc(href)}" target="_blank" rel="noreferrer" aria-label="Open ${esc(p.title)}">↗</a>` : '<span></span>'}
    </article>`;
  }).join('');
}

function renderAll(publications, target, countTarget, query = '') {
  const q = query.trim().toLowerCase();
  const filtered = publications.filter(p => [p.title, p.journal, p.year, (p.authors || []).join(' ')].join(' ').toLowerCase().includes(q));
  countTarget.textContent = q
    ? `${filtered.length} matching publication${filtered.length === 1 ? '' : 's'} of ${publications.length}`
    : `${publications.length} publications`;
  target.innerHTML = filtered.map(p => {
    const href = paperLink(p);
    const authors = Array.isArray(p.authors) && p.authors.length ? p.authors.join(', ') : '';
    return `<article class="all-pub-item">
      <span class="year">${esc(p.year || '')}</span>
      <div><h2>${esc(p.title)}</h2><p>${esc([authors, p.journal].filter(Boolean).join(' · '))}</p></div>
      <div class="pub-links">${href ? `<a href="${esc(href)}" target="_blank" rel="noreferrer">DOI / article ↗</a>` : ''}</div>
    </article>`;
  }).join('') || '<p class="loading">No matching publications.</p>';
}

function formatEventDate(dateString) {
  const date = new Date(`${dateString}T12:00:00`);
  if (Number.isNaN(date.getTime())) return dateString;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit' }).format(date);
}

function renderUpcoming(events, target) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const upcoming = events
    .filter(event => {
      const d = new Date(`${event.date}T12:00:00`);
      return !Number.isNaN(d.getTime()) && d >= today;
    })
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 3);

  if (!upcoming.length) {
    target.innerHTML = '<p class="empty-state">Upcoming talks and appearances will be posted here.</p>';
    return;
  }

  target.innerHTML = upcoming.map(event => {
    const meta = [event.event, event.location].filter(Boolean).join(' · ');
    const body = `<span class="event-date">${esc(formatEventDate(event.date))}</span>
      <div><h4>${esc(event.title || event.event || 'Upcoming event')}</h4><p>${esc(meta)}</p></div>`;
    if (event.url) {
      return `<a class="event-item" href="${esc(event.url)}" target="_blank" rel="noreferrer">${body}<span class="arrow">↗</span></a>`;
    }
    return `<article class="event-item">${body}<span></span></article>`;
  }).join('');
}

async function loadPublications() {
  try {
    const response = await fetch(PUB_DATA, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const publications = Array.isArray(payload) ? payload : payload.publications || [];
    publications.sort((a,b) => (b.date || String(b.year || '')).localeCompare(a.date || String(a.year || '')));

    const latest = document.querySelector('#latest-publications');
    if (latest) renderLatest(publications, latest);

    const all = document.querySelector('#all-publications');
    const count = document.querySelector('#pub-count');
    const search = document.querySelector('#pub-search');
    if (all && count) {
      const params = new URLSearchParams(window.location.search);
      const initialQuery = params.get('q') || '';
      if (search) search.value = initialQuery;
      renderAll(publications, all, count, initialQuery);
      if (search) search.addEventListener('input', () => renderAll(publications, all, count, search.value));
    }
  } catch (err) {
    document.querySelectorAll('#latest-publications, #all-publications').forEach(el => {
      el.innerHTML = '<p class="loading">Publication metadata is temporarily unavailable. The complete record remains available on ORCID.</p>';
    });
  }
}

async function loadEvents() {
  const target = document.querySelector('#upcoming-events');
  if (!target) return;
  try {
    const response = await fetch(EVENTS_DATA, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const events = Array.isArray(payload) ? payload : payload.events || [];
    renderUpcoming(events, target);
  } catch (err) {
    target.innerHTML = '<p class="empty-state">Upcoming talks and appearances will be posted here.</p>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  document.querySelectorAll('#year').forEach(el => el.textContent = new Date().getFullYear());
  loadPublications();
  loadEvents();
});
