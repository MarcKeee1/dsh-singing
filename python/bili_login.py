"""Local, user-operated QR login. The QR and credentials never enter a QQ chat."""
import argparse,http.cookiejar,json,pathlib,queue,re,threading,time,urllib.request,urllib.parse,webbrowser
from bili_session import save_session,session_path,SameHostRedirect,COOKIE_NAMES

def validate_qr(data):
    parsed=urllib.parse.urlparse(data.get('url',''));key=data.get('qrcode_key','')
    allowed={('passport.bilibili.com','/h5-app/passport/login/scan'),('account.bilibili.com','/h5/account-h5/auth/scan-web')}
    if (parsed.scheme!='https' or (parsed.hostname,parsed.path) not in allowed or parsed.username or parsed.password or parsed.port not in (None,443)
        or not re.fullmatch('[0-9a-fA-F]{32}',key) or urllib.parse.parse_qs(parsed.query).get('qrcode_key')!=[key]):raise ValueError('二维码地址校验失败')
    return data

class Login:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(SameHostRedirect(),urllib.request.HTTPCookieProcessor(self.jar))
    def api(self,path):
        request=urllib.request.Request('https://passport.bilibili.com/x/passport-login/web/qrcode/'+path,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.bilibili.com/'})
        try:
            with self.opener.open(request,timeout=15) as response:data=json.load(response)
        except Exception:raise ValueError('B站登录暂不可用或需要验证。已停止；请在官方网页登录，不会自动重试。') from None
        if data.get('code')!=0:raise ValueError('B站没有接受这次登录请求。已停止；请在官方网页完成验证。')
        return data['data']
    def generate(self):
        return validate_qr(self.api('generate'))
    def poll(self,key,root):
        data=self.api('poll?'+urllib.parse.urlencode({'qrcode_key':key}));code=data['code']
        if code==0:
            save_session(root,[{'name':c.name,'value':c.value,'expires':c.expires} for c in self.jar if c.name in COOKIE_NAMES and c.domain.lstrip('.')=='bilibili.com'])
        return code

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',required=True);args=parser.parse_args()
    import tkinter as tk
    from tkinter import messagebox
    try:import qrcode
    except ImportError:messagebox.showerror('缺少登录组件','请先安装 requirements.txt 中的 qrcode 组件');return
    root=pathlib.Path(args.data_dir).resolve();window=tk.Tk();window.title('唱歌插件 · B站登录');window.geometry('480x550');window.resizable(False,False)
    status=tk.StringVar(value='已保存本机登录状态；失效后可重新扫码' if session_path(root).exists() else '可选登录：请用自己的 B站 App 扫码确认')
    tk.Label(window,textvariable=status,wraplength=440).pack(pady=12)
    canvas=tk.Canvas(window,width=330,height=330,bg='white');canvas.pack()
    tk.Label(window,text='只用于正常读取音源；登录不保证解除风控。\n验证码请在官方页面完成。拒绝后不自动重试。\n退出仅删除此插件的本机登录状态。',wraplength=440).pack(pady=8)
    events=queue.Queue();cancel=threading.Event();busy=False
    def worker():
        login=Login()
        try:
            data=login.generate();events.put(('qr',data['url']));deadline=time.monotonic()+175
            while not cancel.wait(3):
                if time.monotonic()>deadline:events.put(('done','二维码已过期；需要时重新点击扫码登录'));return
                code=login.poll(data['qrcode_key'],root)
                if code==0:events.put(('done','登录成功，已安全保存在本机。可关闭此窗口。'));return
                if code==86090:events.put(('status','扫码成功，请在手机上确认登录'))
                elif code==86038:events.put(('done','二维码已失效；需要时重新点击扫码登录'));return
                elif code!=86101:raise ValueError('登录需要额外验证。已停止，请打开官方登录页。')
        except Exception as error:events.put(('done',str(error) if isinstance(error,ValueError) else '本机保存失败，请重试登录'))
    def start():
        nonlocal busy
        if busy:return
        busy=True;cancel.clear();status.set('正在申请登录二维码…');login_button.config(state='disabled');logout_button.config(state='disabled')
        threading.Thread(target=worker,daemon=True).start()
    def logout():
        session_path(root).unlink(missing_ok=True);status.set('已退出插件登录；不影响你的浏览器账号');canvas.delete('all')
    buttons=tk.Frame(window);buttons.pack(pady=8)
    login_button=tk.Button(buttons,text='扫码登录',command=start);login_button.pack(side='left',padx=6)
    logout_button=tk.Button(buttons,text='退出插件登录',command=logout);logout_button.pack(side='left',padx=6)
    tk.Button(buttons,text='官方登录页',command=lambda:webbrowser.open('https://account.bilibili.com/login')).pack(side='left',padx=6)
    def drain():
        nonlocal busy
        try:
            while True:
                kind,text=events.get_nowait()
                if kind=='qr':
                    qr=qrcode.QRCode(border=4);qr.add_data(text);qr.make(fit=True);matrix=qr.get_matrix();scale=330/len(matrix);canvas.delete('all')
                    for y,row in enumerate(matrix):
                        for x,on in enumerate(row):
                            if on:canvas.create_rectangle(x*scale,y*scale,(x+1)*scale,(y+1)*scale,fill='black',outline='black')
                    status.set('用 B站 App 扫码，然后在手机上确认')
                else:status.set(text)
                if kind=='done':busy=False;login_button.config(state='normal');logout_button.config(state='normal');canvas.delete('all')
        except queue.Empty:pass
        window.after(150,drain)
    def close():cancel.set();window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);drain();window.mainloop()

if __name__=='__main__':main()
