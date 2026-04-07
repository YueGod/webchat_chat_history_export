/* ============================================================
   WeChat Viewer — Frontend Logic
   ============================================================ */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let state = {
  accounts: [],
  conversations: [],
  currentChat: null,
  currentPage: 0,
  totalPages: 0,
  loaded: false,
};

const api = () => window.pywebview.api;

/* ── Init ── */
window.addEventListener('pywebviewready', async () => {
  setStatus('正在检测微信数据...');
  initDateInputs();
  bindEvents();
  await detectAccounts();
});

function initDateInputs() {
  const today = new Date().toISOString().split('T')[0];
  $('#date-end').value = today;
  $('#date-start').value = '2020-01-01';
}

function bindEvents() {
  $('#search-input').addEventListener('input', onSearch);
  $('#decrypt-btn').addEventListener('click', showDecryptModal);
  $('#folder-btn').addEventListener('click', loadFolder);
  $('#filter-btn').addEventListener('click', () => loadMessages(0));
  $('#export-btn').addEventListener('click', exportCSV);
  $('#export-all-btn').addEventListener('click', exportAllCSV);
  $('#prev-btn').addEventListener('click', () => loadMessages(state.currentPage - 1));
  $('#next-btn').addEventListener('click', () => loadMessages(state.currentPage + 1));
  $('#decrypt-modal-close').addEventListener('click', hideDecryptModal);
  $('#decrypt-modal').addEventListener('click', e => {
    if (e.target === $('#decrypt-modal')) hideDecryptModal();
  });
}

/* ── Account Detection ── */
async function detectAccounts() {
  try {
    state.accounts = await api().detect_accounts();
    const cached = state.accounts.filter(a => a.has_cached_decrypt);

    if (cached.length > 0) {
      setStatus('发现已解密的缓存数据，正在加载...');
      await loadDB(cached[0].cached_dir);
      if (state.accounts.some(a => a.encrypted_msg_count > 0)) {
        $('#decrypt-btn').style.display = '';
        $('#decrypt-btn').querySelector('span').textContent = '重新解密';
      }
      return;
    }

    const needsDecrypt = state.accounts.filter(a => a.encrypted_msg_count > 0);
    if (needsDecrypt.length > 0) {
      $('#decrypt-btn').style.display = '';
      setWelcome('检测到加密的微信数据库',
        `发现 ${needsDecrypt[0].encrypted_msg_count} 个加密消息数据库\n点击左侧「一键解密」开始（需要管理员密码）`);
      setStatus(`检测到 ${state.accounts.length} 个账号，待解密`);
      return;
    }

    setWelcome('未检测到微信数据', '请确认已安装并登录过 WeChat for Mac 4.x\n或点击「选择目录」加载已解密的数据库');
    setStatus('未检测到微信数据');
  } catch (e) {
    setWelcome('检测失败', e.toString());
  }
}

/* ── Decrypt Flow ── */
function showDecryptModal() {
  const modal = $('#decrypt-modal');
  const container = $('#decrypt-accounts');
  container.innerHTML = '';
  $('#decrypt-progress').style.display = 'none';

  const accounts = state.accounts.filter(a => a.encrypted_msg_count > 0);
  if (accounts.length === 0) {
    container.innerHTML = '<p style="color:var(--text-3)">没有需要解密的账号</p>';
    modal.style.display = '';
    return;
  }

  accounts.forEach(a => {
    const card = document.createElement('div');
    card.className = 'account-card';
    card.innerHTML = `<div class="label">${esc(a.label)}</div>
      <div class="detail">${a.encrypted_msg_count} 个加密消息库 · ${a.total_db_count} 个数据库</div>`;
    card.onclick = () => startDecrypt(a.index);
    container.appendChild(card);
  });
  modal.style.display = '';
}

function hideDecryptModal() {
  $('#decrypt-modal').style.display = 'none';
}

async function startDecrypt(index) {
  $('#decrypt-accounts').style.display = 'none';
  $('#decrypt-progress').style.display = '';
  $('#progress-fill').style.width = '30%';
  $('#progress-text').textContent = '正在启动解密...';

  const res = await api().start_decrypt(index);
  if (!res.ok) {
    $('#progress-text').textContent = '错误: ' + res.error;
    return;
  }
  pollDecryptStatus();
}

async function pollDecryptStatus() {
  const st = await api().get_decrypt_status();
  $('#progress-text').textContent = st.progress || '处理中...';

  if (st.running) {
    $('#progress-fill').style.width = '60%';
    setTimeout(pollDecryptStatus, 600);
    return;
  }

  if (st.error) {
    $('#progress-fill').style.width = '0%';
    $('#progress-text').textContent = '解密失败: ' + st.error;
    return;
  }

  if (st.done) {
    $('#progress-fill').style.width = '100%';
    $('#progress-text').textContent = '解密完成，正在加载...';
    hideDecryptModal();
    await loadDB(st.result_dir);
    $('#decrypt-btn').querySelector('span').textContent = '重新解密';
  }
}

/* ── Load Database ── */
async function loadFolder() {
  const folder = prompt('请输入已解密数据库的目录路径:');
  if (folder) await loadDB(folder);
}

async function loadDB(path) {
  setStatus('正在加载数据库...');
  const res = await api().load_database(path);
  if (!res.ok) {
    setWelcome('加载失败', res.error);
    setStatus('加载失败');
    return;
  }

  state.loaded = true;
  state.conversations = await api().get_conversations();
  renderConversations(state.conversations);
  setStatus(`已加载 ${res.conversations} 个会话，共 ${res.total_messages.toLocaleString()} 条消息`);
  $('#sidebar-footer').textContent = `${res.conversations} 个会话 · ${res.total_messages.toLocaleString()} 条消息`;

  if (state.conversations.length === 0) {
    setWelcome('未找到聊天记录', '当前目录下没有发现有效的聊天数据');
  } else {
    setWelcome('', '请从左侧选择一个会话');
  }
}

