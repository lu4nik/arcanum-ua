'use strict';
// «Тексти» mode: the .mes files (interface, item names, journal, newspaper,
// generic NPC lines). Shares helpers with app.js (el, api, toast, ta, renderHints).

const mes = { files: [], cur: null, recs: [], shown: 150, filter: '', only: false, mode: 'dlg' };

function setMode(m) {
  if (m === mes.mode) return;
  if (state.dirty.size && !confirm('Є незбережені правки. Відкинути?')) return;
  state.dirty.clear();
  mes.mode = m;
  document.body.classList.toggle('mode-mes', m === 'mes');
  $('#file-filter').placeholder = m === 'mes' ? 'Фільтр: назва файлу або що в ньому' : 'Фільтр: назва, номер, текст привітання';
  for (const b of document.querySelectorAll('#mode button')) b.classList.toggle('on', b.dataset.mode === m);
  if (m === 'mes') {
    if (!mes.files.length) loadMesFiles(); else renderMesFiles();
    if (mes.cur) renderMes(); else $('#cards').replaceChildren(el('p', { class: 'empty', text: 'Обери файл ліворуч: інтерфейс, назви й описи предметів, журнал, газета, загальні репліки NPC.' }));
    $('#file-pic').hidden = true;
    $('#file-title').textContent = mes.cur ? mes.cur.path : '';
  } else {
    $('#file-title').textContent = state.cur ? state.cur.path : '';
    if (state.cur) { renderCards(); renderGraph(); showFilePic(state.cur.path); }
    else $('#cards').replaceChildren(el('p', { class: 'empty', text: 'Обери діалог ліворуч.' }));
  }
}

async function loadMesFiles() {
  const r = await api('/api/mes/files');
  mes.files = r.files;
  renderMesFiles();
}

function renderMesFiles() {
  const q = $('#file-filter').value.trim().toLowerCase();
  const ul = $('#mes-files'); ul.textContent = '';
  let group = null;
  for (const f of mes.files) {
    if (q && ![f.name, f.title, f.group].some(v => (v || '').toLowerCase().includes(q))) continue;
    if (f.group !== group) { group = f.group; ul.append(el('li', { class: 'sec', text: group })); }
    const li = el('li', { class: 'f st-' + f.status + (mes.cur && mes.cur.path === f.path ? ' active' : ''), title: f.path,
      onclick: () => openMes(f.path) });
    li.append(el('div', { class: 'l1' }, el('span', { class: 't', text: f.title || f.name }), el('span', { class: 'no', text: f.name })));
    const l3 = el('div', { class: 'l3' });
    if (f.records) l3.append(el('span', { text: `${f.records} записів` }));
    if (f.words) l3.append(el('span', { text: `${f.words} сл.` }));
    if (f.rules.length) l3.append(el('span', { class: 'badge info', title: 'перевіряється ширина:\n' + f.rules.join('\n'), text: 'ширина' }));
    li.append(l3);
    ul.append(li);
  }
}

async function openMes(path, key) {
  if (state.dirty.size && !confirm('Є незбережені правки. Відкинути?')) return;
  state.dirty.clear();
  const d = await api('/api/mes?path=' + encodeURIComponent(path));
  mes.cur = d; mes.recs = d.records; mes.shown = 150;
  if (key != null) { mes.filter = ''; }
  $('#file-title').textContent = d.path;
  document.title = d.path.replace(/^mes\//, '') + ' — тексти';
  history.replaceState(null, '', '#' + d.path + (key != null ? ':' + key : ''));
  renderMesFiles(); renderMes();
  if (key != null) {
    const i = mes.recs.findIndex(r => r.key === String(key));
    if (i >= mes.shown) { mes.shown = i + 20; renderMes(); }
    const e = document.getElementById('mes-' + key);
    if (e) { e.scrollIntoView({ block: 'center' }); e.classList.add('flash'); }
  }
}

const sevOf = r => { const s = (r.hints && r.hints.issues || []).map(i => i.sev); return s.includes('err') ? 'err' : s.includes('warn') ? 'warn' : ''; };

function renderMes() {
  const d = mes.cur, box = $('#cards');
  const q = mes.filter.toLowerCase();
  const nonblank = mes.recs.filter(r => r.en.trim() || r.uk.trim()).length;
  const rows = mes.recs.filter(r => (r.en.trim() || r.uk.trim()) && (!mes.only || sevOf(r)) &&
    (!q || r.key === q || r.en.toLowerCase().includes(q) || r.uk.toLowerCase().includes(q)));
  const errs = mes.recs.filter(r => sevOf(r) === 'err').length, warns = mes.recs.filter(r => sevOf(r) === 'warn').length;
  const find = el('input', { type: 'search', placeholder: 'Пошук у файлі: ключ, EN або UK', value: mes.filter });
  let t = null;
  find.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { mes.filter = find.value.trim(); mes.shown = 150; renderMes(); $('#cards input[type=search]').focus(); }, 250); });
  const only = el('label', { class: 'toggle' }, el('input', { type: 'checkbox' }), ' лише проблемні');
  only.firstChild.checked = mes.only;
  only.firstChild.addEventListener('change', e => { mes.only = e.target.checked; mes.shown = 150; renderMes(); });
  const head = el('div', { class: 'dlg-head' },
    el('div', { class: 'l1' }, el('h2', { text: d.title || d.path })),
    el('div', { class: 'sub' }, el('span', { text: d.path }), el('span', { text: `записів ${nonblank}` }),
      el('span', { text: `помилок ${errs} · попереджень ${warns}` })),
    d.rules.length ? el('div', { class: 'ctx', text: 'Перевіряється, чи влазить: ' + d.rules.join('; ') }) : null,
    d.path === 'mes/gamenewspaper.mes' ? el('div', { class: 'ctx', text: 'Газета: розкладку колонок тут не перевірено — після правок запусти tools/newscheck.py.' }) : null,
    el('div', { class: 'mes-tools' }, find, only, el('span', { class: 'muted', text: rows.length === nonblank ? '' : `знайдено ${rows.length}` })));
  const list = el('div', { class: 'card' });
  rows.slice(0, mes.shown).forEach(r => list.append(mesRec(r)));
  box.replaceChildren(head, list);
  if (rows.length > mes.shown) {
    const more = el('button', { text: `Показати ще (${rows.length - mes.shown})` });
    more.addEventListener('click', () => { mes.shown += 300; renderMes(); });
    box.append(more);
  }
}

