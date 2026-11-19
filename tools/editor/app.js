'use strict';
// Dialogue editor UI. Everything user-visible from files is set via textContent.

const $ = (s, el = document) => el.querySelector(s);
const ENGINE = /^\s*[A-Za-z]:/;
const NODE_W = 176, NODE_H = 48, COL_GAP = 78, ROW_GAP = 14, PAD = 24;

const state = { files: [], cur: null, recs: new Map(), sel: null, scale: 1, pos: new Map(), dirty: new Set() };

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k);
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
async function api(path, body) {
  const opt = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg, bad = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = bad ? 'bad' : ''; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), bad ? 9000 : 3500);
}
function worst(r) {
  const s = (r && r.hints && r.hints.issues || []).map(i => i.sev);
  return s.includes('err') ? 'err' : s.includes('warn') ? 'warn' : '';
}

/* ---------- files & search ---------- */

const KIND = { talk: 'Розмови', examine: 'Огляд предметів', resurrect: 'Воскресіння' };
const KIND_TAG = { talk: '', examine: 'огляд', resurrect: 'воскресіння' };
const listUI = { kind: '' };

async function loadFiles() {
  const r = await api('/api/files');
  state.files = r.files;
  renderKinds(); renderFiles();
  $('#list-info').textContent = r.ready ? '' : 'рахую привітання й проблеми по всіх файлах…';
  if (!r.ready) setTimeout(loadFiles, 1500);
}
function renderKinds() {
  const box = $('#kinds'); box.textContent = '';
  const count = k => state.files.filter(f => !k || f.kind === k).length;
  for (const k of ['', 'talk', 'examine', 'resurrect']) {
    const b = el('button', { class: listUI.kind === k ? 'on' : '', text: `${k ? KIND[k] : 'Усі'} ${count(k)}` });
    b.addEventListener('click', () => { listUI.kind = k; renderKinds(); renderFiles(); });
    box.append(b);
  }
}
function fileRow(x) {
  const no = (x.path.match(/dlg\/(\d+)/) || [])[1] || '';
  const li = el('li', { class: `f st-${x.status}` + (state.cur && state.cur.path === x.path ? ' active' : ''),
    title: x.path, onclick: () => openFile(x.path) });
  const ix = x.ix || {};
  const l1 = el('div', { class: 'l1' }, el('span', { class: 'no', text: no }), el('span', { class: 't', text: ix.title || x.title || x.path }));
  if (KIND_TAG[x.kind]) l1.append(el('span', { class: 'k', text: KIND_TAG[x.kind] }));
  li.append(l1);
  const ww = [ix.who, ix.where].filter(Boolean).join(' · ');
  if (ww) li.append(el('div', { class: 'w', text: ww }));
  if (ix.context || x.greet) li.append(el('div', { class: 'g', title: x.greet || '', text: ix.context || '«' + x.greet + '»' }));
  const l3 = el('div', { class: 'l3' });
  if (x.status) l3.append(el('span', { text: x.status }));
  if (x.words) l3.append(el('span', { text: `${x.words} сл.` }));
  if (x.npc != null) l3.append(el('span', { text: `${x.npc} NPC · ${x.pc} відп.` }));
  if (x.err) l3.append(el('span', { class: 'badge err', title: 'записів з помилками', text: `✕ ${x.err}` }));
  if (x.warn) l3.append(el('span', { class: 'badge warn', title: 'записів з попередженнями', text: `! ${x.warn}` }));
  li.append(l3);
  return li;
}
function renderFiles() {
  const q = $('#file-filter').value.trim().toLowerCase();
  const st = $('#f-status').value, bad = $('#f-bad').checked, sort = $('#f-sort').value;
  let rows = state.files.filter(x =>
    (!listUI.kind || x.kind === listUI.kind) && (!st || x.status === st) && (!bad || x.err || x.warn) &&
    (!q || [x.path, x.title, x.greet, ...Object.values(x.ix || {})].some(v => (v || '').toLowerCase().includes(q))));
  if (sort === 'problems') rows = [...rows].sort((a, b) => (b.err * 100 + b.warn) - (a.err * 100 + a.warn));
  if (sort === 'words') rows = [...rows].sort((a, b) => (+b.words || b.npc + b.pc || 0) - (+a.words || a.npc + a.pc || 0));
  const ul = $('#files'); ul.textContent = '';
  const frag = document.createDocumentFragment();
  if ($('#f-group').checked) renderGroups(rows, frag);
  else rows.forEach(x => frag.append(fileRow(x)));
  ul.append(frag);
  if (state.files.length) $('#list-info').textContent = rows.length === state.files.length ? '' : `показано ${rows.length} з ${state.files.length}`;
}
/* ---------- grouping by speaker ---------- */

