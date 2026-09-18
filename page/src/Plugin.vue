<template>
  <div class="wrap">
    <h1>Distrobuilder</h1>
    <p class="sub">Build custom LXC images on MOS. This starter ships with the Generic SteamCMD GameServer definition.</p>

    <div class="card">
      <h2>GameServer LXC</h2>
      <div class="grid">
        <div><strong>Distribution</strong><span>Debian</span></div>
        <div><strong>Release</strong><span>Trixie</span></div>
        <div><strong>Architecture</strong><span>amd64</span></div>
        <div><strong>Definition</strong><span>gameserver.yaml</span></div>
      </div>

      <div class="actions">
        <button :disabled="busy" @click="run('validate_gameserver', 'Validate GameServer definition')">Validate</button>
        <button class="primary" :disabled="busy" @click="run('build_gameserver', 'Build GameServer LXC image')">Build Image</button>
        <button :disabled="busy" @click="run('clean_cache', 'Clean Distrobuilder cache')">Clean Cache</button>
      </div>

      <p v-if="message" :class="['message', failed ? 'error' : 'ok']">{{ message }}</p>
      <p class="hint">Build artifacts are stored persistently under <code>/boot/optional/plugins/distrobuilder/builds/</code>. Logs are under <code>/boot/optional/plugins/distrobuilder/logs/</code>.</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const busy = ref(false);
const message = ref('');
const failed = ref(false);

async function run(fn, displayName) {
  busy.value = true;
  failed.value = false;
  message.value = `${displayName} started...`;
  try {
    const res = await fetch('/api/v1/mos/plugins/executefunction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
</script>

<style scoped>
.wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
h1 { margin: 0 0 4px; font-size: 30px; }
.sub { opacity: .75; margin-bottom: 22px; }
.card { border: 1px solid rgba(128,128,128,.35); border-radius: 12px; padding: 20px; }
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
code { word-break: break-all; }
</style>
