import { internalTextReason, internalStatus } from './reply-privacy.js';
// Apply before both normal and deferred delivery; reasoning is never chat text.
export function autonomousSource(message) {
    return ['speak-up', 'speak-up:anchor'].includes(message?.source?.kind);
}

export function visibleAssistantMessage(message, autonomous = false) {
    const raw = message.content.filter(block => block.type === 'text').map(block => block.text).join('');
    const rejected = internalTextReason(raw);
    if (rejected) return {...message, content: [], outgoingSuppressedReason: rejected};
    const hasToolCall = message.content.some(block => block.type === 'tool-call');
    const content = message.content.flatMap(block => {
        if (block.type === 'reasoning' || ['analysis', 'reasoning'].includes(block.channel)) return [];
        if (block.type !== 'text') return [block];
        if (autonomous && hasToolCall) return [];
        let text = block.text
            .replace(/<(think|thinking|analysis|reasoning)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, '')
            .replace(/\[\[DSH_SILENT\]\]/g, '');
        if (autonomous) {
            text = text.split('\n').filter(line => !internalStatus(line)).join('\n');
        }
        return text.trim() ? [{...block, text}] : [];
    });
    return {...message, content};
}