const numOf = path => +((path.match(/dlg\/(\d+)/) || [])[1] || 0);
// first word of «хто» that names a thing (an object the player uses or examines)
const THING = /^(вітрин|вівтар|двер|кам['’]?ян|ліжк|надгроб|сейф|табличк|щоденник|калюж|люк|магічн(ий портал|і захисні)|могил|підставк|прадавн|пристр|скляний ключ|системн|службов|таємн|закривавлен|записк|камін|паспорт|амулет|книг|напис|штурвал|експонат|статуя|скриня|скриньк)/i;
const groupOpen = new Map();  // key -> true/false once the user toggled it
// Person part of «хто»: before the first comma, without «?» — «Вірджил, супутник» → «Вірджил».
function personOf(x) {
  const who = ((x.ix || {}).who || '').replace(/\?/g, '').split(',')[0].trim();
  if (who) return who;
  return x.spk && x.spk.name ? x.spk.name : '';
}
// Groups by person name (case-insensitive). Not by game prototype: generic
// protos (villager, guard) are shared by unrelated NPCs. Wrong group? Fix «хто» via ✎ опис.
function groupFiles(rows) {
  const groups = new Map();
  for (const x of rows) {
    const p = personOf(x);
    const k = p ? p.toLowerCase() : '—';
    if (!groups.has(k)) groups.set(k, { key: k, files: [], name: p || 'без персонажа' });
    groups.get(k).files.push(x);
  }
  for (const G of groups.values()) {
    G.pic = G.files.find(x => x.spk && x.spk.own) || G.files.find(x => x.spk);
    // a thing, not a person: only «огляд» dialogues and nobody in the game speaks them
    G.sec = G.key === '—' ? 2 : (!G.pic && (G.files.every(x => x.kind === 'examine') || THING.test(G.name))) ? 1 : 0;
  }
  return [...groups.values()].sort((a, b) => a.sec - b.sec || b.files.length - a.files.length || a.name.localeCompare(b.name, 'uk'));
}
function picImg(x, cls) {
  const img = el('img', { class: cls, alt: '', loading: 'lazy', src: '/api/pic?num=' + numOf(x.path) });
  img.addEventListener('error', () => img.classList.add('none'));
  return img;
}
function renderGroups(rows, frag) {
  const curGroup = state.cur && state.cur.path;
  const SEC = ['Персонажі', 'Предмети й об\u2019єкти', 'Без персонажа'];
  let sec = -1;
  const all = groupFiles(rows);
  for (const G of all) {
    if (G.sec !== sec) {
      sec = G.sec;
      const n = all.filter(g => g.sec === sec);
      frag.append(el('li', { class: 'sec', text: `${SEC[sec]} · ${n.length} груп, ${n.reduce((k, g) => k + g.files.length, 0)} діал.` }));
    }
    const open = groupOpen.has(G.key) ? groupOpen.get(G.key) : G.files.some(x => x.path === curGroup) || rows.length < 40;
    const head = el('li', { class: 'grp' + (open ? ' open' : ''), title: G.pic && G.pic.spk ? [G.pic.spk.name, ...(G.pic.spk.maps || [])].join(' · ') : '' });
    head.append(G.pic ? picImg(G.pic, 'av') : el('span', { class: 'av none' }));
    const bad = G.files.reduce((n, x) => n + (x.err || 0), 0), warn = G.files.reduce((n, x) => n + (x.warn || 0), 0);
    const st = {}; G.files.forEach(x => { if (x.status) st[x.status] = (st[x.status] || 0) + 1; });
    head.append(el('div', { class: 'gt' },
      el('div', { class: 'gn', text: G.name }),
      el('div', { class: 'gs', text: `${G.files.length} діал.` + (Object.keys(st).length ? ' · ' + Object.entries(st).map(([k, v]) => `${k} ${v}`).join(', ') : '') }),
    ));
    if (bad) head.append(el('span', { class: 'badge err', text: `✕ ${bad}` }));
    else if (warn) head.append(el('span', { class: 'badge warn', text: `! ${warn}` }));
    head.addEventListener('click', () => { groupOpen.set(G.key, !open); renderFiles(); });
    frag.append(head);
    if (open) G.files.forEach(x => frag.append(fileRow(x)));
  }
}
function showFilePic(path) {
  const img = $('#file-pic'), x = state.files.find(f => f.path === path);
  let src = x && x.spk ? x : null;
  if (x && !(src && src.spk.own)) {
    const p = personOf(x).toLowerCase();
    const same = p ? state.files.filter(f => f.spk && personOf(f).toLowerCase() === p) : [];
    src = same.find(f => f.spk.own) || src || same[0] || null;
  }
  img.hidden = !src;
  if (src) { img.onerror = () => (img.hidden = true); img.src = '/api/pic?num=' + numOf(src.path); img.title = src.spk.name; }
}
async function search(q) {
  const box = $('#results');
  if (!q) { box.hidden = true; $('#files').hidden = false; return; }
  const m = q.match(/^#\s*(\d+)$/);
  if (m && state.cur) return jump(+m[1]);
  box.hidden = false; $('#files').hidden = true;
  box.textContent = ''; box.append(el('div', { class: 'head', text: 'Шукаю…' }));
  const r = await api('/api/search?q=' + encodeURIComponent(q));
  if (r.files.length === 1 && !r.hits.length) {
    box.hidden = true; $('#files').hidden = false;
    return openFile(r.files[0].path, r.line);
  }
  box.textContent = '';
  box.append(el('div', { class: 'head', text: `файлів: ${r.files.length}, реплік: ${r.hits.length}${r.truncated ? '+' : ''} · Esc — закрити` }));
  for (const f of r.files) box.append(el('div', { class: 'hit', onclick: () => openFile(f.path) }, el('div', { text: f.path })));
  for (const h of r.hits) box.append(el('div', { class: 'hit', onclick: () => openFile(h.path, h.num) },
    el('div', { class: 'p', text: `${h.path.replace(/^dlg\//, '')} #${h.num}` }), el('div', { text: h.uk || h.en })));
}

/* ---------- dialog ---------- */

async function openFile(path, line) {
  if (state.dirty.size && !confirm('Є незбережені правки. Відкинути?')) return;
  const d = await api('/api/dialog?path=' + encodeURIComponent(path));
  state.cur = d; state.recs = new Map(d.records.map(r => [r.num, r])); state.dirty.clear(); state.sel = null;
  $('#file-title').textContent = d.path;
  showFilePic(d.path);
  document.title = d.path.replace(/^dlg\//, '') + ' — діалоги';
  renderFiles(); renderCards(); renderGraph();
  const first = line != null ? line : (d.graph.roots[0] ?? null);
  if (first != null) jump(first, line == null);
  history.replaceState(null, '', '#' + d.path + (line != null ? ':' + line : ''));
}

function nodeOf(num) {
  // the NPC node that owns record num (itself or one of its options)
  for (const n of state.cur.graph.nodes) {
    if (n.num === num || n.options.some(o => o.num === num)) return n;
  }
  return null;
}

function jump(num, quiet = false) {
  const n = nodeOf(num);
  if (!n) { if (!quiet) toast(`запису #${num} нема в цьому діалозі`, true); return; }
  select(n.num, { graph: true });
  const rec = document.getElementById('rec-' + num);
  if (rec) {
    rec.scrollIntoView({ block: 'center' });
    rec.classList.remove('flash'); void rec.offsetWidth; rec.classList.add('flash');
  }
  history.replaceState(null, '', '#' + state.cur.path + ':' + num);
}

function select(num, { card = false, graph = false } = {}) {
  state.sel = num;
  document.querySelectorAll('.card.sel').forEach(c => c.classList.remove('sel'));
  const c = document.getElementById('card-' + num);
  if (c) { c.classList.add('sel'); if (card) c.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  document.querySelectorAll('#graph .node').forEach(g => g.classList.toggle('sel', +g.dataset.num === num));
  document.querySelectorAll('#graph path.edge').forEach(p =>
    p.classList.toggle('hl', +p.dataset.src === num || +p.dataset.dst === num));
  if (graph && state.pos.has(num)) {
    const p = state.pos.get(num), sc = $('#graph-scroll');
    sc.scrollTo({ left: p.x * state.scale - sc.clientWidth / 2 + NODE_W / 2, top: p.y * state.scale - sc.clientHeight / 2, behavior: 'smooth' });
  }
}

/* ---------- cards ---------- */

function targetTag(r) {
  const t = parseInt(r.target || '0', 10);
  if (t > 0) return jumpLink(t);
  if (t < 0) return el('span', { class: 'tag', title: 'кінець розмови, далі скрипт NPC з рядка ' + (-t), text: `кінець · скрипт ${-t}` });
  return el('span', { class: 'tag', text: 'кінець' });
}
function jumpLink(n, prefix = '→ ') {
  const ok = state.recs.has(n) || state.cur.graph.nodes.some(x => x.num === n);
  return el('a', { class: 'jump', title: ok ? 'перейти' : 'такого рядка нема у файлі', onclick: () => jump(n), text: prefix + n + (ok ? '' : ' (нема)') });
}
// Conditions / effects as readable chips; the raw code and details go to the tooltip.
function codeTags(items, raw, kind) {
  const head = kind === 'cond' ? 'якщо' : 'тоді';
  const help = kind === 'cond'
    ? 'Умова показу: репліку видно, лише коли виконано ВСІ умови.'
    : 'Ефекти: що стається, коли гравець обирає цю репліку.';
  const out = [el('span', { class: 'tag code-head ' + kind, title: help + '\nКод у файлі: ' + raw, text: head })];
  for (const it of items || [{ text: raw, raw, detail: '' }]) {
    const tip = [`${it.raw}`, it.detail].filter(Boolean).join('\n');
    out.push(el('span', { class: 'tag code ' + kind + (it.unknown ? ' unk' : ''), title: tip, text: it.text }));
  }
  return out;
}
function effectTags(fx, r) {
  if (!fx) return [];
  const out = codeTags(r && r.fx_h, fx, 'act');
  for (const m of fx.matchAll(/\bfl\s*(-?\d+)/gi)) out.push(jumpLink(Math.abs(+m[1]), 'fl → '));
  return out;
}

function dialogHead() {
  const d = state.cur, m = state.files.find(f => f.path === d.path) || {};
  const npc = d.records.filter(r => r.kind === 'npc').length, pc = d.records.length - npc;
  const sev = d.records.map(worst);
  const ix = m.ix || {};
  const edit = el('button', { class: 'ix-edit', title: 'Редагувати опис у docs/dlg-index.tsv', text: '✎ опис' });
  const head = el('div', { class: 'dlg-head' },
    el('div', { class: 'l1' }, el('h2', { text: ix.title || m.title || d.path }), edit),
    [ix.who, ix.where].some(Boolean) ? el('div', { class: 'ww', text: [ix.who, ix.where].filter(Boolean).join(' · ') }) : null,
    ix.context ? el('div', { class: 'ctx', text: ix.context }) : null,
    el('div', { class: 'sub' },
      el('span', { text: d.path }), el('span', { text: KIND[m.kind] || '' }), el('span', { text: d.status }),
      el('span', { text: `${npc} реплік NPC · ${pc} відповідей · входів ${d.graph.roots.length}` }),
      el('span', { text: `помилок ${sev.filter(s => s === 'err').length} · попереджень ${sev.filter(s => s === 'warn').length}` })));
  if (m.greet) head.append(el('div', { class: 'greet', text: '«' + m.greet + '»' }));
  edit.addEventListener('click', () => {
    if (head.querySelector('form')) return;
    const f = el('form', { class: 'ix-form' });
    const labels = { title: 'Назва', who: 'Хто', where: 'Де', context: 'Про що' };
    for (const k of Object.keys(labels)) {
      const inp = el('input', { name: k, placeholder: labels[k] }); inp.value = ix[k] || '';
      f.append(el('label', {}, el('span', { text: labels[k] }), inp));
    }
    const cancel = el('button', { type: 'button', text: 'Скасувати', onclick: () => f.remove() });
    f.append(el('div', { class: 'actions' }, el('button', { class: 'primary', text: 'Зберегти опис' }), cancel));
    f.addEventListener('submit', async e => {
      e.preventDefault();
      const body = { path: d.path }; for (const k of Object.keys(labels)) body[k] = f.elements[k].value;
      try { await api('/api/index', body); await loadFiles(); head.replaceWith(dialogHead()); toast('Опис збережено в docs/dlg-index.tsv'); }
      catch (err) { toast(err.message, true); }
    });
    head.append(f); f.elements.title.focus();
  });
  return head;
}

function renderCards() {
  const box = $('#cards'); box.textContent = '';
  box.append(dialogHead());
  for (const n of state.cur.graph.nodes) {
    const card = el('div', { class: 'card', id: n.num != null ? 'card-' + n.num : '' });
    if (n.num != null) {
      card.addEventListener('click', () => { if (state.sel !== n.num) select(n.num, { graph: true }); });
      const r = state.recs.get(n.num);
      if (r) card.append(recEl(r, n));
    } else {
      card.append(el('div', { class: 'rec', text: 'Відповіді без NPC-репліки перед ними (рушій їх не покаже):' }));
    }
    for (const o of n.options) { const r = state.recs.get(o.num); if (r) card.append(recEl(r)); }
    box.append(card);
  }
  applyFilter();
}

function recEl(r, node) {
  const kindName = { npc: 'NPC', pc: 'Гравець', dumb: 'Тупий ГГ' }[r.kind];
  const meta = el('div', { class: 'meta' }, el('span', { class: 'id', text: '#' + r.num }), el('span', { text: kindName }));
  if (r.kind === 'npc') {
    if (r.voice) meta.append(el('span', { class: 'tag', title: 'номер озвучки', text: 'голос ' + r.voice }));
    if (node && state.cur.graph.roots.includes(r.num)) meta.append(el('span', { class: 'tag', title: 'на цей рядок ніщо в діалозі не веде: точка входу зі скрипту', text: 'вхід' }));
  } else {
    const iq = parseInt(r.iq, 10);
    meta.append(el('span', { class: 'tag', text: iq < 0 ? `ІНТ ≤ ${-iq}` : `ІНТ ≥ ${iq}` }));
    if (r.gate === '0') meta.append(el('span', { class: 'tag', text: 'лише ГГ-жінка' }));
    if (r.gate === '1') meta.append(el('span', { class: 'tag', text: 'лише ГГ-чоловік' }));
    if (r.cond) meta.append(...codeTags(r.cond_h, r.cond, 'cond'));
    meta.append(targetTag(r));
  }
  meta.append(...effectTags(r.effects, r));

  const box = el('div', { class: `rec ${r.kind}`, id: 'rec-' + r.num }, meta);
  if (ENGINE.test(r.en)) {
    box.classList.add('engine');
    box.append(el('div', { class: 'en', text: r.en + '   — підставляє рушій, не перекладається' }));
    return box;
  }
  const fields = {};
  const hasM = r.en.trim() !== '';
  if (hasM) {
    fields.M = ta(r.uk);
    box.append(el('div', { class: 'pair' }, el('div', { class: 'en', text: r.en }), fields.M));
  }
  let link = null;
  if (r.kind === 'npc' && r.enf && r.enf.trim()) {
    fields.F = ta(r.ukf);
    const same = r.enf === r.en;
    const lab = el('div', { class: 'lab', text: 'Для ГГ-жінки' + (same && hasM ? ' (в оригіналі те саме)' : '') });
    if (hasM) {
      link = el('input', { type: 'checkbox' });
      link.checked = r.ukf === r.uk;
      lab.append(' · ', el('label', {}, link, ' як для чоловіка'));
      const sync = () => { fields.F.disabled = link.checked; if (link.checked) fields.F.value = fields.M.value; };
      link.addEventListener('change', () => { sync(); changed(); });
      fields.M.addEventListener('input', () => link.checked && sync());
      sync();
    }
    box.append(el('div', { class: 'fem' }, lab, el('div', { class: 'pair' },
      el('div', { class: 'en', text: same && hasM ? '' : r.enf }), fields.F)));
  }
  const hints = el('div', { class: 'hints' });
  let active = fields.M || fields.F;
  for (const t of Object.values(fields)) t.addEventListener('focus', () => (active = t));
  let termsBox = renderTerms(r, () => active, box);
  const tmBox = renderTM(r, fields);
  const save = el('button', { class: 'primary', hidden: '', text: 'Зберегти' });
  const revert = el('button', { hidden: '', text: 'Скасувати' });
  const note = el('span', { text: '' });
  box.append(hints, termsBox, tmBox, el('div', { class: 'actions' }, save, revert, note));
  renderHints(hints, r.hints);

  let timer = null;
  function changed() {
    const dirty = (fields.M && fields.M.value !== r.uk) || (fields.F && fields.F.value !== r.ukf);
    for (const t of Object.values(fields)) t.classList.toggle('dirty', dirty);
    save.hidden = revert.hidden = !dirty;
    note.textContent = dirty ? '⌘/Ctrl+Enter — зберегти' : '';
    dirty ? state.dirty.add(r.num) : state.dirty.delete(r.num);
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const h = await api('/api/check', { kind: r.kind === 'npc' ? 'npc' : 'pc', en: r.en, uk: fields.M ? fields.M.value : '',
        enf: r.enf || '', ukf: fields.F ? fields.F.value : '', gate: r.gate || '' });
      renderHints(hints, h);
    }, 300);
  }
  for (const t of Object.values(fields)) {
    t.addEventListener('input', changed);
    t.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); doSave(); } });
    t.addEventListener('focus', () => node !== undefined || select(nodeOf(r.num)?.num));
  }
  revert.addEventListener('click', () => {
    if (fields.M) fields.M.value = r.uk;
    if (fields.F) fields.F.value = r.ukf;
    if (link) { link.checked = r.ukf === r.uk; link.dispatchEvent(new Event('change')); }
    changed();
  });
  save.addEventListener('click', doSave);

  async function doSave() {
    const body = { path: state.cur.path, num: r.num, expect: {} };
    if (fields.M) { body.M = fields.M.value; body.expect.M = r.uk; }
    if (fields.F) { body.F = fields.F.value; body.expect.F = r.ukf; }
    save.disabled = true;
    try {
      const res = await api('/api/save', body);
      if (!res.ok) {
        toast('Не збережено:\n' + res.errors.join('\n'), true);
        if (res.errors.some(e => e.includes('поза редактором')) &&
            confirm(`#${r.num} змінено поза редактором (git, sheet.py…). Перезавантажити діалог з диска? Незбережені правки на сторінці пропадуть.`)) {
          state.dirty.clear(); openFile(state.cur.path, r.num);
        }
        return;
      }
      Object.assign(r, res.record); state.recs.set(r.num, r);
      changed(); renderHints(hints, r.hints); paintNodes(); applyFilter(); loadFiles();
      { const nt = renderTerms(r, () => active, box); termsBox.replaceWith(nt); termsBox = nt; }
      const qa = res.qa.length ? '\nQA: ' + res.qa.join('\n') : '\nQA: чисто';
      toast(`#${r.num} збережено в uk/${state.cur.path}` + (res.notes.length ? '\n' + res.notes.join('\n') : '') + qa, res.qa.length > 0);
    } catch (e) { toast('Помилка: ' + e.message, true); }
    finally { save.disabled = false; }
  }
  return box;
}

