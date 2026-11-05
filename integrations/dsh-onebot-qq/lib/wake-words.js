// Read only the current message's parsed text, never nicknames, quotes,
// forwarded messages, the archive, or OCR. Access/role gates run before this.
export const WAKE_WORDS = Object.freeze(['鱼小二', '小二', '二姐']);
export function matchWakeWord(text) {
    return WAKE_WORDS.find(word => String(text ?? '').includes(word));
}
