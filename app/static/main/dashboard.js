// Hilfsfunktionen
function fmt(v){return v==null?'—':'CHF '+v.toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2})}
function toast(msg,ok=true){const t=document.getElementById('toast');t.textContent=msg;t.style.background=ok?'#1a2a1a':'#2a1a1a';t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3000)}
function categoryHtml(name){return name?`<span class="category-chip">${name}</span>`:'<span class="badge badge-gray">Nicht kategorisiert</span>'}
let categoryCache=[];

function showTab(name, btn){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  btn.classList.add('active');
  // Tab-Zustand in URL schreiben (kein Reload)
  const url=new URL(window.location);
  url.searchParams.set('tab', name);
  history.replaceState({}, '', url);
}

// Beim Laden: Tab aus URL-Parameter wiederherstellen
(function(){
  const tab=new URL(window.location).searchParams.get('tab');
  if(tab==='rechnungen'){
    const btns=document.querySelectorAll('.tab-btn');
    showTab('rechnungen', btns[1]);
  }else if(tab==='kategorien'){
    const btns=document.querySelectorAll('.tab-btn');
    showTab('kategorien', btns[2]);
  }
  reloadCategories();
})();

// E-Banking Detailpositionen ein-/ausklappen
function toggleLines(id, btn){
  const row=document.getElementById('lines-'+id);
  const open=row.style.display==='table-row';
  row.style.display=open?'none':'table-row';
  const n=btn.dataset.count;
  btn.textContent=(open?'▶ ':'▼ ')+n+' Positionen';
}

function toggleMonat(btn){
  const body=btn.nextElementSibling;
  const open=body.style.display!=='none';
  body.style.display=open?'none':'block';
  btn.classList.toggle('open',!open);
}

// PDF-Import
async function runImport(btn){
  btn.disabled=true; btn.textContent='⏳ Importiere…';
  try{
    const r=await fetch('/import',{method:'POST'});
    const d=await r.json();
    const s=d.stats;
    toast(`✅ Import: ${s.transactions.imported} neue Buchungen, ${s.invoices.imported} neue Rechnungen`);
    setTimeout(()=>window.location.reload(),1500);
  }catch(e){
    toast('❌ Import fehlgeschlagen',false);
    btn.disabled=false; btn.textContent='🔄 PDFs importieren';
  }
}

// Buchungs-Titel bearbeiten
async function editTransaction(id, currentTitle){
  const neu=prompt('Titel korrigieren:', currentTitle);
  if(neu===null) return;
  const r=await fetch(`/api/transactions/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:neu||null})
  });
  if(r.ok){
    const d=await r.json();
    const row=document.querySelector(`tr[data-id="${id}"] .td-desc`);
    if(row) row.textContent=d.display_title;
    toast('✅ Titel gespeichert');
  } else toast('❌ Fehler',false);
}

async function updateTransactionCategory(id, categoryId){
  const r=await fetch(`/api/transactions/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({category_id:categoryId?parseInt(categoryId,10):null})
  });
  if(r.ok){
    const d=await r.json();
    const el=document.getElementById(`tx-category-${id}`);
    if(el) el.innerHTML=categoryHtml(d.category_name);
    toast('✅ Kategorie gespeichert');
  } else toast('❌ Fehler',false);
}

// Rechnungs-Titel bearbeiten
async function editInvoiceTitle(id, currentTitle){
  const neu=prompt('Titel korrigieren:', currentTitle);
  if(neu===null) return;
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:neu||null})
  });
  if(r.ok){
    const d=await r.json();
    const card=document.getElementById(`inv-${id}`);
    if(card) card.querySelector('.rechnung-title').textContent=d.display_title;
    toast('✅ Titel gespeichert');
    const remember=confirm('Diesen Titel auch für ähnliche Rechnungen merken?');
    if(remember) await rememberInvoiceTitle(id, d.display_title, d.raw_issuer || '', false);
  } else toast('❌ Fehler',false);
}

