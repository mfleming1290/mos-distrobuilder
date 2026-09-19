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
      <h2>Persistent Storage</h2>
      <p class="muted">Keep templates, builds, cache, and logs off the MOS boot USB.</p>

      <div class="form-grid">
        <label><span>Template folder</span><input v-model.trim="settings.template_dir" type="text" /></label>
        <label><span>Build folder</span><input v-model.trim="settings.build_dir" type="text" /></label>
        <label><span>Cache folder</span><input v-model.trim="settings.cache_dir" type="text" /></label>
        <label><span>Log folder</span><input v-model.trim="settings.log_dir" type="text" /></label>
      </div>

      <div class="actions">
        <button class="primary" :disabled="storageBusy" @click="saveAndPrepareStorage">
          {{ storageBusy ? 'Saving...' : 'Save & Prepare Folders' }}
        </button>
      </div>
      <p v-if="storageMessage" :class="['message', storageFailed ? 'error' : 'ok']">{{ storageMessage }}</p>
    </div>

    <div class="card">
      <h2>LXC Template</h2>

      <div class="template-row">
        <label class="template-select">
          <span>YAML template</span>
          <select v-model="settings.selected_template" :disabled="templatesBusy || templates.length === 0">
            <option value="" disabled>Select a template</option>
            <option v-for="item in templates" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <button :disabled="templatesBusy" @click="loadTemplates">
          {{ templatesBusy ? 'Refreshing...' : 'Refresh Templates' }}
        </button>
      </div>

      <p v-if="templates.length === 0" class="hint">
        Drop <code>.yaml</code> or <code>.yml</code> files into the configured template folder, then refresh.
      </p>

      <div class="actions">
        <button :disabled="busy || !binaryInstalled || !settings.selected_template" @click="validateSelected">Validate</button>
        <button class="primary" :disabled="busy || !binaryInstalled || !settings.selected_template" @click="buildSelected">Build Image</button>
      </div>

      <p v-if="message" :class="['message', failed ? 'error' : 'ok']">{{ message }}</p>
      <p class="hint">Selected: <code>{{ selectedTemplatePath }}</code></p>
      <p class="hint">Builds: <code>{{ settings.build_dir }}</code></p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

const PLUGIN_NAME = 'distrobuilder';

const busy = ref(false);
const message = ref('');
const failed = ref(false);

const binaryBusy = ref(false);
const binaryInstalled = ref(false);
const binaryVersion = ref('');
const binarySha = ref('');
const binaryMessage = ref('');
const binaryFailed = ref(false);

const storageBusy = ref(false);
const storageMessage = ref('');
const storageFailed = ref(false);

const templatesBusy = ref(false);
const templates = ref([]);

const settings = reactive({
  template_dir: '/mnt/user/@storage/distrobuilder/templates',
  build_dir: '/mnt/user/@storage/distrobuilder/builds',
  cache_dir: '/mnt/user/@storage/distrobuilder/cache',
  log_dir: '/mnt/user/@storage/distrobuilder/logs',
  selected_template: '',
});

const selectedTemplatePath = computed(() => {
  if (!settings.template_dir || !settings.selected_template) return '';
  return settings.template_dir.replace(/\/$/, '') + '/' + settings.selected_template;
});

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

async function runFunction(functionName) {
  const res = await fetch('/api/v1/mos/plugins/executefunction', {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      plugin: PLUGIN_NAME,
      function: functionName,
    }),
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok || body?.success === false) {
    throw new Error(body?.error || body?.message || `HTTP ${res.status}`);
  }
  return body;
}

async function fetchSettings() {
  const res = await fetch(`/api/v1/mos/plugins/settings/${PLUGIN_NAME}`, {
    headers: getAuthHeaders(),
  });

  if (!res.ok) return;

  const data = await res.json();
  Object.assign(settings, {
    template_dir: data.template_dir || settings.template_dir,
    build_dir: data.build_dir || settings.build_dir,
    cache_dir: data.cache_dir || settings.cache_dir,
    log_dir: data.log_dir || settings.log_dir,
    selected_template: data.selected_template || '',
  });
}

async function saveSettings() {
  const res = await fetch(`/api/v1/mos/plugins/settings/${PLUGIN_NAME}`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...settings }),
  });

  if (!res.ok) {
    throw new Error(`Saving settings failed (${res.status})`);
  }
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

async function saveAndPrepareStorage() {
  storageBusy.value = true;
  storageFailed.value = false;
  storageMessage.value = '';
  try {
    await saveSettings();
    await runFunction('prepare_storage');
    storageMessage.value = 'Persistent folders are configured and ready.';
    await loadTemplates();
  } catch (err) {
    storageFailed.value = true;
    storageMessage.value = `Storage setup failed: ${err.message}`;
  } finally {
    storageBusy.value = false;
  }
}

async function loadTemplates() {
  templatesBusy.value = true;
  try {
    const body = await queryController(['list_templates'], 10, true);
    templates.value = Array.isArray(body?.output) ? body.output : [];

    if (settings.selected_template && !templates.value.includes(settings.selected_template)) {
      settings.selected_template = '';
    }

    if (!settings.selected_template && templates.value.includes('gameserver.yaml')) {
      settings.selected_template = 'gameserver.yaml';
    } else if (!settings.selected_template && templates.value.length === 1) {
      settings.selected_template = templates.value[0];
    }
  } catch (err) {
    templates.value = [];
    failed.value = true;
    message.value = `Could not list templates: ${err.message}`;
  } finally {
    templatesBusy.value = false;
  }
}

async function validateSelected() {
  busy.value = true;
  failed.value = false;
  message.value = 'Validating selected template...';
  try {
    await saveSettings();
    await runFunction('validate_selected');
    message.value = `${settings.selected_template} validated successfully.`;
  } catch (err) {
    failed.value = true;
    message.value = `Validation failed: ${err.message}`;
  } finally {
    busy.value = false;
  }
}

async function buildSelected() {
  busy.value = true;
  failed.value = false;
  message.value = `Building ${settings.selected_template}...`;
  try {
    await saveSettings();
    await runFunction('build_selected');
    message.value = `Build completed. Artifacts were written to ${settings.build_dir}.`;
  } catch (err) {
    failed.value = true;
    message.value = `Build failed: ${err.message}`;
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  await Promise.all([checkBinaryStatus(), fetchSettings()]);
  try {
    await runFunction('prepare_storage');
  } catch (_) {}
  await loadTemplates();
});
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

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.form-grid label,
.template-select {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
  font-weight: 600;
}

input,
select {
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  border: 1px solid rgba(128,128,128,.5);
  border-radius: 7px;
  padding: 10px 12px;
  background: transparent;
  color: inherit;
  font: inherit;
}

.template-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 12px;
  margin-top: 12px;
}

.template-select { min-width: 0; }
.template-row button { height: 42px; }
code { word-break: break-all; }

@media (max-width: 760px) {
  .form-grid { grid-template-columns: 1fr; }
  .template-row { grid-template-columns: 1fr; }
  .template-row button { width: 100%; }
}</style>