function ta(v) {
  const t = el('textarea', { rows: Math.min(10, Math.max(2, Math.ceil((v || '').length / 60))), spellcheck: 'true', lang: 'uk' });
  t.value = v || '';
  return t;
}

function renderHints(box, h) {
  box.textContent = '';
  if (!h) return;
  for (const i of h.issues) box.append(el('span', { class: 'chip ' + i.sev, text: i.msg }));
  const m = h.metrics || {};
  if (m.ratio != null) box.append(el('span', { class: 'chip metric', title: 'довжина UK / EN', text: `×${m.ratio}` }));
  if (m.px) box.append(el('span', { class: 'chip metric', title: 'ширина в шрифті flare12: UK / EN / видиме вікно', text: `${m.px[0]} px (EN ${m.px[1]})` }));
  for (const k of ['linesM', 'linesF']) if (m[k]) box.append(el('span', { class: 'chip metric', title: 'рядків по 291 px у flare12: UK / EN', text: `${k.slice(5)} ${m[k][0]} рядк. (EN ${m[k][1]})` }));
}

function applyFilter() {
  const only = $('#only-problems').checked;
  document.querySelectorAll('#cards .rec').forEach(e => {
    const r = state.recs.get(+e.id.slice(4));
    e.hidden = only && !worst(r);
  });
  document.querySelectorAll('#cards .card').forEach(c => {
    c.hidden = only && ![...c.querySelectorAll('.rec')].some(e => !e.hidden);
  });
}