async function rememberInvoiceTitle(id, currentTitle, rawIssuer, askConfirm=true){
  if(!rawIssuer){
    toast('❌ Kein Rechnungssteller erkannt', false);
    return;
  }
  const title=(currentTitle||'').trim();
  if(!title){
    toast('❌ Kein Titel zum Merken vorhanden', false);
    return;
  }
  if(askConfirm){
    const ok=confirm(`Titel für ähnliche Rechnungen merken?\n\nRechnungssteller: ${rawIssuer}\nTitel: ${title}`);
    if(!ok) return;
  }
  const r=await fetch(`/api/invoices/${id}/remember-title`,{
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title})
  });
  if(r.ok){
    toast('✅ Titel-Regel gespeichert');
  } else {
    toast('❌ Regel konnte nicht gespeichert werden', false);
  }
}

// Total aller offenen Rechnungen neu berechnen
function recalcTotal(){
  let sum=0;
  document.querySelectorAll('.rechnung-card').forEach(card=>{
    sum+=parseFloat(card.dataset.amount||0);
  });
  const el=document.getElementById('kpi-total');
  if(el) el.textContent='CHF '+sum.toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2});
}

// Rechnungs-Betrag bearbeiten
async function editInvoiceAmount(id, currentAmount){
  const neu=prompt('Betrag korrigieren (CHF):', currentAmount||'');
  if(neu===null) return;
  const parsed=neu ? parseFloat(neu.replace(',','.').replace(/'/g,'').replace(/ /g,'')) : null;
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({amount: parsed})
  });
  if(r.ok){
    const d=await r.json();
    const newAmt=d.amount||0;
    const fmtAmt=newAmt ? 'CHF '+newAmt.toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2}) : '—';
    // Inline-Betrag aktualisieren
    const el=document.getElementById(`inv-amount-${id}`);
    if(el) el.textContent=fmtAmt;
    // Karten-Header aktualisieren
    const hdr=document.getElementById(`inv-header-amount-${id}`);
    if(hdr) hdr.textContent=fmtAmt;
    // data-amount auf Karte setzen → Total korrekt
    const card=document.getElementById(`inv-${id}`);
    if(card) card.dataset.amount=newAmt;
    recalcTotal();
    toast('✅ Betrag gespeichert');
  } else toast('❌ Fehler',false);
}

// Rechnungs-Fälligkeit bearbeiten
async function editInvoiceDueDate(id, currentDate){
  const neu=prompt('Fälligkeitsdatum (TT.MM.JJJJ):', currentDate ? currentDate.split('-').reverse().join('.') : '');
  if(neu===null) return;
  let isoDate=null;
  if(neu.trim()){
    const parts=neu.trim().split('.');
    if(parts.length===3) isoDate=`${parts[2].length===2?'20'+parts[2]:parts[2]}-${parts[1].padStart(2,'0')}-${parts[0].padStart(2,'0')}`;
    if(!isoDate || isNaN(Date.parse(isoDate))){ toast('❌ Ungültiges Datum (TT.MM.JJJJ)',false); return; }
  }
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({due_date: isoDate})
  });
  if(r.ok){
    const d=await r.json();
    const el=document.getElementById(`inv-due-${id}`);
    if(el && d.due_date) el.textContent=d.due_date.split('-').reverse().join('.');
    else if(el) el.textContent='—';
    toast('✅ Datum gespeichert');
  } else toast('❌ Fehler',false);
}

async function editInvoiceSourceYear(id, currentYear){
  const neu=prompt('Filter-Jahr (JJJJ, leer = automatisch aus Fälligkeitsdatum):', currentYear||'');
  if(neu===null) return;
  const clean=neu.trim();
  let payloadYear=null;
  if(clean){
    if(!/^\d{4}$/.test(clean)){toast('❌ Ungültiges Jahr (JJJJ)',false);return;}
    payloadYear=parseInt(clean,10);
  }
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({source_year: payloadYear})
  });
  if(r.ok){
    const d=await r.json();
    const el=document.getElementById(`inv-source-year-${id}`);
    const effectiveYear=d.source_year || (d.due_date ? d.due_date.slice(0,4) : null);
    if(el) el.textContent=effectiveYear || '—';
    toast('✅ Filter-Jahr gespeichert');
  } else toast('❌ Fehler',false);
}