/* ── Conversations ── */
function renderConversations(convs) {
  const list = $('#conv-list');
  list.innerHTML = '';
  if (convs.length === 0) {
    list.innerHTML = '<div class="empty-state"><p>没有会话</p></div>';
    return;
  }

  convs.forEach((c, i) => {
    const el = document.createElement('div');
    el.className = 'conv-item';
    el.dataset.hash = c.chat_hash;
    el.style.animationDelay = `${Math.min(i * 15, 300)}ms`;
    el.innerHTML = `
      <div class="conv-name">${esc(c.display_name)}</div>
      <div class="conv-meta">
        <span>${c.message_count.toLocaleString()} 条</span>
        ${c.last_time ? `<span>${c.last_time}</span>` : ''}
        ${c.is_group ? '<span>群聊</span>' : ''}
      </div>`;
    el.onclick = () => selectConversation(c);
    list.appendChild(el);
  });
}

function selectConversation(conv) {
  $$('.conv-item').forEach(el => el.classList.remove('active'));
  const el = $(`.conv-item[data-hash="${conv.chat_hash}"]`);
  if (el) el.classList.add('active');

  state.currentChat = conv;
  $('#chat-title').textContent = conv.display_name;
  $('#chat-badge').textContent = conv.is_group ? '群聊' : '私聊';
  $('#toolbar').style.display = '';
  loadMessages(0);
}

function onSearch() {
  const q = $('#search-input').value.trim().toLowerCase();
  if (!q) {
    renderConversations(state.conversations);
    return;
  }
  const filtered = state.conversations.filter(c =>
    c.display_name.toLowerCase().includes(q) ||
    (c.user_name && c.user_name.toLowerCase().includes(q))
  );
  renderConversations(filtered);
}

/* ── Messages ── */
async function loadMessages(page) {
  if (!state.currentChat) return;

  const startDate = $('#date-start').value || '';
  const endDate = $('#date-end').value || '';
  setStatus('加载消息中...');

  const res = await api().get_messages(state.currentChat.chat_hash, startDate, endDate, page);

  state.currentPage = res.page;
  state.totalPages = res.pages;

  renderMessages(res.messages, res.is_group);
  updatePagination(res);
  setStatus(`${res.display_name} · ${res.total.toLocaleString()} 条消息`);
}

function renderMessages(msgs, isGroup) {
  const area = $('#messages-area');
  if (msgs.length === 0) {
    area.innerHTML = '<div class="welcome"><p>当前时间范围内没有消息</p></div>';
    return;
  }

  let html = '';
  let lastDate = '';

  msgs.forEach((m, i) => {
    if (m.date !== lastDate) {
      lastDate = m.date;
      html += `<div class="date-divider"><span>${esc(m.date)}</span></div>`;
    }

    const delay = Math.min(i * 8, 200);

    if (m.type === 10000) {
      html += `<div class="msg-row system" style="animation-delay:${delay}ms">
        <div class="msg-bubble">${esc(m.content)}</div></div>`;
      return;
    }

    const cls = m.is_sender ? 'sent' : 'recv';
    const senderHtml = (!m.is_sender && isGroup && m.sender_name)
      ? `<div class="msg-sender">${esc(m.sender_name)}</div>` : '';

    html += `<div class="msg-row ${cls}" style="animation-delay:${delay}ms">
      <div class="msg-bubble">
        ${senderHtml}
        <div class="msg-content">${esc(m.content)}</div>
        <div class="msg-time">${m.time}</div>
      </div>
    </div>`;
  });

  area.innerHTML = html;
  area.scrollTop = 0;
}

function updatePagination(res) {
  const pag = $('#pagination');
  if (res.pages <= 1) { pag.style.display = 'none'; return; }

  pag.style.display = '';
  $('#page-info').textContent = `第 ${res.page + 1} / ${res.pages} 页 · 共 ${res.total.toLocaleString()} 条`;
  $('#prev-btn').disabled = res.page <= 0;
  $('#next-btn').disabled = res.page >= res.pages - 1;
}

/* ── Export ── */
async function exportCSV() {
  if (!state.currentChat) return;
  const res = await api().export_csv(state.currentChat.chat_hash);
  if (res.ok) {
    setStatus(`已导出 ${res.count} 条消息到 ${res.path}`);
  } else if (res.error !== 'cancelled') {
    alert('导出失败: ' + res.error);
  }
}

async function exportAllCSV() {
  const res = await api().export_all_csv();
  if (res.ok) {
    setStatus(`已导出 ${res.count} 个会话到 ${res.path}`);
  } else if (res.error !== 'cancelled') {
    alert('导出失败: ' + res.error);
  }
}

/* ── Helpers ── */
function setStatus(text) {
  $('#status-bar').textContent = text;
}

function setWelcome(title, body) {
  const area = $('#messages-area');
  area.innerHTML = `<div class="welcome">
    <div class="welcome-icon"><img src="icon.png" width="80" height="80" style="border-radius:20px;opacity:0.7"></div>
    ${title ? `<h2>${esc(title)}</h2>` : ''}
    ${body ? `<p>${esc(body).replace(/\n/g, '<br>')}</p>` : ''}
  </div>`;
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
