// Strong machine-context signatures, not a general ban on technical conversation.
export function internalTextReason(text) {
    if (/<\/?whale_feeling_context\b|只有上下文中有明确的新感受，才用 life_feel 的 tone 与 note 记录|tone 不改变原心情分数，15分钟内/i.test(text)) return 'feeling_context_echo';
    if (/You are (?:an AI agent powered by DeepSeek Harness|a coding agent powered by the [^\n]+ model)\./i.test(text)) return 'system_prompt_echo';
    if (/Time sampled while preparing turn \d+, step \d+:|Current runtime context\. This snapshot supersedes|Current DSH file policy:|Current DeepSeek Harness implementation checkout:/i.test(text)) return 'runtime_context_echo';
    if (/<user_message\b[^>]*\bqq\s*=/i.test(text)) return 'input_boundary_echo';
    if (/【记事的规矩】/.test(text) && /memory_?list|memory_?note|selfnote_?append/i.test(text)) return 'memory_rule_echo';
    if (/(?:^|\n)\s*Keep \d+(?:[–-]\d+)? (?:short )?bubbles\b/i.test(text)
        || /(?:^|\n)\s*(?:He|She|The user) says[^\n]{0,180}\bRespond:/i.test(text)) return 'reply_planning_echo';
    if (/<\/(?:think|thinking|analysis|reasoning)\s*>/i.test(text)
        && !/<(?:think|thinking|analysis|reasoning)\b[^>]*>/i.test(text)) return 'unpaired_reasoning_boundary';
    return null;
}

export function internalStatus(text) {
    return /^\s*(?:\[\[DSH_SILENT\]\]|[（(](?:未发送消息|不发送消息|本轮不发送|本轮静默|保持沉默|无需回复|决定不打扰)[^）)\n]*[）)])\s*$/.test(text);
}