/* ---------- graph ---------- */

function renderGraph() {
  const g = state.cur.graph, s = $('#graph');
  s.textContent = ''; state.pos.clear();
  const nodes = g.nodes.filter(n => n.num != null);
  const ids = new Set(nodes.map(n => n.num));
  const out = new Map(nodes.map(n => [n.num, []]));
  for (const e of g.edges) if (!e.missing && ids.has(e.src) && ids.has(e.dst)) out.get(e.src).push(e.dst);
  // layers: BFS from entry points, then from whatever is left (cycles)
  const depth = new Map(), order = [];
  const bfs = start => {
    if (depth.has(start)) return;
    depth.set(start, 0); const q = [start];
    while (q.length) {
      const v = q.shift(); order.push(v);
      for (const w of out.get(v)) if (!depth.has(w)) { depth.set(w, depth.get(v) + 1); q.push(w); }
    }
  };
  g.roots.forEach(bfs); nodes.forEach(n => bfs(n.num));
  const cols = [];
  for (const v of order) (cols[depth.get(v)] ||= []).push(v);
  cols.forEach((col, d) => col.forEach((v, i) =>
    state.pos.set(v, { x: PAD + d * (NODE_W + COL_GAP), y: PAD + i * (NODE_H + ROW_GAP), d })));
  const W = PAD * 2 + cols.length * (NODE_W + COL_GAP), H = PAD * 2 + Math.max(1, ...cols.map(c => c.length)) * (NODE_H + ROW_GAP);
  s.setAttribute('viewBox', `0 0 ${W} ${H}`);
  s.dataset.w = W; s.dataset.h = H; zoom(0);

  // edges (merged per src/dst/kind, labelled with the PC lines that lead there)
  const merged = new Map();
  for (const e of g.edges) {
    if (e.missing || !ids.has(e.src) || !ids.has(e.dst)) continue;
    const k = `${e.src}>${e.dst}>${e.kind}`;
    if (!merged.has(k)) merged.set(k, { ...e, via: [] });
    if (e.via != null) merged.get(k).via.push(e.via);
  }
  const eg = svg('g');
  for (const e of merged.values()) {
    const a = state.pos.get(e.src), b = state.pos.get(e.dst);
    const fwd = b.d > a.d;
    let d, lx, ly;
    if (fwd) {
      const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, c = Math.max(30, (x2 - x1) / 2);
      d = `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`; lx = (x1 + x2) / 2; ly = (y1 + y2) / 2 - 3;
    } else {
      const x1 = a.x + NODE_W, y1 = a.y + NODE_H * 0.7, x2 = b.x + NODE_W, y2 = b.y + NODE_H * 0.3, c = 40 + Math.abs(y2 - y1) / 8;
      d = `M${x1},${y1} C${x1 + c},${y1} ${x2 + c},${y2} ${x2 + 4},${y2}`;
    }
    const p = svg('path', { d, class: `edge ${e.kind === 'fl' ? 'fl' : fwd ? '' : 'back'}`, 'marker-end': 'url(#arrow)', 'data-src': e.src, 'data-dst': e.dst });
    const t = svg('title'); t.textContent = `#${e.src} → #${e.dst}` + (e.via.length ? ` через відповіді ${e.via.map(v => '#' + v).join(', ')}` : '') + (e.kind === 'fl' ? ' (fl)' : '');
    p.append(t); eg.append(p);
    if (fwd && e.via.length) {
      const l = svg('text', { x: lx, y: ly, class: 'elabel', 'text-anchor': 'middle' });
      l.textContent = e.via.slice(0, 3).map(v => '#' + v).join(' ') + (e.via.length > 3 ? '…' : '');
      eg.append(l);
    }
  }
  const defs = svg('defs'), mk = svg('marker', { id: 'arrow', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
  mk.append(svg('path', { d: 'M0,0 L8,4 L0,8 z', fill: 'var(--edge)' })); defs.append(mk);
  s.append(defs, eg);

  for (const n of nodes) {
    const p = state.pos.get(n.num), r = state.recs.get(n.num);
    const gN = svg('g', { class: 'node', transform: `translate(${p.x},${p.y})`, 'data-num': n.num });
    gN.append(svg('rect', { width: NODE_W, height: NODE_H }));
    const t1 = svg('text', { x: 8, y: 15, class: 'num' }); t1.textContent = `#${n.num}`;
    const t1b = svg('text', { x: NODE_W - 8, y: 15, class: 'sub', 'text-anchor': 'end' });
    t1b.textContent = `${n.options.length} відп.` + (g.roots.includes(n.num) ? ' · вхід' : '');
    const txt = r ? (r.uk.trim() ? r.uk : (r.ukf || r.en)) : '';
    const t2 = svg('text', { x: 8, y: 31 }); t2.textContent = clip(txt, 30);
    const t3 = svg('text', { x: 8, y: 43, class: 'sub' }); t3.textContent = clip(txt.slice(clip(txt, 30).length - 1), 32);
    const tt = svg('title'); tt.textContent = txt;
    gN.append(t1, t1b, t2, t3, tt);
    gN.addEventListener('click', () => select(n.num, { card: true }));
    s.append(gN);
  }
  paintNodes();
}
function clip(s, n) { s = (s || '').replace(/\s+/g, ' '); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function paintNodes() {
  for (const g of document.querySelectorAll('#graph .node')) {
    const n = state.cur.graph.nodes.find(x => x.num === +g.dataset.num);
    const sev = [n.num, ...n.options.map(o => o.num)].map(k => worst(state.recs.get(k)));
    g.classList.toggle('err', sev.includes('err'));
    g.classList.toggle('warn', !sev.includes('err') && sev.includes('warn'));
    g.classList.toggle('sel', n.num === state.sel);
  }
}
function zoom(step) {
  state.scale = Math.min(2, Math.max(0.3, state.scale * (step > 0 ? 1.2 : step < 0 ? 1 / 1.2 : 1)));
  const s = $('#graph');
  s.setAttribute('width', s.dataset.w * state.scale); s.setAttribute('height', s.dataset.h * state.scale);
}

/* ---------- wiring ---------- */

$('#file-filter').addEventListener('input', renderFiles);
['#f-status', '#f-sort', '#f-bad'].forEach(id => $(id).addEventListener('change', renderFiles));
$('#f-group').addEventListener('change', e => { try { localStorage.setItem('groupBySpeaker', e.target.checked ? '1' : ''); } catch (_) {} renderFiles(); });
try { $('#f-group').checked = localStorage.getItem('groupBySpeaker') === '1'; } catch (_) {}
$('#search-form').addEventListener('submit', e => { e.preventDefault(); search($('#search').value.trim()).catch(err => toast(err.message, true)); });
$('#search').addEventListener('keydown', e => { if (e.key === 'Escape') { $('#search').value = ''; search(''); } });
$('#only-problems').addEventListener('change', applyFilter);
$('#show-graph').addEventListener('change', e => document.body.classList.toggle('no-graph', !e.target.checked));
$('#zoom-in').addEventListener('click', () => zoom(1));
$('#zoom-out').addEventListener('click', () => zoom(-1));
window.addEventListener('beforeunload', e => { if (state.dirty.size) { e.preventDefault(); e.returnValue = ''; } });

function fromHash() {
  const m = decodeURIComponent(location.hash.slice(1)).match(/^(dlg\/[^:]+\.dlg)(?::(\d+))?$/);
  if (!m) return;
  if (state.cur && state.cur.path === m[1]) { if (m[2]) jump(+m[2]); return; }
  openFile(m[1], m[2] ? +m[2] : undefined).catch(e => toast(e.message, true));
}
window.addEventListener('hashchange', fromHash);
loadFiles().then(fromHash).catch(e => toast(e.message, true));

/* ---------- AI pack: export & diff import ---------- */

const ai = $('#ai');
const imp = { items: [] };

function aiTab(name) {
  document.querySelectorAll('#ai .tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('#ai .ai-tab').forEach(s => (s.hidden = s.dataset.tab !== name));
}
$('#ai-open').addEventListener('click', () => {
  const nodeOk = !!(state.cur && state.sel != null);
  $('#scope-node').textContent = nodeOk ? `вузол #${state.sel} і відповіді (+ сусіди як контекст)` : 'поточний вузол (обери вузол)';
  const radio = document.querySelector('input[name=scope][value=node]');
  radio.disabled = !nodeOk;
  if (!nodeOk && radio.checked) document.querySelector('input[name=scope][value=problems]').checked = true;
  ai.showModal();
});
$('#ai-close').addEventListener('click', () => ai.close());
document.querySelectorAll('#ai .tab').forEach(b => b.addEventListener('click', () => aiTab(b.dataset.tab)));

$('#pack-make').addEventListener('click', async () => {
  if (!state.cur) return toast('Спершу відкрий діалог', true);
  const scope = document.querySelector('input[name=scope]:checked').value;
  try {
    const r = await api('/api/pack', { path: state.cur.path, scope, num: state.sel });
    $('#pack-text').value = r.text;
    $('#pack-copy').disabled = false;
    $('#pack-info').textContent = `${r.text.length.toLocaleString('uk')} символів`;
  } catch (e) { toast(e.message, true); }
});
$('#pack-copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#pack-text').value); toast('Пакет скопійовано'); }
  catch { $('#pack-text').select(); document.execCommand('copy'); toast('Пакет скопійовано'); }
});

