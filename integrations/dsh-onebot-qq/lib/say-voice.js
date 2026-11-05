import { spawn } from 'node:child_process';
import { win32 } from 'node:path';
import { homedir } from 'node:os';

const ROOT = process.env.DSH_TTS_ROOT || win32.join(homedir(), '.dsh', 'voice-local');
const PYTHON = process.env.DSH_TTS_PYTHON || win32.join(ROOT, '.venv-cosy', 'Scripts', 'python.exe');
const SCRIPT = process.env.DSH_TTS_SCRIPT || win32.join(ROOT, 'tts.py');

export function voiceTarget(agent, bridge) {
    const session = agent?.session;
    const id = String(session?.id ?? '');
    const cwd = session?.header?.cwd;
    const inWorkspace = typeof cwd === 'string'
        && win32.isAbsolute(cwd)
        && win32.normalize(cwd).replace(/[\\/]+$/, '').toLowerCase() === win32.normalize(process.env.DSH_QQ_WORKSPACE || bridge.deps.policy.workspacePath || win32.join(homedir(), '.dsh', 'workspaces', 'qq')).replace(/[\\/]+$/, '').toLowerCase();
    if (!inWorkspace) return null;
    const priv = /^onebot-private-(\d+)(?:-|$)/.exec(id);
    if (priv) {
        if (!bridge.deps.policy.adminUsers.map(String).includes(priv[1])) return null;
        return { chat: 'private:' + priv[1] };
    }
    const grp = /^onebot-group-(\d+)(?:-|$)/.exec(id);
    if (grp) return { chat: 'group:' + grp[1] };
    return null;
}

export function voiceScope(agent, bridge) {
    return voiceTarget(agent, bridge) !== null;
}

export const SYNTHESIS_TIMEOUT_MS = 20_000;
export function synthesizeVoice(text, signal, spawnProcess = spawn, timeoutMs = SYNTHESIS_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
        signal?.throwIfAborted();
        const child = spawnProcess(PYTHON, [SCRIPT, '--json', '--', text], {
            cwd: ROOT, windowsHide: true, shell: false,
            stdio: ['ignore', 'pipe', 'pipe'],
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        });
        let stdout = '', stderr = '', settled = false, stopError;
        const finish = (error, value) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            signal?.removeEventListener('abort', abort);
            error ? reject(error) : resolve(value);
        };
        const stop = error => {
            if (settled || stopError) return;
            stopError = error;
            // The Windows venv executable has a runtime child. Kill the owned
            // tree so a timed-out request cannot keep running in the background.
            if (process.platform === 'win32' && child.pid && child.exitCode === null) {
                const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore', shell: false });
                killer.once('error', () => child.kill());
            } else child.kill();
            finish(error);
        };
        const abort = () => stop(new Error('say_voice 已取消，未发送'));
        const timer = setTimeout(() => stop(new Error(`语音生成超过 ${timeoutMs / 1000} 秒，已停止生成`)), timeoutMs);
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) abort();
        child.stdout.setEncoding('utf8');
        child.stderr.setEncoding('utf8');
        child.stdout.on('data', chunk => { stdout = (stdout + chunk).slice(-32768); });
        child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-8192); });
        child.once('error', error => finish(error));
        child.once('close', code => {
            if (code !== 0) return finish(stopError || new Error(stderr.trim() || `tts.py exited ${code}`));
            try {
                const result = JSON.parse(stdout.trim());
                if (!result.ok || typeof result.path !== 'string' || !result.path) throw new Error(result.error || 'tts.py 未返回音频路径');
                finish(null, result);
            } catch (error) { finish(new Error(`语音生成结果无效：${error.message}; ${stderr.trim()}`)); }
        });
    });
}

// Dependencies are explicit so failure, cancellation and routing can be tested
// without synthesizing audio or sending a QQ message.
export function voiceAction(bridge, limits, readMedia, synthesize = synthesizeVoice) {
    return async (args, exec) => {
        let path, sending = false, chat, prepared = false;
        const raw = typeof args.text === 'string' ? args.text.trim() : '';
        const chars = Array.from(raw), truncated = chars.length > 60;
        const text = chars.slice(0, 60).join('');
        const note = truncated ? '文本超过 60 字，已截断到前 60 字。' : undefined;
        const check = () => {
            const target = voiceTarget(exec?.agent, bridge);
            if (!target) throw new Error('say_voice 仅用于配置的 QQ 工作区中的私聊或群聊');
            const id = String(exec.agent.session.id);
            const chat = bridge.chatForSession(id);
            // A proactive private turn has no inbound sender role. Its fixed
            // admin recipient is still authorized; never borrow a group role.
            if (chat !== target.chat) throw new Error('当前会话映射与目标会话不一致，未发送');
            if (!bridge.connected) throw new Error('QQ 连接不可用，未发送');
            exec.signal?.throwIfAborted();
            return chat;
        };
        try {
            chat = check();
            if (!text) throw new Error('text 不能为空');
            prepared = true;
            const audio = await synthesize(text, exec.signal);
            path = audio.path;
            const gate = await bridge.mediaSendRoots(exec.agent.session.id);
            const file = await readMedia(path, limits.maxVoiceBytes, gate.roots);
            if (check() !== chat) throw new Error('会话已变化，未发送');
            sending = true;
            const message_id = await bridge.sendSegments(chat, [{ type: 'record', data: { file } }]);
            return { ok: true, mode: 'voice', path, message_id: message_id ?? null, truncated, ...(note ? { note } : {}) };
        } catch (error) {
            const voiceError = String(error?.message ?? error);
            const explicitlyRejected = error?.name === 'OneBotActionError' && /^OneBot action failed \(retcode /.test(voiceError);
            if (prepared && !exec.signal?.aborted && (!sending || explicitlyRejected)) {
                let fallbackSending = false;
                try {
                    if (check() !== chat) throw new Error('会话已变化，未补发文字');
                    fallbackSending = true;
                    const message_id = await bridge.sendSegments(chat, [{ type: 'text', data: { text } }]);
                    return { ok: true, mode: 'text', fallback: true, message_id: message_id ?? null,
                        voice_error: voiceError, truncated, note: [note, '语音未发出，原句已自动改发文字；不要再重复发送这句话。'].filter(Boolean).join(' ') };
                } catch (fallbackError) {
                    return { ok: false, fallback: false, fallback_attempted: true, voice_error: voiceError, error: String(fallbackError?.message ?? fallbackError),
                        truncated, delivery: fallbackSending ? 'unknown' : 'not_sent',
                        note: fallbackSending ? '文字发送结果未确认，请勿自动重发。' : '本次未补发文字。' };
                }
            }
            return { ok: false, error: voiceError, ...(path ? { path } : {}),
                truncated, ...(note ? { note } : {}),
                ...(sending ? { delivery: 'unknown', note: [note, '发送结果未确认，请勿自动重发语音。'].filter(Boolean).join(' ') } : {}) };
        }
    };
}
