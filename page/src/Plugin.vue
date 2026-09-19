<template>
  <div class="wrap">
    <h1>Distrobuilder</h1>
    <p class="sub">Build custom LXC images on MOS. The plugin downloads and verifies the Distrobuilder runtime separately from the plugin source.</p>

    <div class="card binary-card">
      <div class="card-head">
        <div>
          <h2>Distrobuilder Runtime</h2>
          <p class="muted">Runtime binary is stored persistently under <code>/boot/optional/plugins/distrobuilder/bin/</code> and deployed executable to <code>/usr/bin/distrobuilder-real</code>.</p>
        </div>
        <span :class="['status', binaryInstalled ? 'ok-pill' : 'warn-pill']">
          {{ binaryInstalled ? `Installed${binaryVersion ? ` · ${binaryVersion}` : ''}` : 'Not installed' }}
        </span>
      </div>

      <div class="actions">
        <button class="primary" :disabled="binaryBusy" @click="installBinary">
          {{ binaryBusy ? 'Installing…' : (binaryInstalled ? 'Repair Binary' : 'Install Binary') }}
        </button>
        <button :disabled="binaryBusy" @click="checkBinaryStatus">Refresh Status</button>
      </div>

      <p v-if="binaryMessage" :class="['message', binaryFailed ? 'error' : 'ok']">{{ binaryMessage }}</p>
      <p v-if="binarySha" class="hash"><strong>SHA-256:</strong> <code>{{ binarySha }}</code></p>
    </div>

    <div class="card">
      <h2>GameServer LXC</h2>
      <div class="grid">
        <div><strong>Distribution</strong><span>Debian</span></div>
        <div><strong>Release</strong><span>Trixie</span></div>
        <div><strong>Architecture</strong><span>amd64</span></div>
        <div><strong>Definition</strong><span>gameserver.yaml</span></div>
      </div>

      <div class="actions">
        <button :disabled="busy || !binaryInstalled" @click="run('validate_gameserver', 'Validate GameServer definition')">Validate</button>
        <button class="primary" :disabled="busy || !binaryInstalled" @click="run('build_gameserver', 'Build GameServer LXC image')">Build Image</button>
        <button :disabled="busy" @click="run('clean_cache', 'Clean Distrobuilder cache')">Clean Cache</button>
      </div>

      <p v-if="message" :class="['message', failed ? 'error' : 'ok']">{{ message }}</p>
      <p class="hint">Build artifacts are stored persistently under <code>/boot/optional/plugins/distrobuilder/builds/</code>. Logs are under <code>/boot/optional/plugins/distrobuilder/logs/</code>.</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';

const busy = ref(false);
const message = ref('');
const failed = ref(false);
const binaryBusy = ref(false);
const binaryInstalled = ref(false);
const binaryVersion = ref('');
const binarySha = ref('');
const binaryMessage = ref('');
const binaryFailed = ref(false);

const getAuthHeaders = () => ({
  Authorization: 'Bearer ' + localStorage.getItem('authToken'),
});

async function queryController(args, timeout = 30, parseJson = false) {
  const res = await fetch('/api/v1/mos/plugins/query', {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      command: 'distrobuilder',
      args,
      timeout,
      parse_json: parseJson,
    }),
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok || body?.success === false) {
    throw new Error(body?.error || body?.message || `HTTP ${res.status}`);
  }
  return body;
}

async function checkBinaryStatus() {
  try {
    const body = await queryController(['status'], 10, true);
    const status = body?.output || {};
    binaryInstalled.value = status.installed === true;
    binaryVersion.value = status.version || '';
    binarySha.value = status.sha256 || '';
  } catch (err) {
    binaryInstalled.value = false;
    binaryVersion.value = '';
    binarySha.value = '';
    binaryFailed.value = true;
    binaryMessage.value = `Could not read binary status: ${err.message}`;
  }
}

async function installBinary() {
  binaryBusy.value = true;
  binaryFailed.value = false;
  binaryMessage.value = 'Downloading and verifying Distrobuilder…';
  try {
    await queryController(['install_binary'], 120, false);
    await checkBinaryStatus();
    binaryMessage.value = binaryInstalled.value
      ? `Distrobuilder ${binaryVersion.value || ''} installed and verified.`
      : 'Binary install completed, but status could not confirm the runtime.';
    binaryFailed.value = !binaryInstalled.value;
  } catch (err) {
    binaryFailed.value = true;
    binaryMessage.value = `Binary install failed: ${err.message}`;
  } finally {
    binaryBusy.value = false;
  }
}

async function run(fn, displayName) {
  busy.value = true;
  failed.value = false;
  message.value = `${displayName} started...`;
  try {
    const res = await fetch('/api/v1/mos/plugins/executefunction', {
      method: 'POST',
      headers: {
        ...getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ plugin: 'distrobuilder', function: fn, displayName }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body?.error || body?.message || `HTTP ${res.status}`);
    message.value = `${displayName} completed successfully.`;
  } catch (err) {
    failed.value = true;
    message.value = `${displayName} failed: ${err.message}`;
  } finally {
    busy.value = false;
  }
}

onMounted(checkBinaryStatus);
</script>

<style scoped>
.wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
h1 { margin: 0 0 4px; font-size: 30px; }
.sub { opacity: .75; margin-bottom: 22px; }
.card { border: 1px solid rgba(128,128,128,.35); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.binary-card h2 { margin-bottom: 6px; }
.muted { opacity: .72; margin: 0; }
.status { padding: 5px 9px; border-radius: 999px; font-size: .85rem; white-space: nowrap; }
.ok-pill { background: rgba(80,160,100,.18); }
.warn-pill { background: rgba(210,150,50,.18); }
h2 { margin-top: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; margin: 18px 0; }
.grid div { display: flex; flex-direction: column; gap: 3px; }
.grid span { opacity: .75; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
button { border: 1px solid rgba(128,128,128,.5); border-radius: 7px; padding: 9px 14px; cursor: pointer; background: transparent; color: inherit; }
button.primary { font-weight: 700; }
button:disabled { opacity: .5; cursor: wait; }
.message { padding: 10px 12px; border-radius: 6px; }
.ok { background: rgba(80,160,100,.12); }
.error { background: rgba(190,70,70,.14); }
.hint { opacity: .72; font-size: .92rem; }
.hash { opacity: .75; font-size: .88rem; }
code { word-break: break-all; }
</style>