function wordDiff(a, b) {
  // token LCS; small texts, so O(n*m) is fine
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/), n = A.length, m = B.length;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const box = el('div', { class: 'diff' });
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && A[i] === B[j]) { box.append(A[i]); i++; j++; }
    else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) { box.append(el('ins', { text: B[j] })); j++; }
    else { box.append(el('del', { text: A[i] })); i++; }
  }
  return box;
}

function renderImport() {
  const list = $('#imp-list'); list.textContent = '';
  let sel = 0;
  imp.items.forEach((it, idx) => {
    const bad = it.errors.length > 0;
    const box = el('div', { class: 'item' + (bad ? ' bad' : '') + (!it.changed ? ' same' : '') + (it.applied ? ' applied' : '') });
    const cb = el('input', { type: 'checkbox' });
    cb.checked = it.pick; cb.disabled = bad || !it.changed || it.applied;
    cb.addEventListener('change', () => { it.pick = cb.checked; renderImport(); });
    if (it.pick) sel++;
    const kind = { npc: 'NPC', pc: 'Гравець', dumb: 'Тупий ГГ' }[it.kind];
    const meta = el('div', { class: 'meta' }, el('label', {}, cb, ` ${it.path.replace(/^dlg\//, '')} #${it.num}`), el('span', { text: kind }));
    if (it.applied) meta.append(el('span', { class: 'chip info', text: 'записано' }));
    else if (!it.changed) meta.append(el('span', { class: 'chip info', text: 'без змін' }));
    if (state.cur && it.path === state.cur.path) meta.append(jumpLinkTo(it));
    box.append(meta);
    for (const f of Object.keys(it.old)) {
      const en = f === 'F' ? (it.enf || it.en) : it.en;
      if (!en.trim()) continue;
      const k = it.kind === 'npc' ? (f === 'M' ? 'M' : 'F') : '';
      box.append(el('div', { class: 'fld' }, el('div', { class: 'k', text: k }), el('div', { class: 'en', text: en })));
      box.append(el('div', { class: 'fld' }, el('div', { class: 'k', text: '' }),
        it.new[f] === it.old[f] ? el('div', { class: 'diff', text: it.old[f] }) : wordDiff(it.old[f], it.new[f])));
    }
    const hints = el('div', { class: 'hints' });
    renderHints(hints, it.hints);
    hints.prepend(...it.errors.map(e => el('span', { class: 'chip err', text: 'не пройде: ' + e })));
    box.append(hints);
    list.append(box);
  });
  $('#imp-apply').disabled = sel === 0;
  $('#imp-apply').textContent = `Прийняти вибране (${sel})`;
}
function jumpLinkTo(it) {
  return el('a', { class: 'jump', text: 'до картки', onclick: () => { ai.close(); jump(it.num); } });
}

