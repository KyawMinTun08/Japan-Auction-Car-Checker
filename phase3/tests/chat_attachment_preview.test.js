const assert = require('assert');
require('../chat_attachment_preview.js');
const api = globalThis.JACCChatAttachmentPreview;

assert.equal(api.normalizeAlt('  Auction photo  '), 'Auction photo');
assert.equal(api.normalizeAlt(''), 'Private chat photo');
assert.equal(api.assertPrivateUrl('blob:abc'), 'blob:abc');
assert.equal(api.assertPrivateUrl('https://example.test/object?token=abc&expires=60'), 'https://example.test/object?token=abc&expires=60');
assert.throws(() => api.assertPrivateUrl('http://example.test/object?token=abc'), /private_url_scheme_not_allowed/);
assert.throws(() => api.assertPrivateUrl('https://example.test/public/photo.jpg'), /private_url_not_short_lived/);
assert.equal(api.classifyReadError(new Error('403 forbidden')), 'denied');
assert.equal(api.classifyReadError(new Error('404 not_found')), 'missing');
assert.equal(api.classifyReadError(new Error('signed token expired')), 'expired');

(async () => {
  const ready = api.createAttachmentPreview({
    async createPrivateReadUrl(){ return 'https://cdn.example.test/photo?token=short&expires=60'; }
  });
  const r1 = await ready.resolve({bucket:'jacc-chat-attachments', path:'c/m/x.jpg', alt:'Broker photo'});
  assert.equal(r1.state, 'ready');
  assert.equal(r1.retryable, false);
  assert.equal(r1.alt, 'Broker photo');
  assert.ok(r1.url.includes('token='));

  const expired = api.createAttachmentPreview({
    async createPrivateReadUrl(){ throw new Error('signed token expired'); }
  });
  const r2 = await expired.resolve({bucket:'jacc-chat-attachments', path:'c/m/x.jpg'});
  assert.equal(r2.state, 'expired');
  assert.equal(r2.retryable, true);

  const denied = api.createAttachmentPreview({
    async createPrivateReadUrl(){ throw new Error('403 forbidden'); }
  });
  const r3 = await denied.resolve({bucket:'jacc-chat-attachments', path:'c/m/x.jpg'});
  assert.equal(r3.state, 'denied');
  assert.equal(r3.retryable, false);

  const missing = api.createAttachmentPreview({
    async createPrivateReadUrl(){ throw new Error('404 missing'); }
  });
  const r4 = await missing.resolve({bucket:'jacc-chat-attachments', path:'c/m/x.jpg'});
  assert.equal(r4.state, 'missing');
  assert.equal(r4.retryable, false);

  let refreshCount = 0;
  const refreshable = api.createAttachmentPreview({
    async createPrivateReadUrl(){
      refreshCount++;
      if (refreshCount === 1) throw new Error('token expired');
      return 'blob:refreshed-private-preview';
    }
  });
  assert.equal((await refreshable.resolve({bucket:'jacc-chat-attachments',path:'c/m/x.jpg'})).state, 'expired');
  assert.equal((await refreshable.refresh({bucket:'jacc-chat-attachments',path:'c/m/x.jpg'})).state, 'ready');

  const attrs = {};
  const img = {
    dataset:{},
    setAttribute(k,v){ attrs[k]=String(v); },
    removeAttribute(k){ if(k==='src') delete this.src; },
    set src(v){ this._src=v; },
    get src(){ return this._src; }
  };
  const bound = await ready.bindImage(img,{bucket:'jacc-chat-attachments',path:'c/m/x.jpg',alt:'Private auction image'});
  assert.equal(bound.state,'ready');
  assert.equal(attrs.alt,'Private auction image');
  assert.equal(attrs.tabindex,'0');
  assert.equal(attrs.loading,'lazy');
  assert.equal(img.dataset.previewState,'ready');
  assert.ok(img.src.includes('token='));

  console.log('JACC_CHAT_ATTACHMENT_PREVIEW_PASS');
})().catch(err => { console.error(err); process.exit(1); });
