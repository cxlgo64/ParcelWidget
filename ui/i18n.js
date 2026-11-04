/* Strings for both pages (index.html = the character, settings.html = the settings window). */
const I18N = {
  en: {
    ok:'Got it', close:'Close', save:'Save', cancel:'Cancel', saved:'Saved', copied:'Copied',
    justNow:'just now', minAgo:m=>`${m} min ago`, hrAgo:h=>`${h} h ago`, dayAgo:d=>`${d} d ago`,
    browsers:{chrome:'Google Chrome', msedge:'Microsoft Edge', brave:'Brave', chromium:'Chromium (bundled)', firefox:'Firefox', webkit:'WebKit (Safari engine)'},
    err:{
      blocked:'Blocked by parcelsapp. Try another browser in Parcel Settings.',
      no_data:'No data from parcelsapp yet (too new, or blocked).',
      browser_missing:b=>`${b} not found. Install it, or pick another browser in Parcel Settings.`,
      failed:a=>`Lookup failed: ${a}`,
    },
    waiting:'Waiting for the first check…', updating:'Updating…', manual:'Added by hand',
    // ---- her balloon ----
    report:{
      parcels:{startup:'📦 Parcel check', manual:'📦 Parcel check', scheduled:'📦 Parcel update', install:'📦 Parcels'},
      skin:{make:'🎨 New skin'},
    },
    p:{
      mailOff:'📭 Gmail isn\'t connected, so I only check numbers you add.',
      mailReading:(n,t)=> t ? `📬 Reading Gmail… ${n}/${t}` : '📬 Opening Gmail',
      soFar:k=>`${k} found`,
      mailNone:t=> t ? `📬 Read ${t} shipping email${t>1?'s':''}, no tracking numbers.` : '📬 No shipping emails lately.',
      mailDone:(t,k,nw)=>`📬 Read ${t} email${t>1?'s':''}: ${k} number${k>1?'s':''}` + (nw ? `, <b>${nw} new</b>` : ', nothing new'),
      mailErr:e=>`📭 Couldn't read Gmail: ${e}`,
      trackRun:(i,t,c,n)=>`🔎 Asking parcelsapp ${i}/${t}: ${c} <code>${n}</code>`,
      trackDone:t=>`🔎 Checked ${t} on parcelsapp`, trackNone:'🔎 Nothing to look up',
      sum:s=>{ const p=[]; if(s.delivered.length) p.push(`<b>${s.delivered.length} delivered</b> 🎉`);
        if(s.moved.length) p.push(`${s.moved.length} moved`); if(s.new.length) p.push(`${s.new.length} new`);
        return p.length ? '✨ ' + p.join(', ') : '✨ No changes'; },
      sumErr:k=>`⚠️ ${k} lookup${k>1?'s':''} failed`,
      runErr:e=>`⚠️ Something went wrong: ${e}`,
      installing:b=>`⬇️ Downloading ${b} for parcelsapp (first time only)`, installed:b=>`✅ ${b} is ready, checking again.`,
      install_failed:b=>`⚠️ Couldn't download ${b}. Pick another browser in Parcel Settings.`,
      setup:'Connect Gmail', next:t=>`Next check ${t}`, checkNow:'⟳ Check now', checking:'Checking…',
      list:'📦 Packages', none:'No packages right now.', got:'✓ Got it', refresh:'Check again', open:'Open on parcelsapp',
      archive:'Stop tracking',
      addPh:'Paste a tracking number', add:'Add', tooShort:'That\'s too short for a tracking number.',
      added:n=>`Added ${n}, checking it…`,
      cached:(t,nx)=>`🕒 From the check at ${t}` + (nx ? ` (next one at ${nx})` : ''),
    },
    sk:{
      run:(nm,l,s,t)=>`🎨 Drawing “${nm}”: ${l} (${s}/${t})`, done:nm=>`🎨 “${nm}” is ready and I'm wearing it!`,
      partial:(nm,r)=>`🎨 “${nm}” is ready, but these poses failed: ${r}.`, err:(nm,e)=>`🎨 Couldn't make “${nm}”: ${e}`,
      cancelled:nm=>`🎨 Stopped making “${nm}”.`,
    },
    sys:{title:'📊 System', cpu:'CPU', ram:'RAM', down:'Download', up:'Upload', per:s=>`one candle = ${s<60?s+' s':(s/60)+' min'}`,
      noPsutil:'Can\'t read system stats (psutil missing).', warming:'Collecting data…'},
    pet:{
      hello:['Hi! Let me check on things for you.','Good to see you!'],
      poke:['Hehe, that tickles!','Need something?','I\'m on it, promise!','♪～','Hmm?','Boop!'],
      allDone:['All good! I\'ll keep watch.','Done! Call me if you need me.'],
      delivered:c=>`Your ${c} package was delivered! 🎉`, newPkg:n=>`${n} new package${n>1?'s':''}!`,
      sleep:'zzz…', wake:'Oh! I wasn\'t sleeping!',
    },
    // ---- settings window ----
    title:'Settings', tabs:{general:'General', parcels:'📦 Parcels', sysmon:'📊 System', skin:'🎨 Custom skin'},
    language:'Language', size:'Screen size', sizeHint:'Her size and the balloon scale together.',
    onTop:'Keep on top of other windows',
    skin:'Character', side:'Stand on', sideLeft:'Left', sideRight:'Right', addSkin:'Custom',
    deleteSkin:'Delete this skin', deleteConfirm:n=>`Delete the skin "${n}"?`,
    packages:'Packages', addPh:'Tracking number', add:'Add', tooShort:'Number too short', added:'Added, checking…',
    noPackages:'No packages yet. Add numbers in her balloon (hover over her → 📦), or connect Gmail below.',
    archived:'Archived', restore:'Restore', noArchived:'Nothing archived yet', del:'Delete',
    schedule:'Automatic checks', from:'From', to:'to', every:'every', minutes:'min',
    scheduleHint:'She also checks once when the widget starts. Automatic checks only speak up when something changes.',
    gmail:'Gmail', gmailAddr:'Gmail address', appPw:'App password',
    pwHint:'Google Account → Security → 2-Step Verification → App passwords. Stored in the macOS Keychain.',
    pwSaved:'✓ Password saved. ', pwKeep:'leave empty to keep', scanDays:'Scan emails from the last N days',
    tracking:'Lookups', browser:'Browser used to read parcelsapp',
    browserHint:'If lookups get blocked or return no data, switch to another browser. Firefox / WebKit / Chromium download automatically the first time.',
    headless:'Run the browser in the background (invisible)',
    period:'Each candle covers', colors:'Candle colors', colorsAuto:'By language', greenUp:'Green up, red down', redUp:'Red up, green down',
    sysHint:'CPU, memory and network are sampled every second and kept for an hour.',
    csIntro:'Describe a character (and/or pick a picture of it). An image AI draws all its poses and the widget turns them into an animated skin.',
    csName:'Name', csDesc:'What does the character look like?', csDescPh:'e.g. an orange tabby cat girl in a courier uniform with a little cap',
    csRef:'Reference picture (optional)', csPick:'Choose…', csRefNo:'This provider can\'t use pictures; only the description is used.',
    csProvider:'Image AI', csKeySaved:'✓ Key saved in the macOS Keychain. Leave empty to keep it. ', csGetKey:'Get a key ↗',
    csAdvanced:'Advanced: model / endpoint', csModel:'Model (empty = default)', csEndpoint:'Endpoint (empty = default)',
    csGenerate:'Generate', csCost:'About 10 image requests. Takes a few minutes; you can close this window meanwhile. Charged by the provider.',
    csStep:(s,t,l)=>`Step ${s}/${t}: ${l}`, csDone:'Done! Your new skin is on.', csPartial:r=>`Done, but these poses failed: ${r}`,
    csErr:e=>`Failed: ${e}`, csCancelled:'Cancelled', csBusy:'Already making a skin.', csNoKey:'Enter the API key.',
    csNoDesc:'Describe the character or choose a picture.',
    csLabels:{base:'drawing the character', assemble:'putting the sheet together', done:'done',
      idle:'standing', walk_right:'walking', wave:'waving', jump:'jumping', sleep:'sleeping', cheer:'cheering', think:'thinking', shy:'shy', look_right:'looking around'},
  },
  zh: {
    ok:'好的', close:'关闭', save:'保存', cancel:'取消', saved:'已保存', copied:'已复制',
    justNow:'刚刚', minAgo:m=>`${m} 分钟前`, hrAgo:h=>`${h} 小时前`, dayAgo:d=>`${d} 天前`,
    browsers:{chrome:'Google Chrome', msedge:'Microsoft Edge', brave:'Brave', chromium:'Chromium（内置）', firefox:'Firefox', webkit:'WebKit（Safari 内核）'},
    err:{
      blocked:'被 parcelsapp 拦截了，可以在快递设置里换个浏览器',
      no_data:'parcelsapp 还没有数据（单号太新或被限制）',
      browser_missing:b=>`没有找到 ${b}，请安装或在快递设置里换一个浏览器`,
      failed:a=>`查询失败：${a}`,
    },
    waiting:'等待首次查询…', updating:'正在刷新…', manual:'手动添加',
    report:{
      parcels:{startup:'📦 快递检查', manual:'📦 快递检查', scheduled:'📦 快递有新动态', install:'📦 快递'},
      skin:{make:'🎨 新皮肤'},
    },
    p:{
      mailOff:'📭 还没连接 Gmail，所以只查你手动添加的单号。',
      mailReading:(n,t)=> t ? `📬 正在读 Gmail… ${n}/${t}` : '📬 正在打开 Gmail',
      soFar:k=>`已找到 ${k} 个`,
      mailNone:t=> t ? `📬 读了 ${t} 封物流邮件，里面没有单号` : '📬 最近没有物流邮件',
      mailDone:(t,k,nw)=>`📬 读了 ${t} 封邮件：${k} 个单号` + (nw ? `，<b>${nw} 个是新的</b>` : '，没有新的'),
      mailErr:e=>`📭 读取 Gmail 失败：${e}`,
      trackRun:(i,t,c,n)=>`🔎 正在问 parcelsapp ${i}/${t}：${c} <code>${n}</code>`,
      trackDone:t=>`🔎 在 parcelsapp 查了 ${t} 个`, trackNone:'🔎 没有需要查的',
      sum:s=>{ const p=[]; if(s.delivered.length) p.push(`<b>${s.delivered.length} 个已送达</b> 🎉`);
        if(s.moved.length) p.push(`${s.moved.length} 个有新进展`); if(s.new.length) p.push(`${s.new.length} 个新快递`);
        return p.length ? '✨ ' + p.join('，') : '✨ 没有变化'; },
      sumErr:k=>`⚠️ ${k} 个查询失败`,
      runErr:e=>`⚠️ 出错了：${e}`,
      installing:b=>`⬇️ 正在下载 ${b}，用来查 parcelsapp（只需一次）`, installed:b=>`✅ ${b} 准备好了，重新查一次。`,
      install_failed:b=>`⚠️ ${b} 下载失败，去快递设置里换个浏览器吧。`,
      setup:'连接 Gmail', next:t=>`下次检查 ${t}`, checkNow:'⟳ 立即检查', checking:'检查中…',
      list:'📦 快递', none:'现在没有快递。', got:'✓ 收到', refresh:'再查一次', open:'在 parcelsapp 打开',
      archive:'不再追踪',
      addPh:'粘贴单号', add:'添加', tooShort:'这个太短了，不像单号。',
      added:n=>`已添加 ${n}，正在查询…`,
      cached:(t,nx)=>`🕒 这是 ${t} 检查的结果` + (nx ? `（下次 ${nx}）` : ''),
    },
    sk:{
      run:(nm,l,s,t)=>`🎨 正在画「${nm}」：${l}（${s}/${t}）`, done:nm=>`🎨 「${nm}」做好了，已经换上啦！`,
      partial:(nm,r)=>`🎨 「${nm}」做好了，但这些动作没成功：${r}。`, err:(nm,e)=>`🎨 「${nm}」没做成：${e}`,
      cancelled:nm=>`🎨 已停止制作「${nm}」。`,
    },
    sys:{title:'📊 系统状态', cpu:'CPU', ram:'内存', down:'下载', up:'上传', per:s=>`每根 ${s<60?s+' 秒':(s/60)+' 分钟'}`,
      noPsutil:'读不到系统状态（缺少 psutil）。', warming:'正在收集数据…'},
    pet:{
      hello:['你好呀！我先帮你看看～','欢迎回来！'],
      poke:['嘿嘿，好痒～','有什么吩咐？','我一直在看着呢！','♪～','嗯？','戳回去！'],
      allDone:['都好啦！我在旁边守着～','搞定！有事叫我～'],
      delivered:c=>`你的 ${c} 快递送到啦！🎉`, newPkg:n=>`发现 ${n} 个新快递！`,
      sleep:'zzz…', wake:'诶！我、我没睡着！',
    },
    title:'设置', tabs:{general:'通用', parcels:'📦 快递', sysmon:'📊 系统状态', skin:'🎨 自定义皮肤'},
    language:'语言', size:'屏幕尺寸', sizeHint:'角色和台词框一起缩放。',
    onTop:'窗口置顶',
    skin:'角色', side:'站在', sideLeft:'左边', sideRight:'右边', addSkin:'自定义',
    deleteSkin:'删除这个皮肤', deleteConfirm:n=>`删除皮肤「${n}」？`,
    packages:'快递', addPh:'输入单号', add:'添加', tooShort:'单号太短', added:'已添加，正在查询',
    noPackages:'还没有快递。在台词框里添加单号（鼠标放在她身上 → 📦），或在下面连接 Gmail。',
    archived:'已归档', restore:'恢复', noArchived:'暂无归档记录', del:'删除',
    schedule:'自动检查', from:'从', to:'到', every:'每隔', minutes:'分钟',
    scheduleHint:'小组件启动时也会检查一次。自动检查只在有变化时才会弹出台词框。',
    gmail:'Gmail', gmailAddr:'Gmail 地址', appPw:'应用专用密码',
    pwHint:'Google 账号 → 安全性 → 两步验证 → 应用专用密码。保存在 macOS 钥匙串。',
    pwSaved:'✓ 已保存密码。', pwKeep:'留空表示不修改', scanDays:'扫描最近多少天的邮件',
    tracking:'查询', browser:'读取 parcelsapp 用的浏览器',
    browserHint:'如果查询被拦截或拿不到数据，换一个浏览器试试。Firefox / WebKit / Chromium 第一次使用时会自动下载。',
    headless:'后台运行浏览器（不显示窗口）',
    period:'每根K线', colors:'K线颜色', colorsAuto:'跟随语言', greenUp:'绿涨红跌', redUp:'红涨绿跌',
    sysHint:'CPU、内存和网络每秒采样一次，保留一小时。',
    csIntro:'描述一个角色（也可以选一张它的图片），图像 AI 会画出它的各种动作，小组件再把它们做成会动的皮肤。',
    csName:'名字', csDesc:'角色长什么样？', csDescPh:'例如：穿快递员制服、戴小帽子的橘猫娘',
    csRef:'参考图（可选）', csPick:'选择…', csRefNo:'这个服务商不支持参考图，只会用文字描述。',
    csProvider:'图像 AI', csKeySaved:'✓ 密钥已保存在 macOS 钥匙串，留空表示不修改。', csGetKey:'获取密钥 ↗',
    csAdvanced:'高级：模型 / 接口地址', csModel:'模型（留空用默认）', csEndpoint:'接口地址（留空用默认）',
    csGenerate:'生成', csCost:'大约 10 次图像请求，需要几分钟，期间可以关掉这个窗口。费用由服务商收取。',
    csStep:(s,t,l)=>`第 ${s}/${t} 步：${l}`, csDone:'完成！新皮肤已经换上了。', csPartial:r=>`完成了，但这些动作没生成成功：${r}`,
    csErr:e=>`失败：${e}`, csCancelled:'已取消', csBusy:'已经在生成皮肤了。', csNoKey:'请填写 API 密钥。',
    csNoDesc:'请描述角色或选择一张图片。',
    csLabels:{base:'画角色', assemble:'拼合动作表', done:'完成',
      idle:'站立', walk_right:'走路', wave:'挥手', jump:'跳跃', sleep:'睡觉', cheer:'欢呼', think:'思考', shy:'害羞', look_right:'张望'},
  },
};