$('#imp-preview').addEventListener('click', async () => {
  try {
    const r = await api('/api/import/preview', { text: $('#imp-text').value });
    imp.items = r.items.map(it => ({ ...it, pick: it.changed && !it.errors.length && worst(it) !== 'err' }));
    const ch = imp.items.filter(i => i.changed).length, bad = imp.items.filter(i => i.errors.length).length;
    $('#imp-info').textContent = `правок: ${imp.items.length}, зі змінами: ${ch}, відхилено перевіркою: ${bad}` +
      (r.errors.length ? ` · помилки розбору: ${r.errors.length}` : '');
    if (r.errors.length) toast('Не розібрано:\n' + r.errors.slice(0, 12).join('\n'), true);
    renderImport();
  } catch (e) { toast(e.message, true); }
});
$('#imp-all').addEventListener('change', e => {
  for (const it of imp.items) if (it.changed && !it.errors.length && !it.applied) it.pick = e.target.checked;
  renderImport();
});
$('#imp-clear').addEventListener('click', () => { imp.items = []; $('#imp-info').textContent = ''; renderImport(); });
$('#imp-apply').addEventListener('click', async () => {
  const picked = imp.items.filter(i => i.pick);
  const items = picked.map(it => ({ path: it.path, num: it.num, old: it.old, new: it.new,
    fields: Object.keys(it.old).filter(f => it.kind === 'npc' ? (it.en.trim() || f === 'F') && (f === 'M' || it.enf.trim()) : f === 'M') }));
  try {
    const r = await api('/api/import/apply', { items });
    if (!r.ok) return toast('Нічого не записано:\n' + r.errors.slice(0, 15).join('\n'), true);
    picked.forEach(it => { it.applied = true; it.pick = false; });
    renderImport(); loadFiles();
    const qaBad = Object.entries(r.qa).filter(([, v]) => v.length);
    toast(`Записано ${r.written} записів у ${r.files.length} файлах.` + (qaBad.length ? '\nQA: ' + qaBad.map(([, v]) => v.join('\n')).join('\n') : '\nQA: чисто'), qaBad.length > 0);
    if (state.cur && r.files.includes(state.cur.path)) { state.dirty.clear(); const s = state.sel; await openFile(state.cur.path, s ?? undefined); }
  } catch (e) { toast(e.message, true); }
});