function mesRec(r) {
  const meta = el('div', { class: 'meta' }, el('span', { class: 'id', text: '{' + r.key + '}' }));
  const box = el('div', { class: 'rec mes', id: 'mes-' + r.key }, meta);
  const f = ta(r.uk);
  // where the game draws it: the width rules that cover this entry, else the file's purpose
  const places = r.places && r.places.length ? r.places
    : [{ label: (mes.cur.title || 'текст') + ' — точне вікно не відоме, показано як інфо-панель', font: 'flare12', width: 291, lines: 0 }];
  for (const p of r.places || []) meta.append(el('span', { class: 'tag where', title: `шрифт ${p.font}, ${p.width} px, ${p.lines} ряд.`, text: '📍 ' + p.label }));
  if (!(r.places || []).length && mes.cur.title) meta.append(el('span', { class: 'tag where', text: '📍 ' + mes.cur.title }));
  const pv = el('button', { class: 'pv-btn', title: 'Показати, як рядок виглядатиме в грі (шрифт і ширина вікна)', text: '👁 прев’ю' });
  meta.append(pv);
  const pvBox = el('div', { class: 'pv', hidden: '' });
  let pvOn = false;
  function drawPreview() {
    if (!pvOn) return;
    pvBox.replaceChildren(...places.map(p => el('figure', {},
      el('img', { alt: '', src: '/api/preview?' + new URLSearchParams({ text: f.value, font: p.font, width: p.width, lines: p.lines }) }),
      el('figcaption', { text: p.label }))));
  }
  pv.addEventListener('click', () => { pvOn = !pvOn; pvBox.hidden = !pvOn; pv.classList.toggle('on', pvOn); drawPreview(); });
  box.append(el('div', { class: 'pair' }, el('div', { class: 'en', text: r.en }), f), pvBox);
  const hints = el('div', { class: 'hints' });
  const save = el('button', { class: 'primary', hidden: '', text: 'Зберегти' });
  const revert = el('button', { hidden: '', text: 'Скасувати' });
  const note = el('span', { text: '' });
  box.append(hints, el('div', { class: 'actions' }, save, revert, note));
  renderHints(hints, r.hints);
  let timer = null;
  const id = 'mes:' + r.key;
  function changed() {
    const dirty = f.value !== r.uk;
    f.classList.toggle('dirty', dirty);
    save.hidden = revert.hidden = !dirty;
    note.textContent = dirty ? '⌘/Ctrl+Enter — зберегти' : '';
    dirty ? state.dirty.add(id) : state.dirty.delete(id);
    clearTimeout(timer);
    timer = setTimeout(async () => { drawPreview(); renderHints(hints, await api('/api/mes/check', { path: mes.cur.path, key: r.key, en: r.en, uk: f.value })); }, 300);
  }
  f.addEventListener('input', changed);
  f.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); doSave(); } });
  revert.addEventListener('click', () => { f.value = r.uk; changed(); });
  save.addEventListener('click', doSave);
  async function doSave() {
    save.disabled = true;
    try {
      const res = await api('/api/mes/save', { path: mes.cur.path, key: r.key, uk: f.value, expect: r.uk });
      if (!res.ok) {
        toast('Не збережено:\n' + res.errors.join('\n'), true);
        if (res.errors.some(e => e.includes('поза редактором')) && confirm(`{${r.key}} змінено поза редактором. Перезавантажити файл з диска?`)) {
          state.dirty.clear(); openMes(mes.cur.path, r.key);
        }
        return;
      }
      Object.assign(r, res.record);
      changed(); renderHints(hints, r.hints);
      const qa = res.qa.length ? '\nQA: ' + res.qa.join('\n') : '\nQA: чисто';
      toast(`{${r.key}} збережено в uk/${mes.cur.path}` + (res.notes.length ? '\n' + res.notes.join('\n') : '') + qa, res.qa.length > 0);
    } catch (e) { toast('Помилка: ' + e.message, true); }
    finally { save.disabled = false; }
  }
  return box;
}

for (const b of document.querySelectorAll('#mode button')) b.addEventListener('click', () => setMode(b.dataset.mode));
$('#file-filter').addEventListener('input', () => mes.mode === 'mes' && renderMesFiles());
function mesFromHash() {
  const m = decodeURIComponent(location.hash.slice(1)).match(/^(mes\/[^:]+\.mes)(?::(\d+))?$/);
  if (!m) return;
  setMode('mes');
  if (mes.cur && mes.cur.path === m[1]) return;
  openMes(m[1], m[2]).catch(e => toast(e.message, true));
}
window.addEventListener('hashchange', mesFromHash);
mesFromHash();
