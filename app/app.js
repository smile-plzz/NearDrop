'use strict';
const $ = id => document.getElementById(id);
let lastFiles = '', lastNotes = '';
let state = null, pairingToken = '', stopped = false, refreshing = false, queue = [], busy = false, inviteExpires = 0, toastTimer;
const bytes = n => n < 1024 ? n + ' B' : n < 1048576 ? (n/1024).toFixed(1)+' KB' : n < 1073741824 ? (n/1048576).toFixed(1)+' MB' : (n/1073741824).toFixed(1)+' GB';
const date = t => new Date(t*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
function el(tag, text, cls) {const e=document.createElement(tag); if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function toast(message) { $('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6000); }
async function api(path, data, signal) {
  const options={credentials:'same-origin',signal};
  if(data!==undefined)Object.assign(options,{method:'POST',headers:{'Content-Type':'application/json','X-NearDrop':'1'},body:JSON.stringify(data)});
  const res=await fetch(path,options); const result=await res.json();
  if(!res.ok){const e=new Error(result.error||'Connection failed');e.status=res.status;throw e;}return result;
}
function action(fn){return async(...args)=>{try{await fn(...args);}catch(e){toast(e.message||'Could not connect to the laptop.');}};}
async function copy(text) {
  if(navigator.clipboard && window.isSecureContext) {await navigator.clipboard.writeText(text);toast('Copied');return;}
  const t=el('textarea');t.value=text;t.setAttribute('readonly','');document.body.append(t);t.select();t.setSelectionRange(0,text.length);
  const ok=document.execCommand('copy');t.remove();toast(ok?'Copied':'Select and copy the text manually.');
}
function showPair(){lastFiles='';lastNotes='';state=null;$('pair').hidden=false;$('dashboard').hidden=true;$('connection').textContent='Not paired';$('manualPair').hidden=!!pairingToken;}
async function refresh(){
  if(stopped||refreshing)return;refreshing=true;
  try{state=await api('/api/state');$('pair').hidden=true;$('dashboard').hidden=false;$('connection').textContent='● '+state.device;$('version').textContent=state.version;
    for(const id of ['pairDevice','openFolder','stop'])$(id).hidden=!state.host;
    $('disconnect').hidden=state.host;
    const fk=JSON.stringify(state.files),nk=JSON.stringify(state.notes);
    if(fk!==lastFiles){renderFiles();lastFiles=fk;}if(nk!==lastNotes){renderNotes();lastNotes=nk;}renderSpace();
  }catch(e){if(e.status===401){showPair();}else{$('connection').textContent='Reconnecting…';}}finally{refreshing=false;}
}
function renderFiles(){
  if(!state)return;
  const root=$('files');root.replaceChildren();const search=$('search').value.toLowerCase();const files=state.files.filter(x=>x.name.toLowerCase().includes(search));$('fileCount').textContent=state.files.length;
  if(!files.length){root.append(el('div',search?'No matching files.':'Your shared files will land here.','empty'));return;}
  for(const f of files){
    const row=el('div',undefined,'file-row');row.append(el('div',f.name.includes('.')?f.name.split('.').pop().slice(0,4):'FILE','file-icon'));
    const info=el('div',undefined,'file-info'),name=el('div',f.name,'file-name');name.title=f.name+'\nSHA-256: '+f.sha256;info.append(name,el('div',bytes(f.size)+' · '+f.device+' · '+date(f.created),'meta'));
    const a=el('a','↓','download');a.href='/download/'+f.id;a.download=f.name;a.setAttribute('aria-label','Download '+f.name);row.append(info,a);
    if(state.host){const del=el('button','×','delete');del.setAttribute('aria-label','Delete '+f.name);del.onclick=action(async()=>{if(confirm('Permanently delete “'+f.name+'” from NearDrop?')){await api('/api/delete',{id:f.id,kind:'file'});await refresh();}});row.append(del);}root.append(row);
  }
}
function renderNotes(){
  const root=$('notes');root.replaceChildren();
  for(const n of state.notes){const card=el('div',undefined,'note');card.append(el('p',n.text),el('div',n.device+' · '+date(n.created),'meta'));const actions=el('div',undefined,'note-actions'),btn=el('button','Copy','quiet');btn.onclick=action(()=>copy(n.text));actions.append(btn);
    try{const u=new URL(n.text);if(['http:','https:'].includes(u.protocol)){const a=el('a','Open link ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';actions.append(a);}}catch{}
    if(state.host){const del=el('button','Delete','quiet danger');del.onclick=action(async()=>{if(confirm('Delete this note?')){await api('/api/delete',{id:n.id,kind:'note'});await refresh();}});actions.append(del);}card.append(actions);root.append(card);
  }
}
function renderSpace(){
  $('space').replaceChildren();const line=el('div',undefined,'space-line');line.append(el('span','Laptop storage available'),el('strong',bytes(state.free)));$('space').append(line);
  if(state.host){const p=el('p',state.folder,'small');p.title=state.folder;$('space').append(p);}
  $('devices').replaceChildren();for(const d of state.devices){const row=el('div',undefined,'device');row.append(el('span',(d.host?'▣ ':'▯ ')+d.name));if(!d.host){const b=el('button','Disconnect');b.onclick=action(async()=>{await api('/api/revoke',{id:d.id});await refresh();});row.append(b);}$('devices').append(row);}
}
function queueDraw(){
  const root=$('queue');root.replaceChildren();
  for(const item of queue){const card=el('div',undefined,'transfer'),top=el('div',undefined,'transfer-top');top.append(el('span',item.file.name),el('strong',Math.floor(item.offset/Math.max(1,item.file.size)*100)+'%'));
    const p=el('progress');p.max=Math.max(1,item.file.size);p.value=item.done?Math.max(1,item.file.size):item.offset;top.lastChild.textContent=item.done?'100%':top.lastChild.textContent;
    card.append(top,p,el('small',item.message||'Queued'));
    const controls=el('div');
    if(item.failed){const retry=el('button','Retry / resume');retry.onclick=()=>{item.failed=false;item.message='Queued';runQueue();};controls.append(retry);}
    if(!item.done&&!item.cancelled){const cancel=el('button','Cancel');cancel.onclick=action(async()=>{item.cancelled=true;item.controller?.abort();item.message='Cancelled';if(item.id)await api('/api/upload/cancel',{id:item.id});queueDraw();});controls.append(cancel);}
    if(item.done||item.cancelled){const dismiss=el('button','Dismiss');dismiss.onclick=()=>{queue=queue.filter(x=>x!==item);queueDraw();};controls.append(dismiss);}
    card.append(controls);root.append(card);
  }
}
function addFiles(files){for(const file of files){if(file.size>20*1024**3){toast(file.name+': maximum size is 20 GB.');continue;}queue.push({file,offset:0,message:'Queued',id:null,failed:false,done:false,cancelled:false});}queueDraw();runQueue();}
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function runQueue(){
  if(busy)return;busy=true;
  try{for(const item of queue){if(item.done||item.failed||item.cancelled)continue;item.controller=new AbortController();const signal=item.controller.signal;
    try{let retries=0;while(!item.done&&!item.cancelled){
      try{
        const start=await api('/api/upload/start',{name:item.file.name,size:item.file.size,id:item.id},signal);item.id=start.id;item.offset=start.offset;
        if(start.complete){item.done=true;break;}
        const started=Date.now(),base=item.offset;
        while(item.offset<item.file.size&&!item.cancelled){
          const blob=item.file.slice(item.offset,item.offset+1048576);
          const response=await fetch('/api/upload/chunk?id='+item.id+'&offset='+item.offset,{method:'POST',headers:{'X-NearDrop':'1','Content-Type':'application/octet-stream'},body:blob,signal,credentials:'same-origin'});
          const result=await response.json();if(!response.ok){const e=new Error(result.error);e.status=response.status;throw e;}
          item.offset=result.offset;const speed=(item.offset-base)/Math.max(.01,(Date.now()-started)/1000);item.message=bytes(item.offset)+' / '+bytes(item.file.size)+' · '+bytes(speed)+'/s';queueDraw();
        }
        if(item.cancelled)break;
        item.message='Finishing and calculating checksum…';queueDraw();await api('/api/upload/finish',{id:item.id},signal);item.done=true;
      }catch(e){if(item.cancelled||e.name==='AbortError')break;if([401,403,413,507].includes(e.status)||retries>=3)throw e;retries++;item.message='Connection interrupted. Resuming in '+retries+'s…';queueDraw();await delay(retries*1000);}
    }
    if(item.done){item.message='Saved on laptop · Ready to download';await refresh();}
    }catch(e){if(!item.cancelled){item.failed=true;item.message=e.message||'Connection lost. Retry when the laptop is available.';}}
    finally{queueDraw();}
  }}finally{busy=false;}
}
async function newInvite(){const data=await api('/api/invite',{address:$('network').value});$('qr').src=data.qr;$('inviteUrl').value=data.url;inviteExpires=data.expires;updateExpiry();}
function updateExpiry(){if(!inviteExpires)return;const remaining=Math.max(0,Math.ceil(inviteExpires-Date.now()/1000));$('expiry').textContent=remaining?'One-use link · Expires in '+Math.floor(remaining/60)+':'+String(remaining%60).padStart(2,'0'):'Code expired. Generate a new code.';}
$('pairDevice').onclick=action(async()=>{$('network').replaceChildren(...state.addresses.map(a=>{const o=el('option',a);o.value=a;return o;}));await newInvite();$('pairDialog').showModal();});
$('closeDialog').onclick=()=>$('pairDialog').close();$('network').onchange=action(newInvite);$('newInvite').onclick=action(newInvite);$('copyInvite').onclick=action(()=>copy($('inviteUrl').value));
$('connect').onclick=action(async()=>{
  let token=pairingToken;if(!token){try{token=new URL($('pairLink').value).hash.slice(1).split('pair=')[1];}catch{throw new Error('Paste the full pairing link shown on your laptop.');}}
  if(!token)throw new Error('Scan the laptop QR code or paste its pairing link.');
  $('connect').disabled=true;try{await api('/api/pair',{token,name:$('deviceName').value||'My phone'});pairingToken='';await refresh();}finally{$('connect').disabled=false;}
});
$('fileInput').onchange=e=>{addFiles([...e.target.files]);e.target.value='';};
const drop=$('dropZone');for(const name of ['dragenter','dragover'])drop.addEventListener(name,e=>{e.preventDefault();drop.classList.add('drag');});for(const name of ['dragleave','drop'])drop.addEventListener(name,e=>{e.preventDefault();drop.classList.remove('drag');});drop.addEventListener('drop',e=>addFiles([...e.dataTransfer.files]));
window.addEventListener('dragover',e=>e.preventDefault());window.addEventListener('drop',e=>e.preventDefault());
$('search').oninput=renderFiles;
$('sendNote').onclick=action(async()=>{const text=$('noteText').value.trim();if(!text){toast('Enter some text or a link first.');return;}$('sendNote').disabled=true;try{await api('/api/note',{text});$('noteText').value='';toast('Shared with your devices');await refresh();}finally{$('sendNote').disabled=false;}});
$('openFolder').onclick=action(()=>api('/api/open-folder',{}));
$('disconnect').onclick=action(async()=>{await api('/api/logout',{});showPair();});
$('stop').onclick=action(async()=>{if(confirm('Stop sharing and disconnect all devices? Your saved files will remain.')){await api('/api/stop',{});stopped=true;$('connection').textContent='Stopped';$('dashboard').hidden=true;toast('NearDrop stopped. Launch it again on your laptop to reconnect.');}});
window.addEventListener('beforeunload',e=>{if(queue.some(x=>!x.done&&!x.cancelled)){e.preventDefault();e.returnValue='';}});
async function init(){
  const fragment=new URLSearchParams(location.hash.slice(1));const host=fragment.get('host');pairingToken=fragment.get('pair')||'';history.replaceState(null,'',location.pathname);
  $('deviceName').value=/iPhone/.test(navigator.userAgent)?'My iPhone':/Android/.test(navigator.userAgent)?'My Android':'My device';
  if(host){try{await api('/api/bootstrap',{token:host});}catch(e){toast(e.message);}}
  if(pairingToken){showPair();}else{await refresh();}
  setInterval(()=>{if(!document.hidden&&!pairingToken)refresh();},4000);setInterval(updateExpiry,1000);
}
init();
