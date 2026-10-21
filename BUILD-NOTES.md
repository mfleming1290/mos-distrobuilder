# Build notes

MOS requires a built Vue page in the plugin `.deb`. The included GitHub Actions workflow performs that build with Node 22 and packages the frontend plus the small Distrobuilder controller into an amd64 Debian package.

The large Distrobuilder runtime binary is not part of this source repository or the plugin `.deb`. The controller downloads the pinned runtime manifest, checksum, and binary from `mfleming1290/mos-plugin-binaries`, verifies SHA-256, and stores the verified runtime under `/boot/optional/plugins/distrobuilder/bin/`.

The source repository also needs `functions`, `packages`, and `staticfiles/` because MOS reads those from the plugin source archive during installation and persists them under `/boot/optional/plugins/distrobuilder/`.

For 0.1.11 the GitHub workflow must also package `provision-lxc.py`
as `/usr/bin/plugins/distrobuilder-provision`; the MOS controller
dispatches `provision_info`, `provision_plan`, and `provision_create`
to that helper. The source `packages` list now requires Python 3 and
iproute2. CI runs the offline provisioning tests, shell syntax checks,
and checks that `gameserver-wine.yaml` maps to
`gameserver/trixie-wine` before packaging or publishing.

After installing the plugin from MOS Hub, select and build the new Wine
image in Distrobuilder. The image build is a distinct action from
releasing/updating the plugin and must be verified separately on MOS.


Successful builds now include a `registry.json` manifest derived from the selected template. The merged SimpleStreams registry consumes that manifest so multiple GameServer releases (for example Debian Trixie and Arch Linux) can be published under the same gameserver distribution without registry-side hard-coding.
