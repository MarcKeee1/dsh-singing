// Isolated, user-operated official web sign-in. No access to other browser profiles.
const {app, BrowserWindow, session, dialog} = require('electron');
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const args = process.argv.slice(2);
const option = name => {const i = args.indexOf(name); return i < 0 ? '' : args[i + 1] || '';};
const dataDir = option('--data-dir'), python = option('--python'), importer = option('--importer');
if (![dataDir, python, importer].every(value => value && path.isAbsolute(value))) app.exit(2);
app.disableHardwareAcceleration();
const browserData = path.join(dataDir, '.auth', 'netease-web-runtime');
fs.mkdirSync(browserData, {recursive:true, mode:0o700});
app.setPath('userData', browserData);
app.setName('DSH Singing NetEase Login');
const names = new Set(['MUSIC_U', '__csrf', 'NMTID']);
let window, checking = false, finished = false, closing = false, timer;

function save(rows) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [importer, '--data-dir', dataDir, '--import-session'],
      {stdio:['pipe','ignore','ignore'], shell:false, windowsHide:true});
    const timeout = setTimeout(() => {child.kill(); reject(Error('save_timeout'));}, 15000);
    child.on('error', () => {clearTimeout(timeout); reject(Error('save_failed'));});
    child.on('exit', code => {clearTimeout(timeout); code === 0 ? resolve() : reject(Error('save_failed'));});
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(rows));
  });
}

async function checkCookies(browserSession) {
  if (checking || finished || closing) return;
  checking = true;
  try {
    const cookies = await browserSession.cookies.get({url:'https://music.163.com/'});
    const rows = cookies.filter(c => names.has(c.name) && ['music.163.com','163.com'].includes(c.domain.replace(/^\./,'')))
      .map(c => ({name:c.name, value:c.value, expires:c.session ? null : c.expirationDate}));
    if (!rows.some(c => c.name === 'MUSIC_U' && c.value)) return;
    await save(rows);
    finished = true;
    clearInterval(timer);
    await dialog.showMessageBox(window, {type:'info', title:'网易云登录已保存',
      message:'网易云登录成功，唱歌插件已保存本机登录状态。',
      detail:'之后查找网易云音源会使用此账号，可以关闭登录窗口。', buttons:['完成']});
    window.close();
  } catch {
    if (!closing) window.setTitle('网易云音乐 · 登录保存未完成，请重试或关闭后重新打开');
  } finally {checking = false;}
}

app.whenReady().then(async () => {
  // No persist: prefix: login cookies exist only in memory until copied to DPAPI.
  const browserSession = session.fromPartition('netease-user-login');
  browserSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  browserSession.setPermissionCheckHandler(() => false);
  window = new BrowserWindow({width:1100,height:800,title:'唱歌插件 · 网易云官网登录',autoHideMenuBar:true,
    webPreferences:{session:browserSession,nodeIntegration:false,contextIsolation:true,sandbox:true}});
  window.removeMenu();
  window.webContents.on('page-title-updated', event => {event.preventDefault();window.setTitle('唱歌插件 · 网易云官网登录');});
  window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
  window.webContents.on('will-navigate', (event, target) => {
    try {const u = new URL(target); if (u.protocol !== 'https:' || u.hostname !== 'music.163.com') event.preventDefault();}
    catch {event.preventDefault();}
  });
  browserSession.cookies.on('changed', () => checkCookies(browserSession));
  window.on('closed', () => {closing=true;clearInterval(timer);window=null;app.quit();});
  timer = setInterval(() => checkCookies(browserSession), 1500);
  try {await window.loadURL('https://music.163.com/');}
  catch {await dialog.showMessageBox(window,{type:'error',message:'网易云官网未能打开，请检查网络后重新打开此入口。'});}
});
app.on('window-all-closed', () => app.quit());
