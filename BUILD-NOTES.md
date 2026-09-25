# Build notes

MOS requires a built Vue page in the plugin `.deb`. The included GitHub Actions workflow performs that build with Node 22 and packages the frontend plus the small Distrobuilder controller into an amd64 Debian package.

The large Distrobuilder runtime binary is not part of this source repository or the plugin `.deb`. The controller downloads the pinned runtime manifest, checksum, and binary from `mfleming1290/mos-plugin-binaries`, verifies SHA-256, and stores the verified runtime under `/boot/optional/plugins/distrobuilder/bin/`.

The source repository also needs `functions`, `packages`, and `staticfiles/` because MOS reads those from the plugin source archive during installation and persists them under `/boot/optional/plugins/distrobuilder/`.


Successful builds now include a egistry.json manifest derived from the selected template. The merged SimpleStreams registry consumes that manifest so multiple GameServer releases (for example Debian Trixie and Arch Linux) can be published under the same gameserver distribution without registry-side hard-coding.
