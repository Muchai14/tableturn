import {backend, API_BASE_URL} from './api.js';
'use strict';
const $ = (q, root = document) => root.querySelector(q);
const $$ = (q, root = document) => [...root.querySelectorAll(q)];
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storage = {get(k){try{return localStorage.getItem(k)}catch{return null}},set(k,v){try{localStorage.setItem(k,v)}catch{}},remove(k){try{localStorage.removeItem(k)}catch{}}};
let serverOffset = 0, lastSync = null, failed = false;
const now = () => Date.now() + serverOffset;
function toast(message){const el=$('#toast');el.textContent=message;el.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.hidden=true,4200)}
const api = (...args) => backend.request(...args);
const mutation = (...args) => backend.mutate(...args);
function qrImage(el, path) {
  const code = window.qrcode(0, 'M');
  code.addData(new URL(path, location.origin).href);
  code.make();
  el.src = code.createDataURL(5, 15);
}
async function loadBrand() {
  try {
    const settings = await api('/api/public-settings');
    $$('.restaurant-name,.guest-location').forEach(el=>el.textContent=settings.name);
    $$('input[type=number]').forEach(el=>el.max=settings.max_party_size);
  } catch { /* The page's own polling presents connection errors. */ }
}
loadBrand();
if ($('#logout-form')) $('#logout-form').onsubmit = async event => {
  event.preventDefault();
  const button = $('button', event.currentTarget); button.disabled = true;
  try { await backend.logout(); location.href='/staff/login'; }
  catch (error) { toast(error.message); button.disabled=false; }
};
if (document.body.dataset.page === 'login') {
  const form=$('#login-form');
  form.onsubmit=async event=>{
    event.preventDefault(); const button=$('[type=submit]',form); button.disabled=true;
    $('#login-error').hidden=true;
    try { await backend.login($('#username').value,$('#password').value); location.href='/staff'; }
    catch(error){$('#login-error').textContent=error.message;$('#login-error').hidden=false;}
    finally{button.disabled=false;}
  };
}
function synced(data){if(data.server_time)serverOffset=Date.parse(data.server_time)-Date.now();lastSync=new Date();failed=false;const b=$('#connection-warning');if(b)b.hidden=true;const el=$('#sync-status');if(el)el.textContent='Updated just now'}
function disconnected(){failed=true;const b=$('#connection-warning');if(b){b.textContent='Connection lost—status may be out of date. Retrying automatically.';b.hidden=false}const el=$('#sync-status');if(el)el.textContent=lastSync?'Last updated '+lastSync.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}):'Unable to connect'}
function countdown(deadline){const sec=Math.max(0,Math.ceil((Date.parse(deadline)-now())/1000));return `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`}
function elapsed(time){return `${Math.max(0,Math.floor((now()-Date.parse(time))/60000))} min`}
function tick(){
  $$('[data-wait]').forEach(el=>el.textContent=elapsed(el.dataset.wait));
  $$('[data-deadline]').forEach(el=>{const expired=Date.parse(el.dataset.deadline)<=now();el.textContent=expired?(el.dataset.large?'00:00':'Time elapsed'):countdown(el.dataset.deadline);el.classList.toggle('expired',expired)});
  if(lastSync&&!failed&&$('#sync-status'))$('#sync-status').textContent='Updated '+(Math.floor((Date.now()-lastSync)/1000)<5?'just now':Math.floor((Date.now()-lastSync)/1000)+'s ago');
}
setInterval(tick,1000);
$$('[data-step]').forEach(btn=>btn.addEventListener('click',()=>{const input=$('input',btn.parentElement);input.value=Math.max(+input.min,Math.min(+input.max,(+input.value||1)+ +btn.dataset.step));input.dispatchEvent(new Event('input',{bubbles:true}))}));
function confirmAction(title,copy,label){return new Promise(resolve=>{const d=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-copy').textContent=copy;$('[value=confirm]',d).textContent=label;d.returnValue='';d.addEventListener('close',()=>resolve(d.returnValue==='confirm'),{once:true});d.showModal()})}
function poll(fn){fn();setInterval(()=>{if(!document.hidden)fn()},5000);window.addEventListener('focus',fn);document.addEventListener('visibilitychange',()=>{if(!document.hidden)fn()})}

if(document.body.dataset.page==='dashboard'){
  let data=null, selected=null, selectedVersion=null, loading=false;
  const panel=$('#party-panel');
  const empty=(title,copy,symbol='⌁')=>`<div class="empty-state"><span class="empty-symbol" aria-hidden="true">${symbol}</span><h3>${title}</h3><p>${copy}</p></div>`;
  function render(){
    const focused=document.activeElement;
    const focusSelector=focused?.dataset?.edit ? `[data-edit="${focused.dataset.edit}"]` : focused?.dataset?.action ? `[data-action="${focused.dataset.action}"][data-id="${focused.dataset.id}"]` : null;
    const {waiting,ready,recent,settings}=data;
    $('#wait-count').textContent=waiting.length;$('#ready-count').textContent=ready.length;
    $('#mobile-wait-count').textContent=waiting.length;$('#mobile-ready-count').textContent=ready.length+(ready.some(p=>p.overdue)?' · Review':'');
    $('#party-total').textContent=waiting.length+ready.length;$('#guest-total').textContent=[...waiting,...ready].reduce((n,p)=>n+p.size,0);
    $('#open-toggle').checked=settings.is_open;$('#open-toggle').disabled=false;$('#open-dot').classList.toggle('closed',!settings.is_open);
    $('#open-title').textContent=settings.is_open?'Waitlist is open':'Sign-ups are closed';$('#open-subtitle').textContent=settings.is_open?'Guests can join from the restaurant QR code.':'Your active parties are still on the list.';
    $('#service-date').textContent=new Intl.DateTimeFormat('en-US',{weekday:'long',month:'long',day:'numeric',timeZone:settings.timezone}).format(new Date()).toUpperCase()+' · TODAY’S SERVICE';
    $('#waiting-list').innerHTML=waiting.length?waiting.map((p,i)=>`<div class="party-row"><div class="party-info"><span class="position">${i+1}</span><button class="party-detail" data-edit="${p.id}" aria-label="Edit ${escapeHTML(p.name)}"><span class="party-name">${escapeHTML(p.name)}</span><span class="party-meta">${p.size} ${p.size===1?'guest':'guests'}</span></button></div><span class="wait-time" data-wait="${p.joined_at}">${elapsed(p.joined_at)}</span><button class="button small-button ready-action" data-action="ready" data-id="${p.id}">Mark ready <span aria-hidden="true">↗</span></button></div>`).join(''):empty('No parties waiting.','Add a party or invite guests to scan the restaurant QR code.');
    $('#ready-list').innerHTML=ready.length?ready.map(p=>`<div class="ready-row ${p.overdue?'overdue':''}"><div class="ready-row-top"><button class="party-detail" data-edit="${p.id}" aria-label="Edit ${escapeHTML(p.name)}"><span class="party-name">${escapeHTML(p.name)}</span><span class="party-meta">${p.size} ${p.size===1?'guest':'guests'}</span></button><span class="countdown ${p.overdue?'expired':''}" data-deadline="${p.deadline}">${p.overdue?'Time elapsed':countdown(p.deadline)}</span></div><div class="ready-row-bottom"><span class="ready-caption">${p.overdue?'<span class="review-label">Review</span>':'Awaiting guest'}</span><div class="row-actions">${p.overdue?`<button class="text-button danger-text" data-action="no_show" data-id="${p.id}">No-show</button>`:''}<button class="button small-button primary" data-action="seat" data-id="${p.id}">Seat party →</button></div></div></div>`).join(''):empty('No tables awaiting guests.','Parties appear here when you mark their table ready.','◷');
    const labels={seated:'Seated',no_show:'No-show',cancelled:'Cancelled'};
    $('#recent-list').innerHTML=recent.length?recent.map(p=>`<div class="recent-row"><span class="recent-name">${escapeHTML(p.name)}</span><span class="recent-size">${p.size} guests</span><span class="recent-state">${labels[p.state]}</span>${p.can_undo?`<button class="text-button" data-action="undo" data-id="${p.id}">Undo ↶</button>`:''}</div>`).join(''):'<p class="recent-empty">Seated, cancelled, and no-show parties will appear here.</p>';
    tick();
    if(focusSelector)$(focusSelector)?.focus({preventScroll:true});
  }
  async function refresh(){if(loading)return;loading=true;try{data=await api('/api/staff/queue');synced(data);render()}catch{disconnected()}finally{loading=false}}
  const find=id=>data&&[...data.waiting,...data.ready,...data.recent].find(p=>p.id===id);
  function showExtra(p){$('#party-extra').hidden=false;qrImage($('#party-qr'),p.status_url);$('#guest-link').href=p.status_url;$('#return-party').hidden=p.state!=='ready';$('#cancel-party').hidden=!['waiting','ready'].includes(p.state)}
  function openParty(p){selected=p?.id||null;selectedVersion=p?.version||null;$('#panel-title').textContent=p?'Edit party':'Add a party';$('#party-name').value=p?.name||'';$('#party-size').value=p?.size||2;$('#save-party').textContent=p?'Save changes':'Add to waitlist';$('#panel-error').hidden=true;$('#party-extra').hidden=!p;if(p)showExtra(p);$('#party-times').textContent=p?'Joined '+new Date(p.joined_at).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})+' · '+(p.state==='ready'?'Table ready':'Waiting'):'';panel.showModal();$('#party-name').focus()}
  $('#add-party').onclick=()=>openParty(null);$('#close-panel').onclick=()=>panel.close();
  $('#party-form').onsubmit=async e=>{e.preventDefault();const btn=$('#save-party');btn.disabled=true;$('#panel-error').hidden=true;
    try{const body={name:$('#party-name').value,size:Number($('#party-size').value)};let result;
      if(selected){result=await mutation('/api/staff/parties/'+selected,{...body,version:selectedVersion},'PATCH');toast('Party updated');panel.close()}
      else{result=await mutation('/api/staff/parties',body);toast('Party added to the waitlist');selected=result.party.id;selectedVersion=result.party.version;$('#panel-title').textContent='Party added';$('#save-party').textContent='Save changes';showExtra(result.party)}
      await refresh();
    }catch(err){$('#panel-error').textContent=err.message;$('#panel-error').hidden=false;await refresh();if(err.status===409&&selected){const latest=find(selected);if(latest){selectedVersion=latest.version;$('#party-name').value=latest.name;$('#party-size').value=latest.size;showExtra(latest)}}}finally{btn.disabled=false}
  };
  async function act(p,action,btn){if(!p)return;
    if(['cancel','no_show'].includes(action)){const ok=await confirmAction(action==='cancel'?'Cancel this party?':'Mark as a no-show?',`${p.name}, party of ${p.size}, will leave the active queue. You can undo this from Recently completed.`,action==='cancel'?'Cancel party':'Mark no-show');if(!ok)return}
    if(btn)btn.disabled=true;
    try{await mutation('/api/staff/parties/'+p.id+'/actions',{action,version:p.version});const messages={ready:'Table marked ready · five-minute timer started',seat:'Party seated. Enjoy the meal!',no_show:'Party marked as a no-show',cancel:'Party cancelled',undo:'Previous status restored',return:'Party returned to its original waiting position'};toast(messages[action]);if(panel.open)panel.close();await refresh()}catch(e){toast(e.message);await refresh()}finally{if(btn)btn.disabled=false}
  }
  document.addEventListener('click',e=>{const edit=e.target.closest('[data-edit]');if(edit)openParty(find(edit.dataset.edit));const btn=e.target.closest('[data-action]');if(btn)act(find(btn.dataset.id),btn.dataset.action,btn)});
  $('#cancel-party').onclick=e=>act(find(selected),'cancel',e.currentTarget);$('#return-party').onclick=e=>act(find(selected),'return',e.currentTarget);
  $('#copy-link').onclick=async()=>{try{await navigator.clipboard.writeText(new URL($('#guest-link').getAttribute('href'),location.origin).href);toast('Private link copied')}catch{toast('Open the guest page and copy its address.')}};
  $('#open-toggle').onchange=async e=>{const el=e.currentTarget;el.disabled=true;try{await mutation('/api/staff/settings',{is_open:el.checked,version:data.settings.version},'PATCH');toast(el.checked?'Guest sign-ups opened':'Guest sign-ups closed')}catch(err){toast(err.message)}await refresh()};
  $('#join-qr').onclick=()=>{qrImage($('#join-qr-image'),'/join');$('#qr-dialog').showModal();};$('#close-qr').onclick=()=>$('#qr-dialog').close();
  $$('[data-tab]').forEach(btn=>btn.onclick=()=>{$$('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b===btn)));$('.queue-grid').dataset.active=btn.dataset.tab});
  backend.getSession().then(s=>{if(!s.authenticated)location.href='/staff/login';else poll(refresh)}).catch(()=>poll(refresh));
  setInterval(()=>{if(data&&data.ready.some(p=>!p.overdue&&Date.parse(p.deadline)<=now())){data.ready.forEach(p=>p.overdue=Date.parse(p.deadline)<=now());render()}},1000);
}
if(document.body.dataset.page==='summary')poll(async()=>{try{const d=await api('/api/staff/summary');synced(d);$('#metric-seated').textContent=d.seated;$('#metric-no-shows').textContent=d.no_shows;$('#metric-average').innerHTML=d.average_wait===null?'—':`${d.average_wait}<small> min</small>`;$('#summary-date').textContent=new Date(d.date+'T12:00:00').toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});$('#summary-zone').textContent='Restaurant timezone: '+d.timezone.replaceAll('_',' ')}catch{disconnected()}});
if(document.body.dataset.page==='join'){
  $('#join-form').insertAdjacentHTML('beforebegin','<div id="connection-warning" class="warning-banner" role="alert" hidden></div>');
  let existing=false;const form=$('#join-form');
  async function check(){try{const old=storage.get('tableturn-entry:'+API_BASE_URL);if(old&&/^\/status\/[A-Za-z0-9_-]{43}$/.test(old)){try{const d=await api('/api'+old);existing=['waiting','ready'].includes(d.party.state);if(existing){$('#existing-link').href=old;$('#existing-entry').hidden=false;form.hidden=true;$('#closed-message').hidden=true;synced(d);return}else storage.remove('tableturn-entry:'+API_BASE_URL)}catch(e){if(e.status===404)storage.remove('tableturn-entry:'+API_BASE_URL);else throw e}}const s=await api('/api/public-settings');synced(s);form.hidden=!s.is_open;$('#closed-message').hidden=s.is_open;$('#existing-entry').hidden=true;$('#guest-size').max=s.max_party_size}catch{disconnected()}}
  form.onsubmit=async e=>{e.preventDefault();const btn=$('[type=submit]',form);btn.disabled=true;$('#join-error').hidden=true;try{const d=await mutation('/api/join',{name:$('#guest-name').value,size:Number($('#guest-size').value)});storage.set('tableturn-entry:'+API_BASE_URL,d.status_url);location.href=d.status_url}catch(err){$('#join-error').textContent=err.message;$('#join-error').hidden=false;if(err.status===409)await check()}finally{btn.disabled=false}};
  poll(check);
}
if(document.body.dataset.page==='guest'){
  const token=location.pathname.split('/').pop();let current=null,signature='';
  function renderGuest(p){const overdue=p.state==='ready'&&Date.parse(p.deadline)<=now();const sig=JSON.stringify([p.state,p.name,p.size,p.ahead,p.deadline,overdue]);if(signature===sig)return;signature=sig;const card=$('.status-card');card.classList.toggle('is-ready',p.state==='ready'&&!overdue);card.classList.toggle('is-overdue',overdue);const details=`<div class="status-party"><strong>${escapeHTML(p.name)}</strong><span>Party of ${p.size}</span></div>`;let content='';
    if(p.state==='waiting')content=`<span class="eyebrow">YOUR PLACE IS SAVED</span><strong class="status-number">${p.ahead}</strong><h1 class="status-caption">${p.ahead===0?'No parties ahead':p.ahead===1?'party ahead':'parties ahead'}</h1>${details}<p class="status-message">Keep this page open and check back for your table.</p><p class="status-note">Seating order may vary by party size.</p>`;
    else if(p.state==='ready')content=overdue?`<span class="eyebrow">YOUR HOST CAN HELP</span><h1>Please check<br>with the host.</h1>${details}<p class="status-message">Your return time has passed. Your host will help with the next step.</p>`:`<span class="eyebrow">A TABLE FOR YOU</span><h1>Your table<br>is ready.</h1><p class="status-message">Please return to the host.</p><span class="big-countdown" data-large="true" data-deadline="${p.deadline}" aria-live="off">${countdown(p.deadline)}</span><p class="field-help">Time to return</p>${details}`;
    else {const m={seated:['ENJOY YOUR MEAL','You’re seated.','Enjoy your meal!'],no_show:['PLEASE SEE THE HOST','We missed you.','Your party was marked as a no-show. Please see the host.'],cancelled:['WAITLIST UPDATE','Entry cancelled.','Your waitlist entry has been cancelled. Please see the host if you need help.']}[p.state];content=`<span class="eyebrow">${m[0]}</span><h1>${m[1]}</h1>${details}<p class="status-message">${m[2]}</p>`}
    $('#guest-status').innerHTML=content;
  }
  poll(async()=>{try{const d=await api('/api/status/'+token);synced(d);current=d.party;renderGuest(current);if(['waiting','ready'].includes(current.state))storage.set('tableturn-entry:'+API_BASE_URL,location.pathname);else if(storage.get('tableturn-entry:'+API_BASE_URL)===location.pathname)storage.remove('tableturn-entry:'+API_BASE_URL)}catch(e){if(e.status===404){$('#guest-status').innerHTML='<span class="eyebrow">LET’S FIND YOUR PARTY</span><h1>Link unavailable.</h1><p class="status-message">This waitlist link is unavailable. Please see the host.</p>';current=null;$('#sync-status').textContent=''}else disconnected()}});
  setInterval(()=>{if(current)renderGuest(current)},1000);
}
