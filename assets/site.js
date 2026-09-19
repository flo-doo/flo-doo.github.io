const PUB_DATA = 'data/publications.json';

function esc(value = '') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function paperLink(p) {
  if (p.doi) return `https://doi.org/${encodeURI(p.doi)}`;
  if (p.url) return p.url;
  return '';
}

function renderLatest(publications, target) {
  const items = publications.slice(0, 6);
  target.innerHTML = items.map(p => {
    const href = paperLink(p);
    return `<article class="latest-item">
      <span class="year">${esc(p.year || '')}</span>
      <div><h4>${esc(p.title)}</h4></div>
      <p>${esc(p.journal || p.type || '')}</p>
      ${href ? `<a href="${esc(href)}" target="_blank" rel="noreferrer">↗</a>` : ''}
    </article>`;
  }).join('');
}

function renderAll(publications, target, countTarget, query = '') {
  const q = query.trim().toLowerCase();
  const filtered = publications.filter(p => [p.title, p.journal, p.year, (p.authors || []).join(' ')].join(' ').toLowerCase().includes(q));
  countTarget.textContent = `${filtered.length} publication${filtered.length === 1 ? '' : 's'}`;
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

async function loadPublications() {
  try {
    const response = await fetch(PUB_DATA, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const publications = Array.isArray(payload) ? payload : payload.publications || [];
    publications.sort((a,b) => (b.date || String(b.year || '')).localeCompare(a.date || String(a.year || '')));

    const latest = document.querySelector('#latest-publications');
    if (latest) {
      renderLatest(publications, latest);
      const status = document.querySelector('#pub-status');
      if (status && payload.updated_at) status.textContent = `Scholarly metadata last refreshed ${payload.updated_at}.`;
    }

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

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#year').forEach(el => el.textContent = new Date().getFullYear());
  loadPublications();
});
