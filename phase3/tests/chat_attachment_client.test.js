const assert = require('assert');
require('../chat_attachment_client.js');
const api = globalThis.JACCChatAttachmentClient;

function file(type, size, name='photo.jpg') { return { type, size, name }; }

assert.equal(api.validatePhoto(file('image/jpeg', 1024)).ext, 'jpg');
assert.equal(api.validatePhoto(file('image/png', 1024, 'x.png')).ext, 'png');
assert.equal(api.validatePhoto(file('image/webp', 1024, 'x.webp')).ext, 'webp');
assert.throws(() => api.validatePhoto(file('application/pdf', 1)), /photo_mime_not_allowed/);
assert.throws(() => api.validatePhoto(file('image/jpeg', 0)), /photo_empty/);
assert.throws(() => api.validatePhoto(file('image/jpeg', api.MAX_BYTES + 1)), /photo_too_large/);

const CID = '11111111-1111-4111-8111-111111111111';
const MID = '22222222-2222-4222-8222-222222222222';
const path = api.buildObjectPath(CID, MID, 'client_msg_12345678', 'jpg');
assert.equal(path, `${CID}/${MID}/client_msg_12345678.jpg`);
assert.throws(() => api.buildObjectPath(CID, MID, 'short', 'jpg'), /client_message_id_invalid/);
assert.throws(() => api.buildObjectPath(CID, MID, 'client_msg_12345678', 'pdf'), /photo_extension_not_allowed/);

const activeCustomer = { id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', role:'customer', account_active:true, membership_status:'ACTIVE', service_channel:'app', expires_at:'2099-01-01T00:00:00Z' };
assert.equal(api.assertEntitlement(activeCustomer), true);
assert.throws(() => api.assertEntitlement({...activeCustomer, membership_status:'EXPIRED'}), /membership_inactive/);
assert.throws(() => api.assertEntitlement({...activeCustomer, service_channel:'telegram'}), /app_membership_required/);
assert.equal(api.assertEntitlement({id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',role:'broker',account_active:true,broker_status:'active'}), true);
assert.throws(() => api.assertEntitlement({id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',role:'broker',account_active:true,broker_status:'suspended'}), /broker_suspended/);

(async () => {
  const calls = [];
  const adapter = {
    async createPhotoMessage(payload) { calls.push(['message', payload]); return { id: MID, ...payload }; },
    async uploadPrivateObject(payload) { calls.push(['upload', payload]); payload.onProgress && payload.onProgress(70); },
    async insertAttachmentMetadata(payload) { calls.push(['metadata', payload]); return { id:'33333333-3333-4333-8333-333333333333', ...payload }; },
    async createPrivateReadUrl(payload) { calls.push(['read', payload]); return 'blob:private-preview'; },
    async removePrivateObject(payload) { calls.push(['cleanup', payload]); },
    async markMessageFailed(payload) { calls.push(['failed', payload]); }
  };
  const client = api.createAttachmentClient(adapter);
  const progress = [];
  const result = await client.sendPhoto({ file:file('image/jpeg', 2048), conversationId:CID, requestId:'f1111111-1111-4111-8111-111111111111', profile:activeCustomer, clientMessageId:'client_msg_12345678', onProgress:p=>progress.push(p) });
  assert.equal(result.bucket, 'jacc-chat-attachments');
  assert.equal(result.path, `${CID}/${MID}/client_msg_12345678.jpg`);
  assert.equal(result.privateUrl, 'blob:private-preview');
  assert.deepEqual(calls.map(x=>x[0]).slice(0,4), ['message','upload','metadata','read']);
  assert.equal(calls[1][1].upsert, false);
  assert.equal(calls[2][1].storage_path, result.path);
  assert.equal(calls[2][1].storage_bucket, 'jacc-chat-attachments');
  assert.ok(progress.some(p=>p.phase==='done' && p.percent===100));

  let uploadCount = 0;
  let release;
  const wait = new Promise(r=>release=r);
  const dedupeClient = api.createAttachmentClient({
    async createPhotoMessage(payload){ return {id:MID,...payload}; },
    async uploadPrivateObject(){ uploadCount++; await wait; },
    async insertAttachmentMetadata(payload){ return payload; },
    async createPrivateReadUrl(){ return 'blob:private'; }
  });
  const args = { file:file('image/png', 100), conversationId:CID, profile:activeCustomer, clientMessageId:'same_client_1234' };
  const p1 = dedupeClient.sendPhoto(args);
  const p2 = dedupeClient.sendPhoto(args);
  release();
  await Promise.all([p1,p2]);
  assert.equal(uploadCount, 1, 'same client_message_id must deduplicate in-flight retry');

  const failCalls=[];
  const failClient = api.createAttachmentClient({
    async createPhotoMessage(payload){ return {id:MID,...payload}; },
    async uploadPrivateObject(){ throw new Error('network_failed'); },
    async insertAttachmentMetadata(){ throw new Error('should_not_run'); },
    async createPrivateReadUrl(){ throw new Error('should_not_run'); },
    async removePrivateObject(p){ failCalls.push(['cleanup',p]); },
    async markMessageFailed(p){ failCalls.push(['failed',p]); }
  });
  await assert.rejects(() => failClient.sendPhoto({file:file('image/webp',100),conversationId:CID,profile:activeCustomer,clientMessageId:'retry_client_1234'}), /network_failed/);
  assert.deepEqual(failCalls.map(x=>x[0]), ['cleanup','failed']);

  console.log('JACC_CHAT_ATTACHMENT_CLIENT_PASS');
})().catch(err => { console.error(err); process.exit(1); });