/* ---------- glossary terms, translation memory, glossary editor ---------- */

function insertAt(t, text) {
  if (!t || t.disabled) return;
  const a = t.selectionStart ?? t.value.length, b = t.selectionEnd ?? a;
  t.value = t.value.slice(0, a) + text + t.value.slice(b);
  t.focus(); t.selectionStart = t.selectionEnd = a + text.length;
  t.dispatchEvent(new Event('input'));
}

function renderTerms(r, getActive, box) {
  const wrap = el('div', { class: 'terms' });
  const terms = r.terms || [];
  if (terms.length) wrap.append(el('span', { class: 'lab', text: 'глосарій:' }));
  for (const t of terms) {
    const form = t.uk.split(' / ')[0];
    const b = el('button', { class: 'term ' + (t.ok ? 'ok' : 'miss'), type: 'button',
      title: (t.ok ? '' : 'у перекладі нема цієї форми · ') + (t.note || '') + '\nклік — вставити «' + form + '» у поле',
      text: `${t.en} → ${t.uk}` });
    b.addEventListener('click', e => { e.stopPropagation(); insertAt(getActive(), form); });
    wrap.append(b);
  }
  const add = el('button', { class: 'link-btn', type: 'button', title: 'Виділи слово в оригіналі (і, за бажання, в перекладі) — і натисни', text: '+ термін' });
  add.addEventListener('mousedown', e => e.preventDefault());  // keep the selection
  add.addEventListener('click', e => {
    e.stopPropagation();
    const sel = String(window.getSelection() || '').trim();
    const t = getActive();
    const ukSel = t && t.selectionEnd > t.selectionStart ? t.value.slice(t.selectionStart, t.selectionEnd).trim() : '';
    const inEn = sel && box.querySelector('.en') && [...box.querySelectorAll('.en')].some(x => x.textContent.includes(sel));
    openGlossary({ add: { en: inEn ? sel : '', uk: ukSel, note: '' } });
  });
  wrap.append(add);
  return wrap;
}

