"""A local QR window; the account owner scans and confirms in the NetEase app."""
import argparse
import json
import os
import pathlib
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from netease_session import Login, login_status, session_path


def web_command(root):
    code = pathlib.Path(__file__).resolve().parent
    scripts = [code.parent / 'scripts' / 'netease-web-login.cjs', code / 'netease-web-login.cjs']
    script = next((p for p in scripts if p.is_file()), None)
    home = pathlib.Path(os.environ.get('DSH_HOME', str(pathlib.Path.home() / '.dsh')))
    candidates = [os.environ.get('DSH_SINGING_ELECTRON', ''),
                  str(home / 'electron' / ('electron.exe' if os.name == 'nt' else 'electron')),
                  shutil.which('electron') or '']
    electron = next((pathlib.Path(p).resolve() for p in candidates if p and pathlib.Path(p).is_file()), None)
    if not script or not electron:
        raise ValueError('未找到 DSH 的 Electron 运行时；可设置 DSH_SINGING_ELECTRON 为已有 Electron 的绝对路径')
    python = pathlib.Path(sys.executable)
    console = python.with_name('python.exe') if os.name == 'nt' else python
    if console.is_file():
        python = console
    return [str(electron), str(script), '--data-dir', str(root), '--python', str(python),
            '--importer', str(code / 'netease_login.py')]


def open_web(root):
    return subprocess.Popen(web_command(root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def wait_login(login, root, cancel, emit, timeout=175):
    data = login.generate()
    emit('qr', data['url'])
    deadline = time.monotonic() + timeout
    while not cancel.wait(3):
        if time.monotonic() >= deadline:
            emit('done', '二维码已过期，请重新点击扫码登录')
            return
        code = login.poll(data['key'])
        if cancel.is_set():
            return
        if code == 803:
            login.save(root)
            emit('done', '登录成功，已安全保存在本机。可以关闭窗口。')
            return
        if code == 802:
            emit('status', '扫码成功，请在网易云音乐 App 上确认登录')
        elif code == 800:
            emit('done', '二维码已失效，请重新点击扫码登录')
            return


def main():
    parser = argparse.ArgumentParser()
    default = pathlib.Path(os.environ.get('DSH_HOME', str(pathlib.Path.home() / '.dsh'))) / 'singing'
    parser.add_argument('--data-dir', default=str(default))
    parser.add_argument('--scan', action='store_true', help='Open a fresh QR code on launch')
    parser.add_argument('--status', action='store_true', help='Print only whether the saved login is valid')
    parser.add_argument('--web', action='store_true', help='Open an isolated official web sign-in window')
    parser.add_argument('--import-session', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = pathlib.Path(args.data_dir).expanduser().resolve()
    if args.import_session:
        from netease_session import save_session
        try:
            payload = sys.stdin.buffer.read(65537)
            if len(payload) > 65536:
                raise ValueError()
            save_session(root, json.loads(payload))
        except Exception:
            raise SystemExit(1)
        return
    if args.web:
        open_web(root)
        return
    if args.status:
        try:
            print(json.dumps({'ok': True, 'saved': session_path(root).exists(), 'loggedIn': login_status(root)}))
        except Exception:
            print(json.dumps({'ok': False, 'error': 'login_check_failed'}))
            raise SystemExit(1)
        return

    import tkinter as tk
    from tkinter import messagebox
    try:
        import qrcode
    except ImportError:
        messagebox.showerror('缺少登录组件', '请安装 requirements.txt 中的 qrcode 组件')
        return
    window = tk.Tk()
    window.title('唱歌插件 · 网易云登录')
    window.geometry('510x610')
    window.resizable(False, False)
    saved = session_path(root).exists()
    status = tk.StringVar(value='已保存本机登录状态，可检查或重新扫码' if saved else '请用自己的网易云音乐 App 扫码，再在手机确认')
    tk.Label(window, textvariable=status, wraplength=470).pack(pady=14)
    canvas = tk.Canvas(window, width=330, height=330, bg='white', highlightthickness=0)
    canvas.pack()
    tk.Label(window, text='登录后，网易云查歌和取音源会使用此账号。\n可用歌曲以账号正常播放权限为准。\n登录状态仅保存在本机，不发给 QQ 或模型。', wraplength=470).pack(pady=12)
    events = queue.Queue()
    cancel = threading.Event()
    busy = False
    buttons = tk.Frame(window)
    buttons.pack(pady=6)

    def worker(scan):
        try:
            if scan:
                wait_login(Login(), root, cancel, lambda kind, text: events.put((kind, text)))
            else:
                text = '登录状态有效，网易云音源已使用此账号' if login_status(root) else '当前未登录或登录已失效，请重新扫码'
                events.put(('done', text))
        except Exception as error:
            text = str(error) if isinstance(error, ValueError) else '登录操作未完成，请稍后重试'
            events.put(('done', text))

    def start(scan=True):
        nonlocal busy
        if busy:
            return
        busy = True
        cancel.clear()
        canvas.delete('all')
        status.set('正在申请网易云登录二维码…' if scan else '正在检查登录状态…')
        for button in controls:
            button.config(state='disabled')
        threading.Thread(target=worker, args=(scan,), daemon=True).start()

    def logout():
        try:
            session_path(root).unlink(missing_ok=True)
            status.set('已退出插件登录；不影响浏览器和手机上的账号')
            canvas.delete('all')
        except OSError:
            status.set('本机登录文件删除失败，请关闭正在使用它的程序再试')

    controls = [tk.Button(buttons, text='扫码登录', command=start),
                tk.Button(buttons, text='检查登录状态', command=lambda: start(False)),
                tk.Button(buttons, text='退出插件登录', command=logout)]
    for button in controls:
        button.pack(side='left', padx=5)
    def official_login():
        try:
            open_web(root)
            status.set('已打开独立的网易云官网窗口，请自行登录；完成后点击检查登录状态')
        except (OSError, ValueError) as error:
            status.set(str(error) if isinstance(error, ValueError) else '官方登录窗口未能启动')
    tk.Button(window, text='官方网页登录（扫码受限时使用）', command=official_login).pack(pady=6)
    tk.Button(window, text='打开网易云官网', command=lambda: webbrowser.open('https://music.163.com/')).pack(pady=6)

    def drain():
        nonlocal busy
        try:
            while True:
                kind, text = events.get_nowait()
                if kind == 'qr':
                    qr = qrcode.QRCode(border=4)
                    qr.add_data(text)
                    qr.make(fit=True)
                    matrix = qr.get_matrix()
                    scale = 330 / len(matrix)
                    canvas.delete('all')
                    for y, row in enumerate(matrix):
                        for x, on in enumerate(row):
                            if on:
                                canvas.create_rectangle(x * scale, y * scale, (x + 1) * scale, (y + 1) * scale, fill='black', outline='black')
                    status.set('用网易云音乐 App 扫码，然后在手机确认')
                else:
                    status.set(text)
                if kind == 'done':
                    busy = False
                    for button in controls:
                        button.config(state='normal')
                    canvas.delete('all')
        except queue.Empty:
            pass
        window.after(150, drain)

    def close():
        cancel.set()
        window.destroy()

    window.protocol('WM_DELETE_WINDOW', close)
    drain()
    if args.scan:
        window.after(250, start)
    window.mainloop()


if __name__ == '__main__':
    main()
