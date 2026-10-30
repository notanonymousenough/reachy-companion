// Local browser contract: real page script, bounded fake DOM, no network/devices.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const page = fs.readFileSync(__dirname + '/../src/reachy_companion/control_page.py', 'utf8');
const script = page.split('<script>')[1].split('</script>')[0];
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  const elements = new Map(), calls = [];
  const element = id => {
    if (!elements.has(id)) elements.set(id, {textContent: '', className: '', disabled: false,
      hidden: false, value: '', select() {}, setAttribute(k, v) {this[k] = v;}});
    return elements.get(id);
  };
  const state = {version: 1, binding: {agent_boot_id: 'boot', microphone_epoch: 1,
    policy_epoch: 1, intent_generation: 0, schedule_generation: 0, owner_id: null},
    microphone: {enabled: false, listening: false, capture_active: false, error: false, closed: true},
    automatic: {enabled: false, requested: false, state: 'OFF'},
    policy: {motor_enabled: false, quiet: false, privacy_all: false,
      microphone_owner_id: null, motion_policy_owner_id: null},
    volume: {percent: 70, enabled: true},
    conversation_mode: {version: 1, mode: 'normal', generation: 3, error: null}, phase: 'paused'};
  let respond = async () => ({ok: true, status: 200, json: async () => structuredClone(state)});
  const context = vm.createContext({document: {getElementById: element},
    sessionStorage: {getItem: () => 'fixture-only', setItem() {}, removeItem() {}},
    location: {hash: '', pathname: '/control', origin: 'http://fixture.invalid'},
    history: {replaceState() {}}, AbortController, setTimeout, clearTimeout, setInterval() {},
    Date, Number, Error, JSON, encodeURIComponent, decodeURIComponent,
    fetch: async (path, options) => {calls.push({path, options}); return respond(path, options);}});
  vm.runInContext(script, context);
  return {state, calls, element, run: code => vm.runInContext(code, context),
    set respond(value) {respond = value;}};
}

(async () => {
  let f = fixture(); await flush();
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].options.method, 'GET');
  assert.equal(f.element('mode-state').textContent, 'Обычный');
  assert.equal(f.element('mode-normal').disabled, true);
  assert.equal(f.element('mode-alice').disabled, false); // Works with MIC OFF; no opt-in.
  f.respond = async (path, options) => ({ok: true, status: 200, json: async () => {
    if (options.method === 'POST') {
      f.state.conversation_mode = {version: 1, mode: 'alice_test', generation: 4, error: null};
      return {accepted: true, action: JSON.parse(options.body).action, state: f.state};
    }
    return f.state;
  }});
  await f.element('mode-alice').onclick();
  const post = f.calls.filter(c => c.options.method === 'POST');
  assert.equal(post.length, 1);
  assert.deepEqual(JSON.parse(post[0].options.body), {action: 'mode_alice_test',
    binding: f.state.binding, mode_generation: 3});
  assert.equal(f.element('mode-state').textContent, 'Тест с Алисой');
  assert.equal(f.run('state.microphone.enabled'), false);
  assert.equal(f.run('state.automatic.requested'), false);

  f = fixture(); await flush();
  for (const code of ['state.policy.privacy_all=true', 'state.policy.quiet=true',
    'state.policy.microphone_owner_id="foreign"', 'state.policy.motion_policy_owner_id="foreign"']) {
    f.run(code + ';render()');
    assert.equal(f.element('mode-normal').disabled, true);
    assert.equal(f.element('mode-alice').disabled, true);
    assert.equal(f.element('stop').disabled, false);
  }

  f = fixture(); await flush();
  f.respond = async () => {throw Error('offline');};
  await f.run('refresh()');
  assert.equal(f.element('mode-state').textContent, 'Неизвестно');
  assert.equal(f.element('mode-alice').disabled, true);
  assert.equal(f.element('stop').disabled, false);

  f = fixture(); await flush();
  let release;
  f.respond = async (path, options) => {
    if (options.method === 'GET') return {ok: true, status: 200, json: async () => f.state};
    const action = JSON.parse(options.body).action;
    if (action === 'mode_alice_test') return new Promise(resolve => {
      release = () => resolve({ok: true, status: 200, json: async () => ({accepted: true,
        action, state: {...f.state, conversation_mode: {...f.state.conversation_mode, mode: 'alice_test'}}})});
    });
    return {ok: true, status: 200, json: async () => ({accepted: true, action, state: f.state})};
  };
  const pending = f.run("command('mode_alice_test')"); await flush();
  assert.equal(f.element('stop').disabled, false);
  await f.run("command('stop')");
  release(); await pending;
  assert.equal(f.element('mode-state').textContent, 'Обычный');
  assert.equal(f.run('state.microphone.enabled'), false);
  assert.deepEqual(f.calls.filter(c => c.options.method === 'POST').map(c => JSON.parse(c.options.body).action),
    ['mode_alice_test', 'stop']);
  process.stdout.write('PASS: mode render, explicit bound command, MIC OFF, privacy/owners, offline, concurrent STOP\n');
})().catch(error => {console.error(error); process.exitCode = 1;});
