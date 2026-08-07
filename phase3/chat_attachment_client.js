(() => {
  'use strict';

  const BUCKET = 'jacc-chat-attachments';
  const MAX_BYTES = 5 * 1024 * 1024;
  const MIME_TO_EXT = Object.freeze({
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp'
  });

  function assertUuid(value, label) {
    const v = String(value || '').toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(v)) {
      throw new Error(`${label || 'value'}_invalid_uuid`);
    }
    return v;
  }

  function validatePhoto(file) {
    if (!file) throw new Error('photo_required');
    if (!Object.prototype.hasOwnProperty.call(MIME_TO_EXT, file.type)) throw new Error('photo_mime_not_allowed');
    const size = Number(file.size || 0);
    if (!Number.isFinite(size) || size < 1) throw new Error('photo_empty');
    if (size > MAX_BYTES) throw new Error('photo_too_large');
    return { mime: file.type, size, ext: MIME_TO_EXT[file.type] };
  }

  function makeClientMessageId() {
    return globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function buildObjectPath(conversationId, messageId, clientMessageId, ext) {
    const conversation = assertUuid(conversationId, 'conversation');
    const message = assertUuid(messageId, 'message');
    const safeClient = String(clientMessageId || '').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 96);
    if (safeClient.length < 8) throw new Error('client_message_id_invalid');
    if (!['jpg', 'png', 'webp'].includes(ext)) throw new Error('photo_extension_not_allowed');
    return `${conversation}/${message}/${safeClient}.${ext}`;
  }

  function assertEntitlement(profile) {
    if (!profile || !profile.id) throw new Error('signed_in_profile_required');
    if (profile.account_active === false) throw new Error('account_inactive');
    const role = String(profile.role || '');
    if (role === 'customer') {
      if (String(profile.membership_status || '').toUpperCase() !== 'ACTIVE') throw new Error('membership_inactive');
      if (String(profile.service_channel || '').toLowerCase() !== 'app') throw new Error('app_membership_required');
      if (profile.expires_at && Date.parse(profile.expires_at) <= Date.now()) throw new Error('membership_expired');
    } else if (role === 'broker') {
      if (String(profile.broker_status || '').toLowerCase() !== 'active') throw new Error('broker_suspended');
    } else if (role !== 'admin') {
      throw new Error('role_not_allowed');
    }
    return true;
  }

  function createAttachmentClient(adapter) {
    if (!adapter || typeof adapter.createPhotoMessage !== 'function' || typeof adapter.uploadPrivateObject !== 'function' || typeof adapter.insertAttachmentMetadata !== 'function' || typeof adapter.createPrivateReadUrl !== 'function') {
      throw new Error('attachment_adapter_incomplete');
    }

    const inflight = new Map();

    async function sendPhoto({ file, conversationId, requestId, profile, onProgress, signal, clientMessageId }) {
      assertEntitlement(profile);
      const validated = validatePhoto(file);
      const cid = assertUuid(conversationId, 'conversation');
      const clientId = clientMessageId || makeClientMessageId();

      if (inflight.has(clientId)) return inflight.get(clientId);

      const task = (async () => {
        let objectPath = null;
        let message = null;
        try {
          if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError');
          onProgress && onProgress({ phase: 'message', percent: 10 });

          message = await adapter.createPhotoMessage({
            conversation_id: cid,
            request_id: requestId || null,
            sender_id: profile.id,
            sender_role: profile.role,
            message_type: 'photo',
            transport: 'app',
            client_message_id: clientId,
            status: 'sent'
          });

          const messageId = assertUuid(message && (message.id || message.message_id), 'message');
          objectPath = buildObjectPath(cid, messageId, clientId, validated.ext);

          onProgress && onProgress({ phase: 'upload', percent: 35 });
          await adapter.uploadPrivateObject({
            bucket: BUCKET,
            path: objectPath,
            file,
            contentType: validated.mime,
            cacheControl: '3600',
            upsert: false,
            signal,
            onProgress: value => onProgress && onProgress({ phase: 'upload', percent: Math.max(35, Math.min(85, Number(value) || 35)) })
          });

          if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError');
          onProgress && onProgress({ phase: 'metadata', percent: 90 });

          const attachment = await adapter.insertAttachmentMetadata({
            message_id: messageId,
            conversation_id: cid,
            storage_bucket: BUCKET,
            storage_path: objectPath,
            mime_type: validated.mime,
            byte_size: validated.size,
            original_name: String(file.name || '').slice(0, 255) || null
          });

          const privateUrl = await adapter.createPrivateReadUrl({ bucket: BUCKET, path: objectPath, expiresIn: 60 });
          onProgress && onProgress({ phase: 'done', percent: 100 });
          return { message, attachment, bucket: BUCKET, path: objectPath, privateUrl, clientMessageId: clientId };
        } catch (error) {
          if (objectPath && typeof adapter.removePrivateObject === 'function') {
            try { await adapter.removePrivateObject({ bucket: BUCKET, path: objectPath }); } catch (_) { /* best effort cleanup */ }
          }
          if (message && typeof adapter.markMessageFailed === 'function') {
            try { await adapter.markMessageFailed({ messageId: message.id || message.message_id, reason: String(error && error.message || error) }); } catch (_) { /* best effort */ }
          }
          throw error;
        } finally {
          inflight.delete(clientId);
        }
      })();

      inflight.set(clientId, task);
      return task;
    }

    return Object.freeze({ sendPhoto });
  }

  const api = Object.freeze({ BUCKET, MAX_BYTES, MIME_TO_EXT, validatePhoto, buildObjectPath, assertEntitlement, createAttachmentClient });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  globalThis.JACCChatAttachmentClient = api;
})();
