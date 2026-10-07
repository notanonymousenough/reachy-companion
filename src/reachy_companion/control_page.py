"""Small LAN control page; token stays in the browser session, not in URLs sent to the server."""
PAGE = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ричи</title>
<style>body{font:17px system-ui;background:#101820;color:#edf4f7;margin:0;padding:24px}main{max-width:440px;margin:8vh auto}h1{font-size:36px}button,input{box-sizing:border-box;width:100%;font:inherit;padding:16px;border-radius:14px;border:0;margin:8px 0}button{background:#8be0bc;color:#0d2b20;cursor:pointer}button:disabled{opacity:.5;cursor:wait}input{background:#263744;color:white}small{color:#b5c5ce}#status{padding:20px 0;min-height:40px}#logout{background:#263744;color:#b5c5ce;padding:10px}#switch.off{background:#f5b7a6;color:#49271f}</style>
<main><h1>Ричи</h1><div id="login"><p>Доступ к управлению</p><input id="token" type="password" placeholder="Токен из secrets/token" autocomplete="off"><button id="connect">Подключиться</button><small>На ПК можно открыть эту страницу командой hub control или скриптом control.ps1.</small></div>
<div id="controls" hidden><div id="status" role="status" aria-live="polite">Подключение…</div><button id="switch" disabled>Проверяем микрофон…</button><p><small>При выключении Ричи перестаёт записывать и отвечать. Настройка сохраняется после перезапуска.</small></p><button id="share">Ссылка для телефона</button><input id="sharelink" readonly hidden aria-label="Ссылка для управления"><button id="logout">Закрыть доступ на этом устройстве</button></div></main>
<script>
let token='',state=null,busy=false;
try{token=decodeURIComponent(location.hash.slice(1))||sessionStorage.getItem('reachy-control-token')||''}catch(e){}
history.replaceState(null,'',location.pathname);
const el=id=>document.getElementById(id);
function show(){el('login').hidden=!!token;el('controls').hidden=!token}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});if(r.status===401){token='';sessionStorage.removeItem('reachy-control-token');show();throw Error('Неверный токен')}if(!r.ok)throw Error('Хаб или робот недоступен');return r.json()}
function render(){const enabled=state.microphone_enabled;el('switch').classList.toggle('off',enabled);el('switch').textContent=enabled?'Выключить микрофон':'Включить микрофон';el('switch').disabled=busy;el('status').textContent=enabled?(state.phase==='speaking'?'Микрофон включён · Ричи отвечает':state.phase==='processing'?'Микрофон включён · Ричи думает':state.phase==='paused'?'Микрофон включён · прослушивание приостановлено':'Микрофон включён · Ричи слушает'):(state.capture_active?'Микрофон выключается…':'Микрофон выключен · Ричи молчит');}
async function refresh(){if(!token||busy)return;try{state=await api('/control/status');render()}catch(e){el('status').textContent=e.message;el('switch').disabled=true}}
el('connect').onclick=()=>{token=el('token').value.trim();if(!token)return;try{sessionStorage.setItem('reachy-control-token',token)}catch(e){}el('token').value='';show();refresh()};
el('share').onclick=()=>{el('sharelink').hidden=false;el('sharelink').value=location.origin+'/control#'+encodeURIComponent(token);el('sharelink').select()};
el('logout').onclick=()=>{token='';state=null;try{sessionStorage.removeItem('reachy-control-token')}catch(e){}show()};
el('switch').onclick=async()=>{if(!state||busy)return;busy=true;el('switch').disabled=true;el('status').textContent='Меняем настройку…';try{await api('/control/microphone',{enabled:!state.microphone_enabled})}catch(e){el('status').textContent=e.message}finally{busy=false;refresh()}};
show();refresh();setInterval(refresh,2000);
</script></html>'''
