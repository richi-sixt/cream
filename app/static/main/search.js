function fmtChf(value){
  const v = Number(value || 0);
  return 'CHF ' + v.toLocaleString('de-CH', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function escapeHtml(value){
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function selectedValues(selectId){
  const el = document.getElementById(selectId);
  if(!el) return [];
  return Array.from(el.selectedOptions).map(opt => opt.value).filter(Boolean);
}

function parseMultiText(inputId){
  const raw = (document.getElementById(inputId)?.value || '').trim();
  if(!raw) return [];
  return raw.split(/[;,]/).map(s => s.trim()).filter(Boolean);
}

function setTotals(totals){
  document.getElementById('kpi-positive').textContent = fmtChf(totals.positive);
  document.getElementById('kpi-negative').textContent = fmtChf(totals.negative);
  document.getElementById('kpi-sum').textContent = fmtChf(totals.sum);
  document.getElementById('kpi-count').textContent = String(totals.count || 0);
}

function renderGroupedRows(rows){
  const head = document.getElementById('results-head');
  const body = document.getElementById('results-body');
  head.innerHTML = '<tr><th>Gruppe</th><th>Positiv</th><th>Negativ</th><th>Summe</th><th>Anzahl</th></tr>';
  if(!rows.length){
    body.innerHTML = '<tr><td colspan="5" class="empty">Keine Treffer.</td></tr>';
    return;
  }
  body.innerHTML = rows.map(row => `
    <tr>
      <td>${row.group}</td>
      <td class="num pos">${fmtChf(row.positive)}</td>
      <td class="num neg">${fmtChf(row.negative)}</td>
      <td class="num ${row.sum >= 0 ? 'pos' : 'neg'}">${fmtChf(row.sum)}</td>
      <td class="num">${row.count}</td>
    </tr>
  `).join('');
}

function renderTransactionRows(rows){
  const head = document.getElementById('results-head');
  const body = document.getElementById('results-body');
  head.innerHTML = '<tr><th>Datum</th><th>Konto</th><th>Beschreibung</th><th>Kategorie</th><th>Betrag</th><th>Saldo</th></tr>';
  if(!rows.length){
    body.innerHTML = '<tr><td colspan="6" class="empty">Keine Treffer.</td></tr>';
    return;
  }

  body.innerHTML = rows.map(row => {
    const account = row.account_name || row.account_id || '—';
    const desc = row.display_title || row.raw_description || '—';
    const category = row.category_name || '—';
    const amountClass = row.type === 'income' ? 'pos' : 'neg';
    const amountSign = row.type === 'income' ? '+' : '-';
    return `
      <tr>
        <td>${row.date || '—'}</td>
        <td>${account}</td>
        <td title="${escapeHtml(row.raw_description || '')}">${escapeHtml(desc)}</td>
        <td>${escapeHtml(category)}</td>
        <td class="num ${amountClass}">${amountSign}${fmtChf(row.amount)}</td>
        <td class="num">${row.saldo == null ? '—' : fmtChf(row.saldo)}</td>
      </tr>
    `;
  }).join('');
}

async function runSearch(){
  const params = new URLSearchParams();

  const accountIds = selectedValues('f-accounts');
  const categoryIds = selectedValues('f-categories');
  const years = selectedValues('f-years');
  const months = selectedValues('f-months');
  const rawDescriptions = parseMultiText('f-raw');
  const recipients = parseMultiText('f-recipient');
  const groupBy = document.getElementById('f-group-by')?.value || '';

  if(accountIds.length) params.set('account_ids', accountIds.join(','));
  if(categoryIds.length) params.set('category_ids', categoryIds.join(','));
  if(years.length) params.set('years', years.join(','));
  if(months.length) params.set('months', months.join(','));
  if(rawDescriptions.length) params.set('raw_descriptions', rawDescriptions.join(','));
  if(recipients.length) params.set('recipients', recipients.join(','));
  if(groupBy) params.set('group_by', groupBy);

  const res = await fetch(`/api/transactions/search?${params.toString()}`);
  if(!res.ok){
    throw new Error('Search request failed');
  }

  const data = await res.json();
  setTotals(data.totals || {positive:0, negative:0, sum:0, count:0});

  if(data.group_by){
    renderGroupedRows(data.rows || []);
  }else{
    renderTransactionRows(data.rows || []);
  }
}

function resetSearch(){
  ['f-accounts','f-categories','f-years','f-months'].forEach(id => {
    const el = document.getElementById(id);
    if(!el) return;
    Array.from(el.options).forEach(opt => { opt.selected = false; });
  });
  document.getElementById('f-raw').value = '';
  document.getElementById('f-recipient').value = '';
  document.getElementById('f-group-by').value = '';
  runSearch();
}

function splitTokens(value){
  return value.split(/[;,]/).map(s => s.trim()).filter(Boolean);
}

function setTokensWithLast(input, tokens, last){
  const prefix = tokens.join('; ');
  const suffix = last ? `${prefix ? '; ' : ''}${last}` : '';
  input.value = `${prefix}${suffix}`;
}

function replaceLastToken(input, replacement){
  const parts = input.value.split(/[;,]/);
  const existing = parts.slice(0, -1).map(s => s.trim()).filter(Boolean);
  existing.push(replacement);
  input.value = `${existing.join('; ')}; `;
}

function initTokenSuggest(inputId, boxId, options){
  const input = document.getElementById(inputId);
  const box = document.getElementById(boxId);
  if(!input || !box) return;

  const hide = () => {
    box.style.display = 'none';
    box.innerHTML = '';
  };

  const render = () => {
    const raw = input.value || '';
    const allTokens = splitTokens(raw);
    const parts = raw.split(/[;,]/);
    const last = (parts[parts.length - 1] || '').trim().toLowerCase();

    if(!last){
      hide();
      return;
    }

    const selectedNormalized = new Set(allTokens.map(t => t.toLowerCase()));
    const matches = options
      .filter(opt => opt && opt.toLowerCase().includes(last))
      .filter(opt => !selectedNormalized.has(opt.toLowerCase()))
      .slice(0, 12);

    if(!matches.length){
      hide();
      return;
    }

    box.innerHTML = matches
      .map(opt => `<button type="button" class="suggest-item" data-value="${escapeHtml(opt)}">${escapeHtml(opt)}</button>`)
      .join('');
    box.style.display = 'block';
  };

  input.addEventListener('input', render);
  input.addEventListener('focus', render);
  box.addEventListener('click', (event) => {
    const btn = event.target.closest('.suggest-item');
    if(!btn) return;
    const value = btn.getAttribute('data-value') || '';
    // data-value contains escaped text, but textContent is already decoded.
    replaceLastToken(input, btn.textContent || value);
    hide();
    input.focus();
  });

  document.addEventListener('click', (event) => {
    if(event.target === input || box.contains(event.target)) return;
    hide();
  });
}

function enableClickToggleMultiSelect(selectId){
  const select = document.getElementById(selectId);
  if(!select) return;
  select.addEventListener('mousedown', (event) => {
    const target = event.target;
    if(!(target instanceof HTMLOptionElement)) return;
    event.preventDefault();
    target.selected = !target.selected;
    select.dispatchEvent(new Event('change'));
  });
}

(function initSearchPage(){
  const rawOptions = JSON.parse(document.getElementById('raw-options-data')?.textContent || '[]');
  const recipientOptions = JSON.parse(document.getElementById('recipient-options-data')?.textContent || '[]');

  document.getElementById('run-search')?.addEventListener('click', runSearch);
  document.getElementById('reset-search')?.addEventListener('click', resetSearch);
  ['f-accounts', 'f-categories', 'f-years', 'f-months'].forEach(enableClickToggleMultiSelect);
  initTokenSuggest('f-raw', 'raw-suggest', rawOptions);
  initTokenSuggest('f-recipient', 'recipient-suggest', recipientOptions);
  runSearch();
})();