/* ---------------- helpers shared by both pages ---------------- */
let lang = 'en';
const T = () => I18N[lang] || I18N.en;
const api = () => window.pywebview.api;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const browserName = k => T().browsers[k] || k;
const trackUrl = n => 'https://parcelsapp.com/en/tracking/' + encodeURIComponent(n);
const pick = a => Array.isArray(a) ? a[Math.floor(Math.random() * a.length)] : a;
const shortNum = n => n && n.length > 12 ? '…' + n.slice(-8) : (n || '');
const hhmm = ts => new Date(ts * 1000).toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US', {hour:'2-digit', minute:'2-digit', hour12:false});
function ago(ts){
  const m = Math.round((Date.now()/1000 - ts)/60), L = T();
  if(m < 1) return L.justNow; if(m < 60) return L.minAgo(m);
  const h = Math.round(m/60); return h < 24 ? L.hrAgo(h) : L.dayAgo(Math.round(h/24));
}
function errText(code){
  if(!code) return '';
  const E = T().err, [k, ...rest] = String(code).split(':'), arg = rest.join(':');
  if(k === 'blocked' || k === 'no_data') return E[k];
  if(k === 'browser_missing') return E.browser_missing(browserName(arg));
  if(k === 'failed') return E.failed(arg);
  return code;
}
function applyStaticText(){
  document.documentElement.lang = lang === 'zh' ? 'zh' : 'en';
  document.querySelectorAll('[data-t]').forEach(el => {
    const v = el.dataset.t.split('.').reduce((o, k) => o && o[k], T());
    if(typeof v === 'string') el.textContent = v;
  });
}
