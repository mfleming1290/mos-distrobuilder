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
- `staticfiles/definitions/gameserver-wine.yaml` (Debian Trixie + Wine; publishes as `gameserver/trixie-wine`)
- Dedicated `LXC Provisioning` card with preflight preview, static IP, shared mounts, and optional autostart
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

## GameServer image releases

The existing Debian and Arch templates remain selectable. The new
`gameserver-wine.yaml` builds **Debian Trixie** and adds Wine and Winbind;
the source comments `# mos-registry-product: gameserver` and
`# mos-registry-release: trixie-wine` control the *published* SimpleStreams
identity. Do not change `image.release` to `trixie-wine`: debootstrap
needs Debian's actual `trixie` release.

The Wine image also prepares a `steam` UID/GID 1000 account, SteamCMD,
`/home/steam/.local/bin` PATH and the blank v2 gameserver configuration.
Per-game Steam App IDs, passwords, runtime services, and Tailscale
authentication are supplied later by Flow/manual setup.

## LXC Provisioning (new in 0.1.11)

The plugin's new **LXC Provisioning** panel creates a container from a
completed local build *without using the MOS create dialog*.

1. Build `gameserver.yaml` or `gameserver-wine.yaml` using the image builder.
2. Open LXC Provisioning and refresh the published images and physical NICs.
3. Enter a unique lowercase container name, dedicated IPv4 CIDR,
   gateway, bootstrap DNS, existing gameserver catalogue root and binary folder.
4. Preview the generated `lxc-create` command and LXC config.
5. Reserve the IP in your router and confirm it in the UI, then create.
6. The guest is created with static macvlan networking, one shared
   **read-write** game catalogue mount at /srv/gameserver, an optional read-only
   binary mount and Tailscale TUN. The provisioner also creates the game's
   directory under the catalogue with UID/GID 1000 ownership. Autostart and
   immediate start are independently configurable. All privileged LXCs with
   this mount can modify other games' files; maintain independent backups.

The controller's Python helper is packaged as
`/usr/bin/plugins/distrobuilder-provision`, and it exposes
`info`, `plan`, and `create` to the existing MOS plugin query API.

**Preflight is non-destructive.** It rejects existing LXC names,
nonexistent mount roots, invalid NIC/IP/gateway, unknown local image builds,
and discovered host/LXC/Docker IP conflicts. Router-side DHCP reservations
and silent static devices cannot be fully detected automatically, hence the
explicit operator confirmation.

A failed `lxc-create` or guest startup retains partial state for inspection.
The helper does not delete existing containers, images, or game data.
Bootstrap DNS is written into the new guest before initial startup. Each
new container still needs Tailscale login and its game-specific Flow workflow.
The provisioner currently targets MOS's privileged LXC layout under
`/var/lib/lxc` and amd64 images.

## Verification

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile provision-lxc.py
bash -n functions
bash -n distrobuilder
cd page
npm ci --no-audit --no-fund
npm run build
```

After installing from MOS Hub, validate/build an image, preview one LXC
plan, then create a disposable test container. A desktop build and mocked
unit tests alone do **not** prove live MOS/LXC provisioning or registry
publication. Do not use production saves for the first migration test.