'use strict';
const $ = (id) => document.getElementById(id);
const state = {id: null, messages: [], attachments: [], busy: false};
let agentName = '小弛';
let pendingDelete = null;
let lastDeleted = null;
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求未完成，请检查输入后重试。');
  return data;
}
function showError(message = '') { $('error').textContent = message; $('error').hidden = !message; }
function setBusy(value) {
  state.busy = value;
  for (const button of document.querySelectorAll('button')) button.disabled = value;
  $('question').readOnly = value;
  $('send-button').textContent = value ? '处理中' : '发送';
}
function scrollEnd() {
  const workspace = document.querySelector('.workspace');
  requestAnimationFrame(() => {workspace.scrollTop = workspace.scrollHeight;});
}
function closeMenu() { $('sidebar').classList.remove('open'); $('scrim').classList.remove('open'); $('menu-button').setAttribute('aria-expanded', 'false'); }
function assistantLabel() {
  const label = document.createElement('div'); label.className = 'assistant-label';
  const name = document.createElement('span'); name.textContent = agentName;
  const note = document.createElement('span'); note.className = 'answer-caption'; note.textContent = '参考答复';
  label.append(name, note); return label;
}
function renderMessages(waiting = false) {
  $('messages').replaceChildren();
  $('welcome').hidden = state.messages.length > 0 || waiting;
  for (const item of state.messages) {
    const message = document.createElement('article'); message.className = `message ${item.role}`;
    if (item.role === 'user') {
      if (item.content) {const bubble = document.createElement('div'); bubble.className = 'user-bubble'; bubble.textContent = item.content; message.append(bubble);}
      for (const name of item.attachments || []) {const file = document.createElement('div'); file.className = 'uploaded'; file.textContent = `▤ ${name}`; message.append(file);}
    } else {
      message.append(assistantLabel());
      const answer = document.createElement('div'); answer.className = 'answer';
      // Only server-rendered Markdown (HTML disabled) is accepted here.
      if (item.html) answer.innerHTML = item.html; else answer.textContent = item.content;
      for (const link of answer.querySelectorAll('a')) {link.target = '_blank'; link.rel = 'noopener noreferrer';}
      message.append(answer);
      const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'copy-button'; copy.textContent = '复制答复';
      copy.addEventListener('click', async () => {try {await navigator.clipboard.writeText(item.content); copy.textContent = '已复制';} catch (_) {showError('浏览器未允许复制，请选择答复文字手动复制。');}});
      message.append(copy);
      if (Array.isArray(item.related_questions) && item.related_questions.length === 3) {
        const related = document.createElement('section'); related.className = 'related-questions'; related.setAttribute('aria-label', '相关问题');
        const heading = document.createElement('h3'); heading.textContent = '相关问题';
        const hint = document.createElement('span'); hint.textContent = '点击填入提问框'; heading.append(hint); related.append(heading);
        for (const question of item.related_questions) {
          const button = document.createElement('button'); button.type = 'button'; button.disabled = state.busy;
          button.textContent = question; button.addEventListener('click', () => useQuestion(question)); related.append(button);
        }
        message.append(related);
      }
    }
    $('messages').append(message);
  }
  if (waiting) {
    const article = document.createElement('article'); article.className = 'message assistant'; article.append(assistantLabel());
    const text = document.createElement('div'); text.className = 'waiting'; text.setAttribute('role', 'status');
    const phase = document.createElement('span'); phase.id = 'progress-text'; phase.textContent = `${agentName}正在理解问题……`;
    const elapsed = document.createElement('small'); elapsed.id = 'progress-elapsed'; elapsed.className = 'waiting-elapsed'; elapsed.setAttribute('aria-hidden', 'true');
    elapsed.textContent = '已深度思考 0 秒';
    text.append(phase, elapsed); article.append(text); $('messages').append(article);
  }
  scrollEnd();
}
function watchProgress(conversationId, requestId) {
  let stopped = false, polling = false;
  const started = performance.now();
  const tick = async () => {
    const elapsed = $('progress-elapsed');
    if (elapsed) elapsed.textContent = `已深度思考 ${Math.floor((performance.now() - started) / 1000)} 秒`;
    if (stopped || polling) return;
    polling = true;
    try {
      const snapshot = await api(`/api/conversations/${conversationId}/progress/${requestId}`);
      if (!stopped && snapshot.status === 'running' && $('progress-text')) $('progress-text').textContent = snapshot.message;
    } catch (_) {
      // A missing snapshot does not retry the answer request.
    } finally {polling = false;}
  };
  const timer = setInterval(tick, 1000);
  return () => {stopped = true; clearInterval(timer);};
}
function renderAttachments() {
  $('attachments').replaceChildren();
  state.attachments.forEach((item, index) => {
    const chip = document.createElement('div'); chip.className = 'attachment-chip';
    const name = document.createElement('span'); name.textContent = `▤ ${item.name}`;
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×'; remove.setAttribute('aria-label', `移除 ${item.name}`);
    remove.addEventListener('click', () => {if (state.busy) return; state.attachments.splice(index, 1); renderAttachments();});
    chip.append(name, remove); $('attachments').append(chip);
  });
}
async function refreshHistory() {
  const {conversations} = await api('/api/conversations');
  $('history-count').textContent = conversations.length;
  $('history').replaceChildren();
  if (!conversations.length) {const note = document.createElement('p'); note.className = 'history-empty'; note.textContent = '暂无历史对话'; $('history').append(note);}
  for (const item of conversations) {
    const row = document.createElement('div'); row.className = `history-row${item.id === state.id ? ' active' : ''}`;
    const button = document.createElement('button'); button.className = `history-item${item.id === state.id ? ' active' : ''}`; button.title = item.title; button.disabled = state.busy;
    const label = document.createElement('span'); label.className = 'label'; label.textContent = item.title; button.append(label);
    button.addEventListener('click', () => selectConversation(item.id));
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'history-delete'; remove.disabled = state.busy;
    remove.title = '删除对话'; remove.setAttribute('aria-label', `删除对话：${item.title}`);
    remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7"/></svg>';
    remove.addEventListener('click', () => {
      if (state.busy) return;
      pendingDelete = item; $('delete-title').textContent = item.title; $('delete-dialog').showModal();
    });
    row.append(button, remove); $('history').append(row);
  }
}
async function selectConversation(id) {
  if (state.busy) return;
  setBusy(true); showError();
  try {
    const record = await api(`/api/conversations/${id}`);
    state.id = record.id; state.messages = record.messages; state.attachments = [];
    localStorage.setItem('xiaochi-conversation', state.id);
    $('question').value = '';
    renderAttachments(); renderMessages(); closeMenu(); await refreshHistory();
  } catch (error) {showError(error.message);} finally {setBusy(false);}
}
async function ensureConversation() {
  if (!state.id) {const record = await api('/api/conversations', {method:'POST'}); state.id = record.id; localStorage.setItem('xiaochi-conversation', state.id);}
  return state.id;
}
function resetConversation() {
  state.id = null; state.messages = []; state.attachments = []; localStorage.removeItem('xiaochi-conversation');
  $('question').value = ''; $('question').style.height = 'auto';
  showError(); renderAttachments(); renderMessages(); closeMenu();
}
$('new-chat').addEventListener('click', () => {
  if (state.busy) return;
  resetConversation();
  refreshHistory().catch(error => showError(error.message)); $('question').focus();
});
$('delete-cancel').addEventListener('click', () => $('delete-dialog').close());
$('delete-dialog').addEventListener('close', () => {pendingDelete = null;});
$('delete-confirm').addEventListener('click', async () => {
  if (state.busy || !pendingDelete) return;
  const item = pendingDelete; $('delete-dialog').close(); setBusy(true); showError();
  try {
    await api(`/api/conversations/${item.id}`, {method: 'DELETE'});
    if (state.id === item.id) resetConversation();
    lastDeleted = item; $('history-notice').hidden = false;
    await refreshHistory();
  } catch (error) {showError(error.message);} finally {setBusy(false);}
});
$('undo-delete').addEventListener('click', async () => {
  if (state.busy || !lastDeleted) return;
  setBusy(true); showError();
  try {
    await api(`/api/conversations/${lastDeleted.id}/restore`, {method: 'POST'});
    lastDeleted = null; $('history-notice').hidden = true; await refreshHistory();
  } catch (error) {showError(error.message);} finally {setBusy(false);}
});
$('menu-button').addEventListener('click', () => {
  const open = $('sidebar').classList.toggle('open'); $('scrim').classList.toggle('open', open);
  $('menu-button').setAttribute('aria-expanded', String(open));
});
$('scrim').addEventListener('click', closeMenu);
$('attach-button').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async () => {
  if (state.busy) return;
  const files = [...$('file-input').files]; $('file-input').value = '';
  if (files.length + state.attachments.length > 5) {showError('每条问题最多上传 5 份材料。'); return;}
  if (files.some(file => file.size > 25 * 1024 * 1024)) {showError('单个文件不能超过 25 MB。'); return;}
  setBusy(true); showError();
  try {
    await ensureConversation();
    for (const file of files) {const body = new FormData(); body.append('file', file); state.attachments.push(await api(`/api/conversations/${state.id}/attachments`, {method:'POST', body})); renderAttachments();}
  } catch (error) {showError(error.message);} finally {setBusy(false);}
});
$('question').addEventListener('keydown', event => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); $('chat-form').requestSubmit();}});
$('question').addEventListener('input', () => {$('question').style.height = 'auto'; $('question').style.height = `${Math.min($('question').scrollHeight, 180)}px`;});
$('chat-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  const draft = $('question').value; const draftHeight = $('question').style.height;
  const text = draft.trim(); if (!text && !state.attachments.length) { $('question').focus(); return; }
  let committed = false;
  let stopProgress = () => {};
  const previous = [...state.messages]; const files = [...state.attachments];
  setBusy(true); showError();
  $('question').value = ''; $('question').style.height = 'auto';
  state.messages.push({role:'user', content:text, attachments:files.map(item => item.name)}); renderMessages(true);
  try {
    await ensureConversation();
    const requestId = crypto.randomUUID();
    stopProgress = watchProgress(state.id, requestId);
    const response = await api(`/api/conversations/${state.id}/messages`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:text, attachments:files.map(item => item.id), request_id:requestId})});
    committed = true;
    state.messages.push({role:'assistant', content:response.answer, html:response.answer_html, related_questions:response.related_questions});
    state.attachments = []; renderAttachments(); renderMessages();
    await refreshHistory();
  } catch (error) {
    if (!committed) {state.messages = previous; $('question').value = draft; $('question').style.height = draftHeight;}
    renderMessages(); showError(error.message);
  }
  finally {stopProgress(); setBusy(false); $('question').focus();}
});
function useQuestion(text) {
  if (state.busy) return;
  $('question').value = text;
  $('question').dispatchEvent(new Event('input'));
  $('question').focus();
}
for (const button of document.querySelectorAll('[data-question]')) {
  button.addEventListener('click', () => useQuestion(button.dataset.question));
}
async function initialize() {
  try {
    const config = await api('/api/config'); agentName = config.name; $('footer-note').textContent = config.disclaimer;
    config.quick_questions.forEach(item => {
      const button = document.createElement('button'); button.className = 'suggestion'; button.type = 'button';
      const copy = document.createElement('span'); copy.className = 'suggestion-copy';
      const title = document.createElement('strong'); title.textContent = item.title; const caption = document.createElement('small'); caption.textContent = item.caption; copy.append(title, caption);
      button.append(copy);
      button.addEventListener('click', () => useQuestion(item.text)); $('suggestions').append(button);
    });
    await refreshHistory();
    const remembered = localStorage.getItem('xiaochi-conversation'); if (remembered) await selectConversation(remembered);
  } catch (error) {showError('页面连接未完成，请刷新后重试。');}
}
initialize();
