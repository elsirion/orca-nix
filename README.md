# Orca for Nix / NixOS

This standalone flake packages the **published [Orca](https://github.com/stablyai/orca)
binaries**, not a source checkout. See [`nix/release.json`](nix/release.json) for the pinned version. It supports `x86_64-linux` and `aarch64-linux`.
`flake.lock` pins Nixpkgs; `nix/release.json` pins each release artifact by SHA-256.

The package extracts the AppImage at build time and patches its ELF interpreter
and library paths for Nix. No FUSE, `appimage-run`, or system-wide `nix-ld` setup
is needed. The bundled Electron and native modules stay together so their ABI
matches. This does not change the glibc floor of Orca's upstream Linux releases.

## Build and install

With Nix's `nix-command` and `flakes` experimental features enabled, run from
any directory:

```sh
nix build github:elsirion/orca-nix
nix profile install github:elsirion/orca-nix
```

- **Desktop:** launch Orca from your application menu, run `orca-ide-desktop`,
  or use `nix run github:elsirion/orca-nix` without installing.
- **CLI:** run `orca-ide --help` or `nix run github:elsirion/orca-nix#cli -- --help`.
- **Headless server:** run `orca-ide serve`; Xvfb is included for hosts without a
  display. See the [headless server guide](https://github.com/stablyai/orca/blob/main/docs/reference/headless-linux-server.md) for setup.

The package deliberately does not install a command named `orca`, which would
conflict with the GNOME screen reader. Use `orca-ide` wherever Orca's general
documentation uses `orca`.

Git, OpenSSH, ripgrep, Xvfb, desktop integration tools, and the Linux Computer Use
Python/AT-SPI dependencies are supplied as fallback commands. Existing commands
on your `PATH` take precedence. Install your preferred shells and agent CLIs
separately. Folder workspaces do not require a Git repository. SSH execution
still uses the remote host's tools; this package only supplies local dependencies.

On non-NixOS Linux, desktop graphics may additionally need host-specific graphics
driver integration (for example, nixGL). Chromium's sandbox is not disabled by
the package; the host must allow unprivileged user namespaces.

## Declarative installation

Add this repository as an input to your system or Home Manager flake:

```nix
inputs.orca.url = "github:elsirion/orca-nix";
```

Pass `inputs` through your configuration's `specialArgs` (or Home Manager's
`extraSpecialArgs`), then add the package:

```nix
{ inputs, pkgs, ... }:
{
  environment.systemPackages = [
    inputs.orca.packages.${pkgs.stdenv.hostPlatform.system}.orca-ide
  ];
}
```

For Home Manager, use `home.packages` instead. A non-flake configuration can use
`pkgs.callPackage /absolute/path/to/orca-nix/nix/package.nix { }` with a compatible
Nixpkgs (the flake's locked revision is the tested version).

## Patched source overlay

The default package is not a pure release: its bundled JavaScript is rebuilt from the
upstream tag pinned in `nix/release.json` with the patches listed in
[`nix/source-overlay.json`](nix/source-overlay.json) applied (currently the
[Linux bubblewrap agent sandbox](nix/patches/linux-agent-bubblewrap-sandbox.patch),
proposed upstream from [elsirion/orca](https://github.com/elsirion/orca)). Only
`out/` inside `app.asar` is replaced; Electron and every native module still come
from the release AppImage, so the ABI contract above is unchanged.

The overlay pins two hashes that change with every release. CI refreshes them with
`scripts/update_source_overlay.py` right after the release manifest, so the daily
update keeps working as long as the patches still apply. A patch conflict fails that
update and leaves the published pin unchanged until the patch is rebased. If the
overlay pin ever lags the release, the package evaluates with a warning and builds
the unpatched release instead, so `nix build` never silently mixes versions.

To rebase after a release moved on, regenerate the patch from a fork branch rebased
onto the new tag, drop it into `nix/patches/`, then run
`python3 scripts/update_source_overlay.py` (it needs Nix and network access).

## Updates and verification

The Nix store is immutable: upgrade through Nix, not Orca's in-app updater.
The launchers clear AppImage runtime variables so the extracted installation is
not treated as a writable AppImage, including when launched from another AppImage.

[CI](https://github.com/elsirion/orca-nix/actions/workflows/ci.yml) checks for the
latest stable upstream release every day at **05:37 UTC** and can also be run
manually with **Run workflow**. The updater downloads and hashes both AppImages,
compares GitHub's asset digests when present, and refuses incomplete releases or
downgrades. Native x86-64 and ARM64 runners build and smoke-test the same candidate
before CI commits the release manifest directly to `main`. Failed checks leave
the published pin unchanged. No personal access token or extra secret is needed.

Validation runs before publishing because pushes using `GITHUB_TOKEN` do not
[trigger another workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
GitHub may delay scheduled jobs and
[disables schedules after 60 days of public-repository inactivity](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule);
re-enable the workflow if this happens. Updating the repository does **not**
automatically update installed systems: their flake lock remains pinned.

To update a NixOS installation:

```sh
sudo nix flake update orca --flake /etc/nixos
sudo nixos-rebuild switch --flake /etc/nixos#YOUR_HOST
```

For a profile installation use `nix profile upgrade orca-nix` (substitute the
entry name shown by `nix profile list`). From this repository, maintainers can run
`python3 scripts/update_release.py` with Python 3, Nix, and an authenticated `gh`
CLI. It writes `nix/release.json` only after both downloads succeed.
`nix flake update nixpkgs` updates build dependencies, not the Orca version.

## Development checks

From this checkout:

```sh
ORCA_BACKGROUND_LAUNCH=1 python3 -m unittest discover -s tests -v
nix fmt -- --check flake.nix nix/package.nix
```

```sh
ORCA_BACKGROUND_LAUNCH=1 nix flake check . -L
```

Checks run on the current architecture and verify CLI version/help, native module
loading, ANGLE graphics-library paths, desktop entry validity, command naming, AppImage environment cleanup,
and unchanged SSH relay payloads without opening a window.
Run them on both supported architectures before shipping a version update.

Packaging extracted from the Orca checkout; upstream MIT license retained in
[`LICENSE`](LICENSE). This is an unofficial Linux package, not the GNOME Orca
screen reader. macOS and Windows users should use upstream installers.
