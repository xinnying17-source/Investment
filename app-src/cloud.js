// Login + cloud progress for the standalone app (Supabase email/password auth).
(function(){
  const cfg=window.APP_CONFIG||{};
  const configured=cfg.SUPABASE_URL&&!/YOUR-PROJECT/.test(cfg.SUPABASE_URL)&&cfg.SUPABASE_ANON_KEY&&!/YOUR-ANON-KEY/.test(cfg.SUPABASE_ANON_KEY)&&window.supabase;
  const KEEP='ig-keep', OWNER='ig-owner', PKEY='invest-guide-v1';
  const ls={get:k=>{try{return localStorage.getItem(k);}catch(e){return null;}},set:(k,v)=>{try{localStorage.setItem(k,v);}catch(e){}},del:k=>{try{localStorage.removeItem(k);}catch(e){}}};
  const keep=()=>ls.get(KEEP)!=='0';
  let lang=ls.get('ig-lang')==='en'?'en':'zh';const T=(zh,en)=>lang==='en'?en:zh;
  const store={getItem:k=>{try{return (keep()?localStorage:sessionStorage).getItem(k);}catch(e){return null;}},
    setItem:(k,v)=>{try{(keep()?localStorage:sessionStorage).setItem(k,v);(keep()?sessionStorage:localStorage).removeItem(k);}catch(e){}},
    removeItem:k=>{try{localStorage.removeItem(k);sessionStorage.removeItem(k);}catch(e){}}};
  const css=`.auth{position:fixed;inset:0;z-index:100;background:var(--bg);display:flex;align-items:center;justify-content:center;padding:max(16px,env(safe-area-inset-top,0px)) max(16px,env(safe-area-inset-right,0px)) max(16px,env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px));overflow-y:auto}
.auth[hidden]{display:none!important}
.acard{width:min(420px,100%);background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:24px;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:14px}
.alogo{display:flex;align-items:center;gap:12px}.alogo img{width:52px;height:52px;border-radius:14px}
.alogo h1{font-size:28px}.alogo p{color:var(--muted);font-size:13px}
.aseg{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.aseg button{border:0;background:var(--surface);padding:10px;font-weight:500}.aseg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.acard label{display:flex;flex-direction:column;gap:5px;font-size:14px;font-weight:500}
.acard input[type=email],.acard input[type=password]{font:inherit;color:var(--ink);background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
.acard label.row{flex-direction:row;align-items:center;gap:8px;font-weight:400}
.acard label.row input{width:18px;height:18px;accent-color:var(--accent)}
.amsg{font-size:13.5px;min-height:1em}.amsg.err{color:var(--bad)}.amsg.ok{color:var(--good)}
.alink{background:none;border:0;color:var(--accent);padding:0;text-decoration:underline;align-self:flex-start;font-size:13.5px}
.acct{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);flex-wrap:wrap}
.alang{display:flex;justify-content:flex-end;gap:4px}.alang button{border:1px solid var(--line);background:var(--surface2);border-radius:8px;padding:3px 10px;font-size:12.5px}.alang button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.acct button{border:1px solid var(--line);background:var(--surface2);border-radius:8px;padding:3px 10px;font-size:12.5px}`;
  const st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
  const box=document.createElement('div');box.className='auth';box.id='auth';
  function drawForm(){box.innerHTML=`<form class="acard" id="aform" novalidate>
   <div class="alang"><button type="button" data-l="zh" aria-pressed="${lang==='zh'}">中文</button><button type="button" data-l="en" aria-pressed="${lang==='en'}">English</button></div>
   <div class="alogo"><img src="icons/icon-192.png" alt=""><div><h1>${T('投资白话地图','Plain-Talk Investing Map')}</h1><p>${T('登入后，学习进度和模拟器会保存到云端，换手机或电脑也能接着学。','Sign in to save your learning progress and simulator to the cloud, so you can continue on any phone or computer.')}</p></div></div>
   <div class="aseg" id="aseg"><button type="button" data-m="in" aria-pressed="true">${T('登录','Sign in')}</button><button type="button" data-m="up" aria-pressed="false">${T('注册新账号','Create account')}</button></div>
   <label for="a-email">Email<input type="email" id="a-email" autocomplete="email" required></label>
   <label for="a-pw" id="a-pwl">${T('密码','Password')}<input type="password" id="a-pw" autocomplete="current-password" minlength="6" required></label>
   <label for="a-pw2" id="a-pw2l" hidden>${T('再输入一次密码','Repeat password')}<input type="password" id="a-pw2" autocomplete="new-password" minlength="6"></label>
   <label class="row" for="a-keep"><input type="checkbox" id="a-keep" checked>${T('保持登录（这台设备下次不用再登录）','Keep me signed in on this device')}</label>
   <button class="btn primary" type="submit" id="a-go">${T('登录','Sign in')}</button>
   <button class="alink" type="button" id="a-forgot">${T('忘记密码？','Forgot password?')}</button>
   <p class="amsg" id="a-msg" aria-live="polite"></p>
   <button class="alink" type="button" id="a-offline">${T('先不登录，只在这台设备上使用','Continue without an account (this device only)')}</button>
  </form>`;}
  drawForm();
  let mode='in';
  function setMode(m){mode=m;box.querySelectorAll('#aseg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.m===m));
    $a('#a-pw2l').hidden=m!=='up'&&m!=='reset';$a('#a-pwl').hidden=m==='forgot';$a('#a-email').closest('label').hidden=m==='reset';
    $a('#a-go').textContent={in:T('登录','Sign in'),up:T('注册','Create account'),forgot:T('发送重设密码邮件','Send reset email'),reset:T('设置新密码','Set new password')}[m];
    $a('#a-pw').autocomplete=m==='in'?'current-password':'new-password';$a('#a-forgot').hidden=m!=='in';$a('#a-keep').closest('label').hidden=m==='forgot'||m==='reset';msg('');}
  const $a=q=>box.querySelector(q);
  const msg=(t,c)=>{const el=$a('#a-msg');el.textContent=t;el.className='amsg'+(c?' '+c:'');};
  function zh(e){const m=(e&&e.message||'')+'';if(/Invalid login/i.test(m))return T('Email 或密码不正确。','Wrong email or password.');if(/Email not confirmed/i.test(m))return T('这个账号还没确认，请先到邮箱点击确认链接。','This account isn’t confirmed yet. Click the link in your confirmation email first.');if(/already registered|already exists/i.test(m))return T('这个 Email 已经注册过了，请直接登录。','This email is already registered. Please sign in.');if(/Password should be/i.test(m))return T('密码至少要 6 个字符。','Passwords need at least 6 characters.');if(/rate limit|too many/i.test(m))return T('尝试太多次了，请稍后再试。','Too many attempts. Please try again later.');if(/fetch|network/i.test(m))return T('连不上服务器，请检查网络。','Can’t reach the server. Check your connection.');return m||T('发生错误，请再试一次。','Something went wrong. Please try again.');}

  let resolveUser;const userReady=new Promise(r=>resolveUser=r);let client=null,user=null;
  function showAccount(u){if(!document.querySelector('.top .meter')&&document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>showAccount(u));return;}let el=document.getElementById('acct');if(!el){el=document.createElement('div');el.className='acct';el.id='acct';const meter=document.querySelector('.top .meter');(meter?meter.parentNode:document.body).appendChild(el);}
    el.innerHTML='';const sp=document.createElement('span');sp.textContent='👤 '+u.email;const b=document.createElement('button');b.textContent=T('登出','Sign out');b.onclick=async()=>{try{await client.auth.signOut();}catch(e){}ls.del(PKEY);ls.del(OWNER);location.reload();};el.append(sp,b);}
  function signedIn(u){user=u;box.hidden=true;showAccount(u);resolveUser(u);}

  if(!configured){
    // Cloud not set up yet: app still works with on-device progress.
    return;
  }
  client=window.supabase.createClient(cfg.SUPABASE_URL,cfg.SUPABASE_ANON_KEY,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true,storage:store,storageKey:'ig-auth'}});
  document.body.appendChild(box);box.hidden=true;
  function wire(){
  box.querySelectorAll('#aseg button').forEach(b=>b.onclick=()=>setMode(b.dataset.m));
  $a('#a-forgot').onclick=()=>setMode('forgot');
  $a('#a-offline').onclick=()=>{box.hidden=true;resolveUser(null);};
  $a('#a-keep').checked=keep();
  $a('#aform').addEventListener('submit',async e=>{e.preventDefault();const email=$a('#a-email').value.trim(),pw=$a('#a-pw').value,pw2=$a('#a-pw2').value;const go=$a('#a-go');
    if(mode!=='reset'&&!/^\S+@\S+\.\S+$/.test(email)){msg(T('请输入正确的 Email。','Please enter a valid email.'),'err');return;}
    if((mode==='in'||mode==='up'||mode==='reset')&&pw.length<6){msg(T('密码至少要 6 个字符。','Passwords need at least 6 characters.'),'err');return;}
    if((mode==='up'||mode==='reset')&&pw!==pw2){msg(T('两次输入的密码不一样。','The passwords don’t match.'),'err');return;}
    ls.set(KEEP,$a('#a-keep').checked?'1':'0');go.disabled=true;msg(T('处理中…','Working…'));
    try{
      if(mode==='in'){const {data,error}=await client.auth.signInWithPassword({email,password:pw});if(error)throw error;signedIn(data.user);}
      else if(mode==='up'){const {data,error}=await client.auth.signUp({email,password:pw,options:{emailRedirectTo:location.origin+location.pathname}});if(error)throw error;
        if(data.session)signedIn(data.user);else{setMode('in');msg(T('注册成功！请到 '+email+' 的邮箱点击确认链接，然后回来登录。','Account created! Click the confirmation link sent to '+email+', then come back and sign in.'),'ok');}}
      else if(mode==='forgot'){const {error}=await client.auth.resetPasswordForEmail(email,{redirectTo:location.origin+location.pathname});if(error)throw error;msg(T('已发送。请到邮箱点击链接重设密码。','Sent. Click the link in your email to reset your password.'),'ok');}
      else if(mode==='reset'){const {data,error}=await client.auth.updateUser({password:pw});if(error)throw error;msg(T('密码已更新。','Password updated.'),'ok');signedIn(data.user);}
    }catch(err){msg(zh(err),'err');}finally{go.disabled=false;}});
  box.querySelectorAll('[data-l]').forEach(x=>x.onclick=()=>{lang=x.dataset.l;ls.set('ig-lang',lang);if(typeof window.setLang==='function')window.setLang(lang);const k=$a('#a-keep').checked,em=$a('#a-email').value,md=mode;drawForm();wire();$a('#a-keep').checked=k;$a('#a-email').value=em;setMode(md);});
  }
  wire();
  client.auth.onAuthStateChange((ev,session)=>{if(ev==='PASSWORD_RECOVERY'){box.hidden=false;setMode('reset');}});
  client.auth.getSession().then(({data})=>{const s=data&&data.session;if(s&&s.user)signedIn(s.user);else{box.hidden=false;setMode('in');}}).catch(()=>{box.hidden=false;});

  window.CLOUD={
    async load(){const u=await userReady;if(!u)throw new Error('offline');
      const fresh=ls.get(OWNER)!==u.id;ls.set(OWNER,u.id);
      const {data,error}=await client.from('progress').select('data').eq('user_id',u.id).maybeSingle();if(error)throw error;
      return {data:data?data.data:null,fresh};},
    async save(d){if(!user)throw new Error('no user');const {error}=await client.from('progress').upsert({user_id:user.id,data:d,updated_at:new Date().toISOString()});if(error)throw error;}
  };
})();
