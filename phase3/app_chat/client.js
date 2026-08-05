/* JACC Phase 3 in-app chat client — staged only.
 *
 * Requires the Phase 2 `JACCDeviceBinding` helper and a Railway API base URL.
 * This file never receives or stores Supabase credentials.
 */
(function (global) {
  'use strict';

  const DEFAULT_POLL_MS = 3000;
  const MIN_POLL_MS = 2000;
  const MAX_POLL_MS = 15000;
  const MAX_MESSAGE_CHARS = 4000;

  class JACCChatError extends Error {
    constructor(code, status) {
      super(code || 'chat_error');
      this.name = 'JACCChatError';
      this.code = code || 'chat_error';
      this.status = Number(status || 0);
    }
  }

  class JACCAppChatClient extends EventTarget {
    constructor(options) {
      super();
      const config = options || {};
      this.apiBase = String(
        config.apiBase || global.JACC_CHAT_API_BASE || ''
      ).trim().replace(/\/$/, '');
      this.storage = config.storage || global.localStorage;
      this.fetchImpl = config.fetchImpl || global.fetch.bind(global);
      this.pollMs = clamp(
        Number(config.pollMs || DEFAULT_POLL_MS),
        MIN_POLL_MS,
        MAX_POLL_MS
      );
      this.activeThreadId = '';
      this.pollTimer = null;
      this.polling = false;
      this.lastMessages = [];

      if (!this.apiBase) {
        throw new JACCChatError('chat_api_base_missing');
      }
      if (!global.JACCDeviceBinding) {
        throw new JACCChatError('device_binding_missing');
      }
    }

    authPayload() {
      const binding = global.JACCDeviceBinding;
      const session = binding.readSession(this.storage);
      if (!session || !session.token || !session.userId) {
        throw new JACCChatError('session_missing', 401);
      }
      return {
        token: String(session.token),
        userId: String(session.userId),
        deviceId: binding.getInstallationId(this.storage),
        app: binding.detectClientApp(),
      };
    }

    async post(path, fields) {
      const body = Object.assign({}, fields || {}, {
        auth: this.authPayload(),
      });
      let response;
      try {
        response = await this.fetchImpl(this.apiBase + path, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          credentials: 'omit',
          cache: 'no-store',
          body: JSON.stringify(body),
        });
      } catch (error) {
        throw new JACCChatError('chat_network_unavailable');
      }

      let result;
      try {
        result = await response.json();
      } catch (error) {
        throw new JACCChatError('chat_invalid_response', response.status);
      }
      if (!response.ok || !result || result.ok !== true) {
        const code = String(
          (result && result.error) || 'chat_request_failed'
        );
        if (response.status === 401) {
          try {
            global.JACCDeviceBinding.clearSession(this.storage);
          } catch (error) {
            // Session cleanup is best effort; the API rejection is authoritative.
          }
        }
        throw new JACCChatError(code, response.status);
      }
      return result;
    }

    async listThreads(limit) {
      const result = await this.post('/api/v1/chat/threads', {
        limit: clamp(Number(limit || 50), 1, 100),
      });
      return Array.isArray(result.threads) ? result.threads : [];
    }

    async openRequest(requestCode) {
      const code = String(requestCode || '').trim().toUpperCase();
      if (!/^[A-Z][A-Z0-9-]{3,31}$/.test(code)) {
        throw new JACCChatError('request_code_invalid');
      }
      const result = await this.post('/api/v1/chat/open', {
        requestCode: code,
      });
      const thread = result.thread || null;
      if (!thread || !thread.thread_id) {
        throw new JACCChatError('chat_thread_missing');
      }
      this.activeThreadId = String(thread.thread_id);
      this.dispatchEvent(new CustomEvent('threadopen', { detail: thread }));
      return thread;
    }

    async listMessages(threadId, options) {
      const config = options || {};
      const id = requiredUuid(threadId || this.activeThreadId, 'thread_id_invalid');
      const result = await this.post('/api/v1/chat/messages', {
        threadId: id,
        before: config.before || null,
        limit: clamp(Number(config.limit || 50), 1, 100),
      });
      const newestFirst = Array.isArray(result.messages)
        ? result.messages
        : [];
      const chronological = newestFirst.slice().reverse();
      this.lastMessages = chronological;
      this.dispatchEvent(new CustomEvent('messages', {
        detail: { threadId: id, messages: chronological },
      }));
      return chronological;
    }

    async sendText(body, options) {
      const config = options || {};
      const threadId = requiredUuid(
        config.threadId || this.activeThreadId,
        'thread_id_invalid'
      );
      const text = String(body || '').trim();
      if (!text || text.length > MAX_MESSAGE_CHARS) {
        throw new JACCChatError('message_length_invalid');
      }
      const clientMessageId = requiredUuid(
        config.clientMessageId || randomUuid(),
        'client_message_id_invalid'
      );
      const result = await this.post('/api/v1/chat/send', {
        threadId: threadId,
        clientMessageId: clientMessageId,
        body: text,
      });
      this.dispatchEvent(new CustomEvent('messagesent', {
        detail: result.message || null,
      }));
      return result.message || null;
    }

    async markRead(lastReadMessageId, threadId) {
      const id = requiredUuid(
        threadId || this.activeThreadId,
        'thread_id_invalid'
      );
      const messageId = lastReadMessageId
        ? requiredUuid(lastReadMessageId, 'last_read_message_id_invalid')
        : null;
      const result = await this.post('/api/v1/chat/read', {
        threadId: id,
        lastReadMessageId: messageId,
      });
      return Number(result.unreadCount || 0);
    }

    async close(reason, threadId) {
      const id = requiredUuid(
        threadId || this.activeThreadId,
        'thread_id_invalid'
      );
      const text = String(reason || '').trim();
      if (text.length > 500) {
        throw new JACCChatError('close_reason_too_long');
      }
      const result = await this.post('/api/v1/chat/close', {
        threadId: id,
        reason: text || null,
      });
      this.stopPolling();
      this.dispatchEvent(new CustomEvent('threadclosed', {
        detail: { threadId: id, status: result.status || 'closed' },
      }));
      return result.status || 'closed';
    }

    startPolling(threadId) {
      this.activeThreadId = requiredUuid(
        threadId || this.activeThreadId,
        'thread_id_invalid'
      );
      this.stopPolling();

      const tick = async () => {
        if (this.polling) return;
        if (global.document && global.document.hidden) return;
        this.polling = true;
        try {
          const messages = await this.listMessages(this.activeThreadId, {
            limit: 100,
          });
          const last = messages[messages.length - 1];
          if (last && last.message_id) {
            await this.markRead(last.message_id, this.activeThreadId);
          }
        } catch (error) {
          this.dispatchEvent(new CustomEvent('chaterror', { detail: error }));
        } finally {
          this.polling = false;
        }
      };

      tick();
      this.pollTimer = global.setInterval(tick, this.pollMs);
      return this.pollTimer;
    }

    stopPolling() {
      if (this.pollTimer) {
        global.clearInterval(this.pollTimer);
      }
      this.pollTimer = null;
      this.polling = false;
    }
  }

  function randomUuid() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') {
      return global.crypto.randomUUID();
    }
    if (!global.crypto || typeof global.crypto.getRandomValues !== 'function') {
      throw new JACCChatError('secure_random_unavailable');
    }
    const bytes = new Uint8Array(16);
    global.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, function (value) {
      return value.toString(16).padStart(2, '0');
    }).join('');
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20),
    ].join('-');
  }

  function requiredUuid(value, code) {
    const text = String(value || '').trim().toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(text)) {
      throw new JACCChatError(code || 'uuid_invalid');
    }
    return text;
  }

  function clamp(value, minimum, maximum) {
    if (!Number.isFinite(value)) return minimum;
    return Math.max(minimum, Math.min(maximum, value));
  }

  global.JACCChatError = JACCChatError;
  global.JACCAppChatClient = JACCAppChatClient;
})(window);