// PDF im Standard-Programm öffnen
async function openPdf(filename){
  try{
    const r=await fetch(`/open-pdf/${encodeURIComponent(filename)}`);
    if(r.ok) toast('📄 PDF geöffnet');
    else toast('❌ PDF nicht gefunden',false);
  }catch(e){toast('❌ Fehler beim Öffnen',false);}
}

// Rechnungs-Status ändern
async function updateInvoiceStatus(id, status){
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({status})
  });
  if(r.ok) toast(`✅ Status auf «${status}» gesetzt`);
  else toast('❌ Fehler',false);
}

async function updateInvoiceCategory(id, categoryId){
  const r=await fetch(`/api/invoices/${id}`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({category_id:categoryId?parseInt(categoryId,10):null})
  });
  if(r.ok){
    const d=await r.json();
    const el=document.getElementById(`inv-category-${id}`);
    if(el) el.innerHTML=categoryHtml(d.category_name);
    toast('✅ Kategorie gespeichert');
  } else toast('❌ Fehler',false);
}

async function deleteInvoice(id, filename){
  const ok = confirm(`Rechnung wirklich löschen?\n\n${filename}\n\nDie PDF-Datei bleibt erhalten und kann später erneut importiert werden.`);
  if(!ok) return;
  const r = await fetch(`/api/invoices/${id}`, {method:'DELETE'});
  if(r.ok){
    const card=document.getElementById(`inv-${id}`);
    if(card) card.remove();
    recalcTotal();
    const remaining=document.querySelectorAll('#tab-rechnungen .rechnung-card').length;
    if(remaining===0){
      const tab=document.getElementById('tab-rechnungen');
      const existing=tab.querySelector('.empty');
      if(!existing){
        const p=document.createElement('p');
        p.className='empty';
        p.textContent='Keine Rechnungen gefunden.';
        tab.appendChild(p);
      }
    }
    toast('✅ Rechnung gelöscht');
  } else {
    toast('❌ Rechnung konnte nicht gelöscht werden', false);
  }
}

function categoryUsageText(cat){
  return `${cat.usage_total} genutzt`;
}

function categoryDetailsText(cat){
  return `Buchungen: ${cat.tx_count} · Rechnungen: ${cat.invoice_count} · Regeln: ${cat.rule_count}`;
}

function renderCategories(cats){
  categoryCache=cats||[];
  const body=document.getElementById('categories-body');
  if(!body) return;
  const parentSelect=document.getElementById('cat-new-parent');
  if(parentSelect){
    parentSelect.innerHTML='<option value="">Kein Parent (Root)</option>'+categoryCache
      .map(cat=>`<option value="${cat.id}">${cat.path || cat.name}</option>`)
      .join('');
  }
  if(!categoryCache.length){
    body.innerHTML='<tr><td colspan="5" class="empty">Keine Kategorien vorhanden.</td></tr>';
    return;
  }
  body.innerHTML=categoryCache.map(cat=>`
    <tr data-name="${(cat.name||'').toLowerCase()}">
      <td><strong>${cat.path || cat.name}</strong></td>
      <td>
        <select class="category-select" onchange="changeCategoryParent(${cat.id}, this.value)">
          <option value="">Kein Parent (Root)</option>
          ${categoryCache
            .filter(other=>other.id!==cat.id)
            .map(other=>`<option value="${other.id}" ${cat.parent_id===other.id?'selected':''}>${other.path || other.name}</option>`)
            .join('')}
        </select>
      </td>
      <td>
        <span class="badge ${cat.usage_total>0?'badge-blue':'badge-gray'}">${categoryUsageText(cat)}</span>
      </td>
      <td style="color:var(--muted)">${categoryDetailsText(cat)}</td>
      <td>
        <button class="edit-btn btn-sm" onclick="renameCategory(${cat.id}, '${(cat.name||'').replace(/'/g, "\\'")}')">✏️ Umbenennen</button>
        <button class="edit-btn btn-sm" style="border-color:var(--red);color:var(--red)" onclick="deleteCategory(${cat.id}, '${(cat.name||'').replace(/'/g, "\\'")}', ${cat.deletable ? 'true' : 'false'})">🗑️ Löschen</button>
      </td>
    </tr>
  `).join('');
  filterCategoryRows();
}

