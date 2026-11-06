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
      parcels:{startup:'📦 Parcel check', manual:'📦 Parcel check', scheduled:'📦 Parcel update', wake:'📦 Parcel update', retry:'📦 Parcel update', install:'📦 Parcels'},
      skin:{make:'🎨 New skin'},
      usb:{startup:'🔌 USB devices', manual:'🔌 USB devices', printer:'🖨 Printer'},
    },
    p:{
      mailOff:'📭 Gmail isn\'t connected, so I only check numbers you add.',
      mailReading:(n,t)=> t ? `📬 Reading Gmail… ${n}/${t}` : '📬 Opening Gmail',
      soFar:k=>`${k} found`,
      mailNone:t=> t ? `📬 Read ${t} shipping email${t>1?'s':''}, no tracking numbers.` : '📬 No shipping emails lately.',
      mailDone:(t,k,nw)=>`📬 Read ${t} email${t>1?'s':''}: ${k} number${k>1?'s':''}` + (nw ? `, <b>${nw} new</b>` : ', nothing new'),
      mailErr:e=>`📭 Couldn't read Gmail: ${e}`,
      mailNoNet:'📡 No internet connection, so I couldn\'t reach Gmail.',
      mailAuth:'🔑 Gmail didn\'t accept the app password.',
      retryLater:'I\'ll try again later.', retry:'⟳ Try again',
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
    u:{title:'🔌 USB', scanning:'🔌 Looking at what\'s plugged in…', online:n=>`🔌 ${n} device${n==1?'':'s'} · checking drivers online…`,
      found:(n,a,t)=>`🔌 ${n} USB device${n==1?'':'s'}: ${a} Apple driver${a==1?'':'s'}` + (t ? `, <b>${t} other${t==1?'':'s'}</b>` : ''),
      none:'🔌 Nothing plugged in over USB.',
      macosOk:v=>`✅ Apple's drivers are current (macOS ${v}).`,
      macosUpd:(v,u)=>`⬆️ macOS ${u} is out (you have ${v}): Apple's USB drivers update with it.`,
      newer:n=>`⬆️ Maybe newer online: ${n}`, offline:e=>`Couldn't check online: ${e}`,
      showAll:'Show devices', checkAgain:'⟳ Check again', checking:'Checking…', checked:t=>`Checked ${t}`,
      hidden:n=>`+ ${n} hub${n==1?'':'s'}`,
      kinds:{hub:'Hub', printer:'Printer', storage:'Storage', network:'Network', input:'Keyboard / mouse', audio:'Audio',
        video:'Video', camera:'Camera / scanner', wireless:'Wireless', billboard:'USB-C adapter', vendor:'Device', other:'Device'},
      noDriver:'no driver of its own', cups:'printed to by macOS (CUPS)',
      b:{apple_ok:'✓ macOS', apple_update:u=>`⬆ macOS ${u}`, apple_unknown:'macOS', ok:'✓ current', maybe_newer:v=>`⬆ v${v} online?`, unknown:'? see links'},
      tip:{apple_ok:'Comes with macOS, which is up to date', apple_update:'Comes with macOS: updates with the macOS update',
        apple_unknown:'Comes with macOS', ok:'No newer version found online',
        maybe_newer:'A newer version number shows up online - check the links', unknown:'No version found online - check the links'},
      pr:{configured:n=>`🖨 ${n} is in your printer list.`,
        airprint:n=>`🖨 ${n} isn't set up yet. It does AirPrint, so it needs no driver.`,
        local:n=>`🖨 ${n} isn't set up yet. Its driver is already on this Mac.`,
        found:(n,t,d,s)=>`🖨 ${n} needs <b>${t}</b> (${d}, ${s}).`,
        downloading:(t,p,s)=>`⬇️ Downloading ${t}: ${p}% of ${s}`,
        downloaded:t=>`✅ ${t} is in Downloads › Printer Drivers. Open it to install, then add the printer.`,
        none:n=>`🖨 I couldn't find a driver for ${n} by myself. These might help:`,
        error:e=>`⚠️ Driver download failed: ${e}`},
      add:'Add printer', air:'Set up with AirPrint', airMore:'Printers', dl:'Download', cancel:'Stop', install:'Install…', retry:'Try again', folder:'Show folder'},
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
    title:'Settings', tabs:{general:'General', parcels:'📦 Parcels', sysmon:'📊 System', usb:'🔌 USB', printers:'🖨 Printers', skin:'🎨 Custom skin', log:'📝 Log'},
    lg:{all:'All', checks:'Checks', errors:'Errors', auto:'Live', refresh:'Refresh', copy:'Copy', copied:'Copied',
        reveal:'Show in Finder', clear:'Clear', clearConfirm:'Clear the log?', empty:'Nothing logged yet.',
        lines:n => n + ' lines', asleep:'Computer asleep: checks paused', busy:'Checking now…',
        next:t => 'Next check ' + t, retry:(t, n) => 'No network: retry ' + n + '/3 at ' + t, none:'No check scheduled'},
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
    usbAuto:'Download printer drivers by myself', usbAutoHint:'When a USB printer that isn\'t set up needs a driver, I download it from Apple into this folder. Installing is up to you.',
    usbHubs:'Show hubs and adapters', usbFolder:'Driver folder', usbDevices:'Devices',
    ap:{intro:'AirPrint printers need no driver: macOS asks the printer what it can do (two-sided, color, paper trays). One click sets a printer up that way. The same printer is often in the list more than once; I keep the best entry and can remove the others.',
      list:'Printers', refresh:'⟳ Refresh', looking:'Looking…', find:'Look nearby (Bonjour)', addr:'Add by address',
      addrPh:'IP address or host name, e.g. 10.0.0.12', addrGo:'Set up with AirPrint', addrHint:'For printers on the network that don\'t show up nearby (offices often block that).',
      setup:'Set up with AirPrint', setupDef:'and make it the default', tidy:n=>`Remove ${n} duplicate${n==1?'':'s'}`, def:'Make default', test:'Print test page',
      addWin:'Open Add Printer…', none:'No printers yet.',
      via:{usb:'USB', network:'Network', bonjour:'Nearby', other:'Other'}, notConnected:'not plugged in',
      st:{ready:'✓ AirPrint', other:'other driver', offline:'not answering', none:'not set up'},
      isDefault:'default', airprint:'AirPrint', offlineQ:'offline', server:'Print server with its own sign-in: left as it is.',
      hintOther:'Uses a generic driver. AirPrint usually gives more options (two-sided, color, trays).',
      hintNone:'Not in the printer list yet.', hintNoUsb:'Plug it in to set it up.',
      tidyAsk:(n,keep,list)=>`Remove ${n} duplicate entr${n==1?'y':'ies'} of this printer from the printer list?\n\n${list}\n\n"${keep}" stays.`,
      job:{working:'Working…', done:q=>`✓ Done: "${q}"`, already:q=>`✓ Already set up with AirPrint: "${q}"`,
        manual:'The macOS Add Printer window is open: pick the printer and choose "AirPrint" under "Use".',
        error:e=>`⚠️ ${e}`, test:'✓ Test page sent'},
      err:{'no-airprint':'This printer doesn\'t do AirPrint.', cancelled:'Cancelled.', 'not-connected':'Plug the printer in first.',
        'bad address':'That doesn\'t look like an address.', 'no answer':'The printer didn\'t answer.'}},
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
      parcels:{startup:'📦 快递检查', manual:'📦 快递检查', scheduled:'📦 快递有新动态', wake:'📦 快递有新动态', retry:'📦 快递有新动态', install:'📦 快递'},
      skin:{make:'🎨 新皮肤'},
      usb:{startup:'🔌 USB 设备', manual:'🔌 USB 设备', printer:'🖨 打印机'},
    },
    p:{
      mailOff:'📭 还没连接 Gmail，所以只查你手动添加的单号。',
      mailReading:(n,t)=> t ? `📬 正在读 Gmail… ${n}/${t}` : '📬 正在打开 Gmail',
      soFar:k=>`已找到 ${k} 个`,
      mailNone:t=> t ? `📬 读了 ${t} 封物流邮件，里面没有单号` : '📬 最近没有物流邮件',
      mailDone:(t,k,nw)=>`📬 读了 ${t} 封邮件：${k} 个单号` + (nw ? `，<b>${nw} 个是新的</b>` : '，没有新的'),
      mailErr:e=>`📭 读取 Gmail 失败：${e}`,
      mailNoNet:'📡 没有网络，连不上 Gmail。',
      mailAuth:'🔑 Gmail 不接受这个应用专用密码。',
      retryLater:'我等会儿再试。', retry:'⟳ 再试一次',
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
    u:{title:'🔌 USB', scanning:'🔌 正在看插了什么…', online:n=>`🔌 ${n} 个设备 · 正在上网查驱动…`,
      found:(n,a,t)=>`🔌 ${n} 个 USB 设备：${a} 个苹果驱动` + (t ? `，<b>${t} 个第三方驱动</b>` : ''),
      none:'🔌 没有插 USB 设备。',
      macosOk:v=>`✅ 苹果自带的驱动是最新的（macOS ${v}）。`,
      macosUpd:(v,u)=>`⬆️ macOS ${u} 出了（你现在是 ${v}）：苹果的 USB 驱动跟着系统一起更新。`,
      newer:n=>`⬆️ 网上可能有新版：${n}`, offline:e=>`没法上网查：${e}`,
      showAll:'查看设备', checkAgain:'⟳ 重新检查', checking:'检查中…', checked:t=>`${t} 检查过`,
      hidden:n=>`+ ${n} 个集线器`,
      kinds:{hub:'集线器', printer:'打印机', storage:'存储', network:'网络', input:'键盘 / 鼠标', audio:'音频',
        video:'视频', camera:'相机 / 扫描仪', wireless:'无线', billboard:'USB-C 转接', vendor:'设备', other:'设备'},
      noDriver:'没有专门的驱动', cups:'由 macOS 打印系统（CUPS）负责',
      b:{apple_ok:'✓ 系统自带', apple_update:u=>`⬆ macOS ${u}`, apple_unknown:'系统自带', ok:'✓ 最新', maybe_newer:v=>`⬆ 网上有 v${v}？`, unknown:'? 看链接'},
      tip:{apple_ok:'macOS 自带，系统已是最新', apple_update:'macOS 自带：随系统更新一起更新',
        apple_unknown:'macOS 自带', ok:'网上没找到更新的版本',
        maybe_newer:'网上出现了更高的版本号，看看链接确认一下', unknown:'网上没找到版本号，看看链接'},
      pr:{configured:n=>`🖨 ${n} 已经在打印机列表里了。`,
        airprint:n=>`🖨 ${n} 还没添加。它支持 AirPrint，不需要驱动。`,
        local:n=>`🖨 ${n} 还没添加。它的驱动这台 Mac 上已经有了。`,
        found:(n,t,d,s)=>`🖨 ${n} 需要 <b>${t}</b>（${d}，${s}）。`,
        downloading:(t,p,s)=>`⬇️ 正在下载 ${t}：${p}%，共 ${s}`,
        downloaded:t=>`✅ ${t} 已下载到 下载 › Printer Drivers。打开安装，然后添加打印机。`,
        none:n=>`🖨 我没能自己找到 ${n} 的驱动，这些可能有用：`,
        error:e=>`⚠️ 驱动下载失败：${e}`},
      add:'添加打印机', air:'用 AirPrint 设置', airMore:'打印机', dl:'下载', cancel:'停止', install:'安装…', retry:'再试一次', folder:'打开文件夹'},
    sys:{title:'📊 系统状态', cpu:'CPU', ram:'内存', down:'下载', up:'上传', per:s=>`每根 ${s<60?s+' 秒':(s/60)+' 分钟'}`,
      noPsutil:'读不到系统状态（缺少 psutil）。', warming:'正在收集数据…'},
    pet:{
      hello:['你好呀！我先帮你看看～','欢迎回来！'],
      poke:['嘿嘿，好痒～','有什么吩咐？','我一直在看着呢！','♪～','嗯？','戳回去！'],
      allDone:['都好啦！我在旁边守着～','搞定！有事叫我～'],
      delivered:c=>`你的 ${c} 快递送到啦！🎉`, newPkg:n=>`发现 ${n} 个新快递！`,
      sleep:'zzz…', wake:'诶！我、我没睡着！',
    },
    title:'设置', tabs:{general:'通用', parcels:'📦 快递', sysmon:'📊 系统状态', usb:'🔌 USB', printers:'🖨 打印机', skin:'🎨 自定义皮肤', log:'📝 日志'},
    lg:{all:'全部', checks:'检查', errors:'错误', auto:'实时', refresh:'刷新', copy:'复制', copied:'已复制',
        reveal:'在访达中显示', clear:'清空', clearConfirm:'清空日志？', empty:'还没有日志。',
        lines:n => n + ' 行', asleep:'电脑待机中：已暂停检查', busy:'正在检查…',
        next:t => '下次检查 ' + t, retry:(t, n) => '没有网络：' + t + ' 第 ' + n + '/3 次重试', none:'没有安排检查'},
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
    usbAuto:'自动下载打印机驱动', usbAutoHint:'插上还没设置的 USB 打印机、又需要驱动时，我从苹果下载到这个文件夹。安装由你来。',
    usbHubs:'显示集线器和转接器', usbFolder:'驱动文件夹', usbDevices:'设备',
    ap:{intro:'AirPrint 打印机不需要驱动：macOS 直接问打印机会什么（双面、彩色、纸盒）。一键就能按这种方式设置好。同一台打印机常常在列表里出现好几次，我会保留最好的那个，其余的可以一键删掉。',
      list:'打印机', refresh:'⟳ 刷新', looking:'正在找…', find:'搜索附近 (Bonjour)', addr:'按地址添加',
      addrPh:'IP 地址或主机名，例如 10.0.0.12', addrGo:'用 AirPrint 设置', addrHint:'用于附近搜不到的网络打印机（公司网络经常屏蔽搜索）。',
      setup:'用 AirPrint 设置', setupDef:'并设为默认', tidy:n=>`删掉 ${n} 个重复项`, def:'设为默认', test:'打印测试页',
      addWin:'打开“添加打印机”…', none:'还没有打印机。',
      via:{usb:'USB', network:'网络', bonjour:'附近', other:'其他'}, notConnected:'未插入',
      st:{ready:'✓ AirPrint', other:'其他驱动', offline:'没有响应', none:'未设置'},
      isDefault:'默认', airprint:'AirPrint', offlineQ:'离线', server:'带登录的打印服务器，保持原样。',
      hintOther:'用的是通用驱动。换成 AirPrint 通常功能更全（双面、彩色、纸盒）。',
      hintNone:'还不在打印机列表里。', hintNoUsb:'插上后才能设置。',
      tidyAsk:(n,keep,list)=>`从打印机列表里删掉这台打印机的 ${n} 个重复项？\n\n${list}\n\n保留“${keep}”。`,
      job:{working:'正在处理…', done:q=>`✓ 完成：“${q}”`, already:q=>`✓ 已经用 AirPrint 设置好了：“${q}”`,
        manual:'已打开 macOS 的“添加打印机”窗口：选中打印机，在“使用”里选“AirPrint”。',
        error:e=>`⚠️ ${e}`, test:'✓ 测试页已发送'},
      err:{'no-airprint':'这台打印机不支持 AirPrint。', cancelled:'已取消。', 'not-connected':'请先插上打印机。',
        'bad address':'这看起来不是一个地址。', 'no answer':'打印机没有响应。'}},
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
// what kind of Gmail error: 'net' (no connection / DNS / timeout), 'auth' (password), or ''
function mailErrKind(e){
  e = String(e || '').toLowerCase();
  if(/errno 8|nodename|name or service|network is unreachable|timed out|timeout|connection (reset|refused|aborted)|no route|offline/.test(e)) return 'net';
  if(/authenticat|invalid credentials|login|password/.test(e)) return 'auth';
  return '';
}
function applyStaticText(){
  document.documentElement.lang = lang === 'zh' ? 'zh' : 'en';
  document.querySelectorAll('[data-t]').forEach(el => {
    const v = el.dataset.t.split('.').reduce((o, k) => o && o[k], T());
    if(typeof v === 'string') el.textContent = v;
  });
  document.querySelectorAll('[data-tp]').forEach(el => {
    const v = el.dataset.tp.split('.').reduce((o, k) => o && o[k], T());
    if(typeof v === 'string') el.placeholder = v;
  });
}
