/* JACC Phase 3 in-app chat UI — staged only. */
(function (global) {
  'use strict';

  const ERROR_MESSAGES = Object.freeze({
    chat_api_base_missing: 'Chat server လိပ်စာ မသတ်မှတ်ရသေးပါ။',
    device_binding_missing: 'Device verification module မဖွင့်ရသေးပါ။',
    session_missing: 'Login session မရှိတော့ပါ။ ပြန် Login ဝင်ပါ။',
    chat_network_unavailable: 'Chat server ကို ဆက်သွယ်မရပါ။ Internet စစ်ပါ။',
    chat_request_failed: 'Chat request မအောင်မြင်ပါ။',
    chat_access_denied: 'ဒီ conversation ကို ကြည့်ခွင့်မရှိပါ။',
    chat_send_denied: 'ဒီ conversation ထဲ စာပို့ခွင့်မရှိပါ။',
    chat_thread_closed: 'ဒီ Chat ကို ပိတ်ထားပြီးပါပြီ။',
    chat_thread_missing: 'Chat conversation မတွေ့ပါ။',
    chat_request_not_found: 'Request ID မတွေ့ပါ။',
    chat_request_has_no_assigned_broker: 'ဒီ Request အတွက် Broker မချိတ်ရသေးပါ။',
    request_code_invalid: 'Request ID ပုံစံ မမှန်ပါ။',
    message_length_invalid: 'စာသား ၁ လုံးမှ ၄,၀၀၀ လုံးအတွင်း ဖြစ်ရပါမယ်။',
    send_rate_limited: 'စာပို့တာ မြန်လွန်းနေပါတယ်။ ခဏစောင့်ပါ။',
    rate_limited: 'Request များနေပါတယ်။ ခဏစောင့်ပြီး ပြန်လုပ်ပါ။',
    device_mismatch: 'ဒီ Membership ကို အခြား device တစ်ခုနဲ့ ချိတ်ထားပါတယ်။',
    device_required: 'Secure Device ID မရပါ။ Private mode ပိတ်ပါ။',
    device_invalid: 'Device verification မအောင်မြင်ပါ။',
    profile_not_found: 'JACC profile မတွေ့ပါ။ Admin ကို ဆက်သွယ်ပါ။',
    profile_inactive: 'Account ကို အသုံးပြုခွင့် ပိတ်ထားပါတယ်။',
    chat_backend_unavailable: 'Chat database ခဏမရပါ။',
  });

  class JACCAppChatUI {
    constructor(root, client) {
      this.root = root;
      this.client = client;
      this.threads = [];
      this.activeThread = null;
      this.visible = false;
      this.initialized = false;
      this.loadingThreads = false;
      this.sending = false;
      this.elements = this.collectElements();
    }

    collectElements() {
      const byId = (id) => this.root.querySelector('#' + id);
      return {
        shell: byId('jacc-chat-shell'),
        threadList: byId('jacc-chat-thread-list'),
        requestInput: byId('jacc-chat-request-code'),
        openButton: byId('jacc-chat-open-button'),
        refreshButton: byId('jacc-chat-refresh-button'),
        backButton: byId('jacc-chat-back-button'),
        counterpartName: byId('jacc-chat-counterpart-name'),
        counterpartMeta: byId('jacc-chat-counterpart-meta'),
        status: byId('jacc-chat-status'),
        closeButton: byId('jacc-chat-close-button'),
        messages: byId('jacc-chat-messages'),
        placeholder: byId('jacc-chat-placeholder'),
        composer: byId('jacc-chat-composer'),
        textarea: byId('jacc-chat-textarea'),
        sendButton: byId('jacc-chat-send-button'),
        notice: byId('jacc-chat-notice'),
      };
    }

    async init() {
      if (this.initialized) return;
      this.initialized = true;
      this.bindEvents();
      this.renderInactiveConversation();
      await this.loadThreads();
    }

    bindEvents() {
      const el = this.elements;
      el.openButton.addEventListener('click', () => this.openFromInput());
      el.refreshButton.addEventListener('click', () => this.loadThreads());
      el.backButton.addEventListener('click', () => this.showThreadList());
      el.sendButton.addEventListener('click', () => this.sendCurrentMessage());
      el.closeButton.addEventListener('click', () => this.closeCurrentThread());
      el.requestInput.addEventListener('input', () => {
        el.requestInput.value = el.requestInput.value.toUpperCase();
      });
      el.requestInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          this.openFromInput();
        }
      });
      el.textarea.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          this.sendCurrentMessage();
        }
      });

      this.client.addEventListener('messages', (event) => {
        const detail = event.detail || {};
        if (!this.activeThread || detail.threadId !== this.activeThread.thread_id) return;
        this.renderMessages(Array.isArray(detail.messages) ? detail.messages : []);
      });
      this.client.addEventListener('chaterror', (event) => {
        const error = event.detail || new Error('chat_request_failed');
        this.showNotice(this.errorMessage(error), 'error');
      });
      this.client.addEventListener('threadclosed', () => {
        if (!this.activeThread) return;
        this.activeThread.status = 'closed';
        this.renderConversationHeader();
        this.setComposerEnabled(false);
      });
    }

    async setVisible(visible) {
      this.visible = Boolean(visible);
      if (!this.initialized && this.visible) await this.init();
      if (!this.initialized) return;
      if (!this.visible) {
        this.client.stopPolling();
        return;
      }
      if (this.activeThread && this.activeThread.thread_id && this.activeThread.status === 'open') {
        this.client.startPolling(this.activeThread.thread_id);
      }
    }

    async loadThreads() {
      if (this.loadingThreads) return;
      this.loadingThreads = true;
      this.elements.refreshButton.disabled = true;
      this.showNotice('Conversation စာရင်းယူနေပါတယ်…', '');
      try {
        this.threads = await this.client.listThreads(100);
        this.renderThreadList();
        this.showNotice('', '');
      } catch (error) {
        this.showNotice(this.errorMessage(error), 'error');
        this.renderThreadList();
      } finally {
        this.loadingThreads = false;
        this.elements.refreshButton.disabled = false;
      }
    }

    renderThreadList() {
      const list = this.elements.threadList;
      list.replaceChildren();
      if (!this.threads.length) {
        const empty = document.createElement('div');
        empty.className = 'jacc-chat-empty-list';
        empty.textContent = 'Conversation မရှိသေးပါ။ Request ID ထည့်ပြီး Chat ဖွင့်နိုင်ပါတယ်။';
        list.appendChild(empty);
        return;
      }

      this.threads.forEach((thread) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'jacc-chat-thread';
        if (this.activeThread && thread.thread_id === this.activeThread.thread_id) {
          button.classList.add('active');
        }
        button.addEventListener('click', () => this.selectThread(thread));

        const left = document.createElement('div');
        const name = document.createElement('div');
        name.className = 'jacc-chat-thread-name';
        name.textContent = thread.counterpart_name || 'JACC Conversation';
        const code = document.createElement('div');
        code.className = 'jacc-chat-thread-code';
        code.textContent = thread.request_code || '—';
        left.append(name, code);

        const time = document.createElement('div');
        time.className = 'jacc-chat-thread-time';
        time.textContent = this.formatCompactTime(thread.last_message_at);

        const unreadValue = Math.max(0, Number(thread.unread_count || 0));
        const unread = document.createElement('span');
        unread.className = 'jacc-chat-unread';
        unread.textContent = unreadValue > 99 ? '99+' : String(unreadValue);
        unread.hidden = unreadValue === 0;

        button.append(left, time, document.createElement('span'), unread);
        list.appendChild(button);
      });
    }

    async openFromInput() {
      const code = String(this.elements.requestInput.value || '').trim().toUpperCase();
      if (!code) {
        this.showNotice('Request ID ထည့်ပါ။', 'error');
        return;
      }
      await this.openRequestCode(code, null);
    }

    async selectThread(thread) {
      if (!thread || !thread.request_code) return;
      await this.openRequestCode(thread.request_code, thread);
    }

    async openRequestCode(code, listThread) {
      this.setBusy(true);
      this.showNotice('Chat ဖွင့်နေပါတယ်…', '');
      try {
        const opened = await this.client.openRequest(code);
        this.activeThread = Object.assign({}, listThread || {}, opened || {});
        if (!this.activeThread.counterpart_name && listThread) {
          this.activeThread.counterpart_name = listThread.counterpart_name;
        }
        this.elements.requestInput.value = this.activeThread.request_code || code;
        this.renderThreadList();
        this.renderConversationHeader();
        this.elements.shell.classList.add('conversation-open');
        this.elements.placeholder.hidden = true;
        this.elements.messages.hidden = false;
        this.elements.composer.hidden = false;
        this.setComposerEnabled(this.activeThread.status === 'open');
        const messages = await this.client.listMessages(this.activeThread.thread_id, { limit: 100 });
        this.renderMessages(messages);
        if (this.visible && this.activeThread.status === 'open') {
          this.client.startPolling(this.activeThread.thread_id);
        }
        this.showNotice('', '');
        await this.loadThreads();
      } catch (error) {
        this.showNotice(this.errorMessage(error), 'error');
      } finally {
        this.setBusy(false);
      }
    }

    renderConversationHeader() {
      const thread = this.activeThread;
      if (!thread) {
        this.elements.counterpartName.textContent = 'Conversation ရွေးပါ';
        this.elements.counterpartMeta.textContent = 'Request ID မရွေးရသေးပါ';
        this.elements.status.textContent = 'Idle';
        this.elements.status.className = 'jacc-chat-status closed';
        this.elements.closeButton.hidden = true;
        return;
      }
      this.elements.counterpartName.textContent = thread.counterpart_name || 'JACC Conversation';
      this.elements.counterpartMeta.textContent = thread.request_code || '—';
      const status = String(thread.status || 'open').toLowerCase();
      this.elements.status.textContent = status;
      this.elements.status.className = 'jacc-chat-status' + (status === 'open' ? '' : ' ' + status);
      this.elements.closeButton.hidden = status !== 'open';
    }

    renderInactiveConversation() {
      this.activeThread = null;
      this.renderConversationHeader();
      this.elements.shell.classList.remove('conversation-open');
      this.elements.placeholder.hidden = false;
      this.elements.messages.hidden = true;
      this.elements.composer.hidden = true;
      this.elements.messages.replaceChildren();
    }

    renderMessages(messages) {
      const container = this.elements.messages;
      const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
      container.replaceChildren();
      if (!messages.length) {
        const empty = document.createElement('div');
        empty.className = 'jacc-chat-placeholder';
        empty.textContent = 'စာမရှိသေးပါ။ ပထမဆုံး message ပို့နိုင်ပါတယ်။';
        container.appendChild(empty);
        return;
      }

      messages.forEach((message) => {
        const role = this.normalizedRole(message.sender_role, message.message_type);
        const item = document.createElement('article');
        item.className = 'jacc-chat-message ' + role;

        const label = document.createElement('div');
        label.className = 'jacc-chat-message-label';
        label.textContent = role === 'broker' ? 'Broker' : role === 'customer' ? 'Customer' : 'JACC';

        const bubble = document.createElement('div');
        bubble.className = 'jacc-chat-bubble';
        bubble.textContent = String(message.body || '');

        const time = document.createElement('time');
        time.className = 'jacc-chat-message-time';
        time.textContent = this.formatMessageTime(message.created_at);

        item.append(label, bubble, time);
        container.appendChild(item);
      });

      if (wasNearBottom || messages.length < 20) {
        container.scrollTop = container.scrollHeight;
      }
    }

    normalizedRole(senderRole, messageType) {
      if (String(messageType || '').toLowerCase() === 'system') return 'system';
      const role = String(senderRole || '').toLowerCase();
      if (role === 'broker') return 'broker';
      if (role === 'customer') return 'customer';
      return 'system';
    }

    async sendCurrentMessage() {
      if (this.sending || !this.activeThread || this.activeThread.status !== 'open') return;
      const text = String(this.elements.textarea.value || '').trim();
      if (!text) return;
      this.sending = true;
      this.elements.sendButton.disabled = true;
      try {
        await this.client.sendText(text, { threadId: this.activeThread.thread_id });
        this.elements.textarea.value = '';
        const messages = await this.client.listMessages(this.activeThread.thread_id, { limit: 100 });
        this.renderMessages(messages);
        this.showNotice('ပို့ပြီးပါပြီ။', 'ok');
        global.setTimeout(() => this.showNotice('', ''), 1300);
        await this.loadThreads();
      } catch (error) {
        this.showNotice(this.errorMessage(error), 'error');
      } finally {
        this.sending = false;
        this.elements.sendButton.disabled = false;
      }
    }

    async closeCurrentThread() {
      if (!this.activeThread || this.activeThread.status !== 'open') return;
      const confirmed = global.confirm('ဒီ Chat ကို ပိတ်မှာ သေချာပါသလား?');
      if (!confirmed) return;
      this.setBusy(true);
      try {
        await this.client.close('Closed from JACC app', this.activeThread.thread_id);
        this.activeThread.status = 'closed';
        this.renderConversationHeader();
        this.setComposerEnabled(false);
        this.showNotice('Chat ပိတ်ပြီးပါပြီ။', 'ok');
        await this.loadThreads();
      } catch (error) {
        this.showNotice(this.errorMessage(error), 'error');
      } finally {
        this.setBusy(false);
      }
    }

    showThreadList() {
      this.elements.shell.classList.remove('conversation-open');
    }

    setBusy(busy) {
      this.elements.openButton.disabled = Boolean(busy);
      this.elements.closeButton.disabled = Boolean(busy);
      this.elements.refreshButton.disabled = Boolean(busy || this.loadingThreads);
    }

    setComposerEnabled(enabled) {
      this.elements.textarea.disabled = !enabled;
      this.elements.sendButton.disabled = !enabled;
      this.elements.textarea.placeholder = enabled
        ? 'Message ရေးပါ…'
        : 'ဒီ Chat ကို ပိတ်ထားပြီးပါပြီ';
    }

    showNotice(message, type) {
      const notice = this.elements.notice;
      const text = String(message || '').trim();
      notice.textContent = text;
      notice.hidden = !text;
      notice.className = 'jacc-chat-notice' + (type ? ' ' + type : '');
    }

    errorMessage(error) {
      const code = String((error && (error.code || error.message)) || 'chat_request_failed')
        .trim()
        .toLowerCase();
      return ERROR_MESSAGES[code] || ('Chat error: ' + code.replace(/_/g, ' '));
    }

    formatCompactTime(value) {
      if (!value) return '—';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '—';
      const now = new Date();
      if (date.toDateString() === now.toDateString()) {
        return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' }).format(date);
      }
      return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' }).format(date);
    }

    formatMessageTime(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '';
      return new Intl.DateTimeFormat('en-GB', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
    }
  }

  let singleton = null;
  let initPromise = null;

  async function initChatUI() {
    if (singleton) {
      await singleton.setVisible(true);
      return singleton;
    }
    if (initPromise) return initPromise;
    initPromise = (async function () {
      const root = global.document && global.document.getElementById('tab-chat');
      if (!root) return null;
      try {
        const client = new global.JACCAppChatClient({
          apiBase: global.JACC_CHAT_API_BASE,
          pollMs: 3000,
        });
        singleton = new JACCAppChatUI(root, client);
        await singleton.setVisible(true);
        return singleton;
      } catch (error) {
        const notice = root.querySelector('#jacc-chat-notice');
        if (notice) {
          const code = String((error && (error.code || error.message)) || 'chat_request_failed').toLowerCase();
          notice.textContent = ERROR_MESSAGES[code] || 'Chat module မဖွင့်နိုင်ပါ။';
          notice.className = 'jacc-chat-notice error';
          notice.hidden = false;
        }
        return null;
      }
    })();
    return initPromise;
  }

  async function setChatVisible(visible) {
    if (visible) return initChatUI();
    if (singleton) await singleton.setVisible(false);
    return singleton;
  }

  global.JACCAppChatUI = JACCAppChatUI;
  global.JACCChatUIInit = initChatUI;
  global.JACCChatUISetVisible = setChatVisible;
})(window);
