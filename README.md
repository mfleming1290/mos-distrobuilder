# MOS Distrobuilder Plugin

MOS plugin for building LXC images with Distrobuilder.

## Runtime binary model

The large Distrobuilder executable is intentionally **not stored in this plugin repository**.

The installed plugin contains a small MOS-safe controller at:

`/usr/bin/plugins/distrobuilder`

That controller downloads the pinned binary manifest from:

`https://raw.githubusercontent.com/mfleming1290/mos-plugin-binaries/main/distrobuilder/3.3.1/linux-amd64/distrobuilder.json`

The controller then:

1. Downloads the Distrobuilder binary from the manifest URL.
2. Verifies its SHA-256 against the manifest.
3. Stores the verified binary persistently at:
   `/boot/optional/plugins/distrobuilder/bin/distrobuilder`
4. Stores a copy of the binary manifest beside it.

The plugin UI can install or repair the runtime binary at any time.

## Included

- Small Distrobuilder controller script for MOS
- SHA-256 verified runtime download
- `staticfiles/definitions/gameserver.yaml` (Debian Trixie)
- `staticfiles/definitions/gameserver-arch.yaml` (Arch Linux)
- MOS plugin functions to validate/build GameServer images and emit `registry.json` SimpleStreams metadata
- Vue plugin page with runtime status/install controls
- Runtime package dependencies
- GitHub Actions workflow that creates the installable MOS `.deb`
- Example MOS Hub plugin template

## First test

1. Build and release the plugin.
2. Install it from MOS Hub.
3. Open **Plugins > Distrobuilder**.
4. Confirm the runtime reports **Installed**.
5. Click **Validate**.
6. Click **Build Image**.

If automatic runtime installation failed during plugin installation, use **Install Binary** in the UI.

## Persistent paths

- Runtime: `/boot/optional/plugins/distrobuilder/bin/distrobuilder`
- Runtime manifest: `/boot/optional/plugins/distrobuilder/bin/distrobuilder.json`
- Builds: `/boot/optional/plugins/distrobuilder/builds/`
- Logs: `/boot/optional/plugins/distrobuilder/logs/`
- Cache: `/boot/optional/plugins/distrobuilder/cache/`
- Debian definition: `/boot/optional/plugins/distrobuilder/staticfiles/definitions/gameserver.yaml`
- Arch definition: `/boot/optional/plugins/distrobuilder/staticfiles/definitions/gameserver-arch.yaml`

## Scope

The plugin builds LXC image artifacts and emits a `registry.json` manifest beside each successful build. A separate merged SimpleStreams registry can consume those manifests and expose the builds in the MOS LXC creation dropdown.