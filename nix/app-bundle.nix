# Rebuilds Orca's JavaScript (`out/`) from the upstream release tag plus the patches listed in
# source-overlay.json. Native modules are not built here: package.nix keeps the release's, so the
# overlay only ever replaces bundled JavaScript and the Electron/native ABI stays untouched.
{
  lib,
  stdenv,
  fetchFromGitHub,
  applyPatches,
  fetchPnpmDeps,
  pnpmConfigHook,
  nodejs_24,
  pnpm_11,
  version,
  overlay,
}:
let
  # Upstream pins pnpm 12, which ships only as a native binary; pnpm 11 reads its lockfile and
  # patch hashes unchanged, so the pin is dropped and the sandbox never tries to download 12.
  pnpm = pnpm_11;
  src = applyPatches {
    name = "orca-source-${version}";
    src = fetchFromGitHub {
      owner = "stablyai";
      repo = "orca";
      tag = "v${version}";
      hash = overlay.sourceHash;
    };
    patches = map (name: ./patches + "/${name}") overlay.patches;
    postPatch = ''
      # The build smoke-launches daemon-entry.js under plain Node, which needs node-pty's native
      # addon. This build produces JavaScript only; the release's native modules are reused.
      substituteInPlace config/build-plugins/plain-node-entry-guard.ts \
        --replace-fail "if (this.meta.watchMode) {" \
          "if (this.meta.watchMode || process.env.ORCA_NIX_SKIP_PLAIN_NODE_ENTRY_SMOKE === '1') {"
      # Fetching every platform's optional binaries would multiply the dependency closure; the
      # lockfile is unaffected, so --frozen-lockfile still holds.
      grep -q '^supportedArchitectures:' pnpm-workspace.yaml
      sed -i '/^supportedArchitectures:/,/^[^ ]/{/^supportedArchitectures:/d;/^ /d}' pnpm-workspace.yaml
      grep -q '"packageManager": "pnpm@' package.json
      sed -i '/"packageManager": "pnpm@/d' package.json
    '';
  };
in
stdenv.mkDerivation (finalAttrs: {
  pname = "orca-ide-app-bundle";
  inherit version src;

  nativeBuildInputs = [
    nodejs_24
    pnpm
    pnpmConfigHook
  ];

  pnpmDeps = fetchPnpmDeps {
    inherit (finalAttrs) pname version src;
    inherit pnpm;
    fetcherVersion = 4;
    hash = overlay.pnpmDepsHash;
  };

  env.ORCA_NIX_SKIP_PLAIN_NODE_ENTRY_SMOKE = "1";

  # Same order as upstream's build:desktop, minus typecheck, relay and native steps.
  buildPhase = ''
    runHook preBuild
    pnpm exec tsc -p config/tsconfig.cli.json --outDir out --composite false --incremental false
    node config/scripts/run-electron-vite-build.mjs
    node config/scripts/project-renderer-web-client.mjs
    runHook postBuild
  '';

  # Mirrors electron-builder's `files` filters for out/.
  installPhase = ''
    runHook preInstall
    find out -name '*.map' -delete
    find out -name '*.test.js' -delete
    rm -rf out/renderer/.vite out/electron-dev
    mkdir -p "$out"
    for dir in main preload renderer shared cli web; do
      cp -r "out/$dir" "$out/$dir"
    done
    runHook postInstall
  '';

  meta = {
    description = "Orca's bundled JavaScript rebuilt from source with orca-nix patches";
    homepage = "https://github.com/stablyai/orca";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
})