function renderTM(r, fields) {
  const wrap = el('div', { class: 'tm' });
  for (const [f, tm] of Object.entries(r.tm || {})) {
    if (!tm) continue;
    const lab = Object.keys(fields).length > 1 ? `${f}: ` : '';
    if (!tm.other.length) {
      wrap.append(el('span', { class: 'lab', title: 'пам\'ять перекладів', text: `${lab}так само перекладено ще ${tm.same}×` }));
      continue;
    }
    wrap.append(el('span', { class: 'lab', title: 'та сама англійська репліка в інших місцях', text: `${lab}ПП${tm.same ? ` (так само ${tm.same}×)` : ''}, інакше:` }));
    for (const v of tm.other) {
      const take = el('button', { type: 'button', title: 'взяти цей варіант у поле', text: 'взяти' });
      take.addEventListener('click', e => {
        e.stopPropagation(); const t = fields[f] || fields.M;
        if (t && !t.disabled) { t.value = v.uk; t.dispatchEvent(new Event('input')); t.focus(); }
      });
      const where = el('a', { class: 'jump', title: v.at.join('\n'), text: `${v.n}×` });
      where.addEventListener('click', e => { e.stopPropagation(); const [p, n] = v.at[0].split('#'); openFile(p, +n); });
      wrap.append(el('span', { class: 'var' }, el('span', { text: '«' + v.uk + '»' }), where, take));
    }
  }
  return wrap;
}

const gl = $('#gl');
let glTimer = null;

async function openGlossary({ q = '', add = null } = {}) {
  if (!gl.open) gl.showModal();
  if (q !== null) $('#gl-q').value = q || (add && add.en) || '';
  await loadGlossary();
  if (add) glForm(add);
}
async function loadGlossary(highlight) {
  const r = await api('/api/glossary?q=' + encodeURIComponent($('#gl-q').value.trim()));
  $('#gl-info').textContent = r.total > r.rows.length ? `${r.rows.length} з ${r.total}` : `${r.total}`;
  const list = $('#gl-list'); list.textContent = '';
  for (const g of r.rows) {
    const row = el('div', { class: 'gl-row' + (highlight && g.en === highlight ? ' hl' : '') },
      el('span', { text: g.en }), el('strong', { text: g.uk }), el('span', { class: 'n', text: g.note }));
    const ed = el('button', { type: 'button', text: '✎' });
    ed.addEventListener('click', () => glForm(g, row));
    row.append(ed); list.append(row);
  }
}
function glForm(g, row) {
  // g with .i = edit an existing row; without = add
  document.querySelectorAll('.gl-form').forEach(f => f.remove());
  const f = el('form', { class: 'gl-form' });
  const inp = (n, ph) => { const i = el('input', { name: n, placeholder: ph }); i.value = g[n] || ''; return i; };
  f.append(inp('en', 'EN (як в оригіналі)'), inp('uk', 'UK форма (варіанти через « / »)'), inp('note', 'коментар: відмінки, ?, рішення'));
  f.append(el('button', { class: 'primary', text: g.i != null ? 'Зберегти' : 'Додати' }));
  const right = el('span', {});
  if (g.i != null) {
    const del = el('button', { type: 'button', text: 'Видалити' });
    del.addEventListener('click', async () => {
      if (!confirm(`Видалити з глосарія «${g.en} → ${g.uk}»?`)) return;
      glSave({ action: 'delete', i: g.i, expect: g }, f);
    });
    right.append(del);
  }
  right.append(el('button', { type: 'button', text: '✕', onclick: () => f.remove() }));
  f.append(right);
  f.addEventListener('submit', e => {
    e.preventDefault();
    const body = { action: g.i != null ? 'update' : 'add', en: f.elements.en.value, uk: f.elements.uk.value, note: f.elements.note.value };
    if (g.i != null) Object.assign(body, { i: g.i, expect: { en: g.en, uk: g.uk, note: g.note } });
    glSave(body, f);
  });
  if (row) row.after(f); else $('#gl-form-slot').append(f);
  (f.elements.en.value ? f.elements.uk : f.elements.en).focus();
}
async function glSave(body, form) {
  try {
    const r = await api('/api/glossary', body);
    if (!r.ok) return toast(r.errors.join('\n'), true);
    form.remove();
    toast(body.action === 'delete' ? 'Рядок видалено з glossary/glossary.tsv' : 'Глосарій збережено (glossary/glossary.tsv)');
    await loadGlossary(body.en);
    if (state.cur && !state.dirty.size) { const s = state.sel; await openFile(state.cur.path, s ?? undefined); }
    else if (state.cur) toast('Глосарій збережено. Підказки в картках оновляться після збереження правок або перезавантаження діалогу.');
  } catch (e) { toast(e.message, true); }
}
$('#gl-open').addEventListener('click', () => openGlossary({ q: $('#gl-q').value }));
$('#gl-close').addEventListener('click', () => gl.close());
$('#gl-add').addEventListener('click', () => glForm({ en: '', uk: '', note: '' }));
$('#gl-q').addEventListener('input', () => { clearTimeout(glTimer); glTimer = setTimeout(() => loadGlossary(), 200); });
