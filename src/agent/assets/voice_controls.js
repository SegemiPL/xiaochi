() => {
  if (window.w3VoiceObserver) window.w3VoiceObserver.disconnect();
  const speaker = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
  const enhance = () => {
    const mic = document.getElementById('w3-mic-button');
    if (mic) {
      mic.title = '语音输入';
      mic.setAttribute('aria-label', '语音输入');
    }
    const chat = document.querySelector('.w3-chatbot');
    if (!chat) return;
    chat.querySelectorAll('[aria-label^="bot\'s message:"]').forEach(bubble => {
      if (!bubble.closest('.bot-row')?.querySelector('[title="3wagent"]')) return;
      const host = bubble.parentElement.querySelector('.message-buttons-bot');
      if (!host) return;
      const rows = [...chat.querySelectorAll('.message-row')];
      const following = rows.slice(rows.indexOf(bubble.closest('.message-row')) + 1);
      const nextUser = following.findIndex(el => el.classList.contains('user-row'));
      const tail = nextUser < 0 ? following : following.slice(0, nextUser);
      const intermediate = tail.some(el => el.classList.contains('bot-row'));
      const existing = host.querySelector('.w3-read-reply');
      if (existing) {
        existing.hidden = intermediate;
        const busy = !!document.querySelector('.w3-chat-input textarea:disabled');
        if (existing.disabled !== busy) existing.disabled = busy;
        return;
      }
      if (intermediate) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'w3-read-reply';
      button.disabled = !!document.querySelector('.w3-chat-input textarea:disabled');
      button.title = '朗读结论';
      button.setAttribute('aria-label', '朗读结论');
      button.innerHTML = speaker;
      button.addEventListener('click', () => {
        const rows = [...chat.querySelectorAll('.message-row')];
        const row = bubble.closest('.message-row');
        window.w3VoiceTurn = rows.slice(0, rows.indexOf(row) + 1)
          .filter(el => el.classList.contains('user-row')).length - 1;
        document.querySelectorAll('.w3-read-reply').forEach(el => el.removeAttribute('data-active'));
        button.dataset.active = 'true';
        document.getElementById('w3-tts-trigger')?.click();
      });
      host.appendChild(button);
    });
  };
  // Schedule once per render frame, including streamed replies and restored history.
  let scheduled = false;
  window.w3VoiceObserver = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; enhance(); });
  });
  const attach = () => {
    const stage = document.querySelector('.w3-chat-stage');
    if (!stage) { setTimeout(attach, 100); return; }
    window.w3VoiceObserver.observe(stage, {childList: true, subtree: true, attributes: true, attributeFilter: ['disabled']});
    enhance();
  };
  attach();
}
