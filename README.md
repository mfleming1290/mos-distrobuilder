# MOS Distrobuilder Plugin (starter)

Minimal MOS plugin for building LXC images with a bundled amd64 `distrobuilder` binary.

## Included

- Bundled Linux amd64 `distrobuilder` binary
- `staticfiles/definitions/gameserver.yaml`
- MOS plugin functions to validate/build the GameServer image
- Basic Vue plugin page
- `packages` list for Debian/LXC build dependencies
- GitHub Actions workflow that creates the installable MOS `.deb`
- Example MOS Hub plugin template

## First test

1. Push this folder to a GitHub repository.
2. In Repository Settings > Actions > General, enable **Read and write permissions**.
3. Run the **Build and Release** workflow with version `0.1.0`, or push tag `0.1.0`.
4. Point your MOS Hub plugin JSON at that repository and install release `0.1.0`.
5. Open **Plugins > Distrobuilder**.
6. Click **Validate**.
7. Click **Build Image**.

Persistent outputs:

- Builds: `/boot/optional/plugins/distrobuilder/builds/`
- Logs: `/boot/optional/plugins/distrobuilder/logs/`
- Cache: `/boot/optional/plugins/distrobuilder/cache/`
- Definition: `/boot/optional/plugins/distrobuilder/staticfiles/definitions/gameserver.yaml`

## Scope of v0.1.0

This is intentionally only the image-builder half of the eventual workflow. It builds LXC image artifacts but does **not** yet publish a SimpleStreams registry or automatically add the image to the MOS LXC creation dropdown.

## Bundled binary

`bin/distrobuilder` is the user-provided Linux amd64 binary that was already tested on a Linux GameServer LXC.