function filterCategoryRows(){
  const q=(document.getElementById('cat-search')?.value||'').trim().toLowerCase();
  const rows=document.querySelectorAll('#categories-body tr[data-name]');
  rows.forEach(row=>{
    const name=row.dataset.name||'';
    row.style.display=!q || name.includes(q) ? '' : 'none';
  });
}

async function reloadCategories(){
  const body=document.getElementById('categories-body');
  if(body) body.innerHTML='<tr><td colspan="5" class="empty">Lade Kategorien…</td></tr>';
  try{
    const r=await fetch('/api/categories');
    if(!r.ok) throw new Error('load failed');
    const data=await r.json();
    renderCategories(data);
  }catch(_e){
    if(body) body.innerHTML='<tr><td colspan="5" class="empty">Kategorien konnten nicht geladen werden.</td></tr>';
    toast('❌ Kategorien konnten nicht geladen werden', false);
  }
}

async function createCategory(){
  const name=(document.getElementById('cat-new-name')?.value||'').trim();
  const parent=document.getElementById('cat-new-parent')?.value||'';
  const clean=name.trim();
  if(!clean){toast('❌ Name darf nicht leer sein', false);return;}
  const r=await fetch('/api/categories',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:clean,parent_id:parent?parseInt(parent,10):null})
  });
  if(r.ok){
    toast('✅ Kategorie erstellt');
    const input=document.getElementById('cat-new-name');
    const parentSel=document.getElementById('cat-new-parent');
    if(input) input.value='';
    if(parentSel) parentSel.value='';
    window.location.reload();
  }else{
    toast('❌ Kategorie konnte nicht erstellt werden', false);
  }
}

async function renameCategory(id, currentName){
  const name=prompt('Kategorie umbenennen:', currentName||'');
  if(name===null) return;
  const clean=name.trim();
  if(!clean){toast('❌ Name darf nicht leer sein', false);return;}
  const r=await fetch(`/api/categories/${id}`,{
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:clean})
  });
  if(r.ok){
    toast('✅ Kategorie umbenannt');
    window.location.reload();
  }else{
    toast('❌ Kategorie konnte nicht umbenannt werden', false);
  }
}

async function changeCategoryParent(id, parentId){
  const r=await fetch(`/api/categories/${id}`,{
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({parent_id:parentId?parseInt(parentId,10):null})
  });
  if(r.ok){
    toast('✅ Kategorie-Hierarchie gespeichert');
    window.location.reload();
  }else{
    toast('❌ Parent konnte nicht gespeichert werden (evtl. Zyklus)', false);
    window.location.reload();
  }
}

async function deleteCategory(id, name, deletable){
  if(!deletable){
    toast('❌ Kategorie ist noch in Benutzung und kann nicht gelöscht werden', false);
    return;
  }
  const ok=confirm(`Kategorie wirklich löschen?\n\n${name}`);
  if(!ok) return;
  const r=await fetch(`/api/categories/${id}`,{method:'DELETE'});
  if(r.ok){
    toast('✅ Kategorie gelöscht');
    window.location.reload();
  }else{
    toast('❌ Kategorie konnte nicht gelöscht werden', false);
  }
}

// Chart
(function(){
  const chartNode=document.getElementById('chart-data');
  if(!chartNode) return;
  const months = JSON.parse(chartNode.textContent || '{}');
  if(!months.labels) return;
  const ctx=document.getElementById('monatsChart').getContext('2d');
  new Chart(ctx,{
    type:'bar',
    data:{
      labels:months.labels,
      datasets:[
        {label:'Einnahmen',data:months.income,backgroundColor:'rgba(76,175,135,.7)',borderRadius:4},
        {label:'Ausgaben', data:months.expense,backgroundColor:'rgba(224,92,106,.7)', borderRadius:4},
      ]
    },
    options:{
      responsive:true,
      plugins:{legend:{labels:{color:'#8b91b8'}}},
      scales:{
        x:{ticks:{color:'#8b91b8'},grid:{color:'#2e3352'}},
        y:{ticks:{color:'#8b91b8',callback:v=>'CHF '+v.toLocaleString('de-CH')},grid:{color:'#2e3352'}},
      }
    }
  });
})();
