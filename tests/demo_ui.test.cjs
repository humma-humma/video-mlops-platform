const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

class Element {
  constructor() { this.value = ''; this.textContent = ''; this.children = []; this.handlers = {}; this.files = []; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren() { this.children = []; }
  set innerHTML(_) { throw new Error('Unsafe HTML rendering'); }
}
const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(setImmediate); };
function harness(handler) {
  const elements = new Map(), requests = [], timers = [];
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const context = vm.createContext({
    document: {getElementById: get, createElement: () => new Element()},
    window: {addEventListener() {}}, Headers, AbortSignal, crypto: webcrypto,
    FormData: class { constructor() { this.fields = []; } append(...v) { this.fields.push(v); } },
    setTimeout: fn => { timers.push(fn); return timers.length; }, clearTimeout() {},
    fetch: async (path, options) => {
      requests.push({path, options});
      let data = path === '/health/ready' ? {status:'ok', database:'ok', queue:'ok', storage:'ok'} : [];
      const custom = await handler(path, options);
      if (custom !== undefined) data = custom;
      return {ok: !data.httpError, status: data.httpError || 200, json: async () => data, text: async () => String(data)};
    }
  });
  vm.runInContext(fs.readFileSync('src/service/static/demo.js', 'utf8'), context);
  return {context, get, requests, timers};
}
const one = '11111111-1111-4111-8111-111111111111';
const two = '22222222-2222-4222-8222-222222222222';

test('opens the newest persisted job without submitting another video', async () => {
  const h = harness(async path => {
    if (path === '/api/v1/jobs?limit=12') return [{job_id:one, status:'SUCCEEDED'}];
    if (path === `/api/v1/jobs/${one}`) return {status:'SUCCEEDED', result:{model_version:'real', summary:'saved result', category:'Demo'}};
    if (path.endsWith('/events') || path.endsWith('/attempts')) return [];
  });
  await settle();
  assert.equal(h.get('selected-id').textContent, one);
  assert.equal(h.get('summary').textContent, 'saved result');
  assert.equal(h.requests.filter(r => r.options.method === 'POST').length, 0);
});

test('renders fake result explicitly and treats generated HTML as text', async () => {
  const h = harness(async path => {
    if (path.endsWith('/events') || path.endsWith('/attempts')) return [];
    if (path === `/api/v1/jobs/${one}`) return {status:'SUCCEEDED', result:{model_version:'fake', summary:'<img onerror=alert(1)>', category:'News', timings:{total:1}}};
  });
  await settle(); h.context.selectJob(one); await settle();
  assert.equal(h.get('health').textContent, 'Service ready');
  assert.equal(h.get('result-mode').textContent, 'SIMULATED · fake worker');
  assert.equal(h.get('summary').textContent, '<img onerror=alert(1)>');
  assert.equal(h.get('result').hidden, false);
  assert.equal(h.get('cancel').disabled, true);
  assert.equal(h.timers.length, 0);
});

test('a late response cannot replace the newly selected job', async () => {
  let release;
  const h = harness(async path => {
    if (path.endsWith('/events') || path.endsWith('/attempts')) return [];
    if (path === `/api/v1/jobs/${one}`) return new Promise(resolve => { release = resolve; });
    if (path === `/api/v1/jobs/${two}`) return {status:'SUCCEEDED', result:{model_version:'real', summary:'new result'}};
  });
  await settle(); h.context.selectJob(one); await settle();
  h.context.selectJob(two); await settle();
  release({status:'SUCCEEDED', result:{summary:'stale result'}}); await settle();
  assert.equal(h.get('selected-id').textContent, two);
  assert.equal(h.get('summary').textContent, 'new result');
});

test('upload forwards in-memory authentication and idempotency, then polls accepted job', async () => {
  const h = harness(async (path, options) => {
    if (path === '/api/v1/jobs' && options.method === 'POST') return {job_id:one};
    if (path === `/api/v1/jobs/${one}`) return {status:'QUEUED'};
    if (path.endsWith('/events') || path.endsWith('/attempts')) return [];
  });
  await settle(); h.get('api-key').value = 'test-only-key'; h.get('video').files = [{size:10}];
  await h.get('submit-form').handlers.submit({preventDefault(){}}); await settle();
  const post = h.requests.find(r => r.options.method === 'POST');
  assert.equal(post.options.headers.get('X-API-Key'), 'test-only-key');
  assert.match(post.options.headers.get('Idempotency-Key'), /^[0-9a-f-]{36}$/);
  assert.equal(h.get('job-status').textContent, 'QUEUED');
  assert.equal(h.get('cancel').disabled, false);
  assert.equal(h.timers.length, 1);
});

test('uncertain upload failure explains reconciliation instead of auto-resubmitting', async () => {
  const h = harness(async (path, options) => options.method === 'POST' ? {httpError:503, detail:'Storage unavailable'} : undefined);
  await settle(); h.get('video').files = [{size:10}];
  await h.get('submit-form').handlers.submit({preventDefault(){}}); await settle();
  assert.match(h.get('message').textContent, /Check Recent jobs before submitting again/);
  assert.equal(h.requests.filter(r => r.options.method === 'POST').length, 1);
  assert.equal(h.get('submit').disabled, false);
});
