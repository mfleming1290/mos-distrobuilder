# Build notes

MOS requires a built Vue page in the plugin `.deb`. The included GitHub Actions workflow performs that build with Node 22 and packages the frontend plus the bundled distrobuilder binary into an amd64 Debian package.

The source repository also needs `functions`, `packages`, and `staticfiles/` because MOS reads those from the plugin source archive during installation and persists them under `/boot/optional/plugins/distrobuilder/`.
