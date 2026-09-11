{
  lib,
  stdenvNoCC,
  stdenv,
  fetchurl,
  appimageTools,
  autoPatchelfHook,
  patchelf,
  makeWrapper,
  wrapGAppsHook3,
  gobject-introspection,
  runCommand,
  desktop-file-utils,
  alsa-lib,
  at-spi2-atk,
  at-spi2-core,
  cairo,
  cups,
  dbus,
  expat,
  gdk-pixbuf,
  glib,
  gtk3,
  gtk4,
  libdrm,
  libgbm,
  libGL,
  libappindicator-gtk3,
  libnotify,
  libpulseaudio,
  libsecret,
  libx11,
  libxcb,
  libxcomposite,
  libxdamage,
  libxext,
  libxfixes,
  libxkbcommon,
  libxrandr,
  libxshmfence,
  libxtst,
  nspr,
  nss,
  pango,
  systemd,
  vulkan-loader,
  zlib,
  git,
  coreutils,
  openssh,
  ripgrep,
  xdg-utils,
  xorg-server,
  xclip,
  xdotool,
  python3,
}:
let
  inherit (builtins.fromJSON (builtins.readFile ./release.json)) version sources;
  source =
    sources.${stdenvNoCC.hostPlatform.system}
      or (throw "Orca's Nix package supports only x86_64-linux and aarch64-linux");
  src = fetchurl {
    url = "https://github.com/stablyai/orca/releases/download/v${version}/${source.file}";
    inherit (source) hash;
  };
  contents = appimageTools.extract {
    pname = "orca-ide";
    inherit version src;
  };
  runtimeTools = lib.makeBinPath [
    coreutils
    git
    openssh
    ripgrep
    xdg-utils
    xorg-server
    xclip
    xdotool
    (python3.withPackages (ps: [ ps.pygobject3 ]))
  ];
in
stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "orca-ide";
  inherit version src;

  nativeBuildInputs = [
    autoPatchelfHook
    makeWrapper
    wrapGAppsHook3
    gobject-introspection
  ];
  buildInputs = [
    alsa-lib
    at-spi2-atk
    at-spi2-core
    cairo
    cups
    dbus
    expat
    gdk-pixbuf
    glib
    gtk3
    gtk4
    libdrm
    libgbm
    libGL
    libnotify
    libpulseaudio
    libsecret
    libx11
    libxcb
    libxcomposite
    libxdamage
    libxext
    libxfixes
    libxkbcommon
    libxrandr
    libxshmfence
    libxtst
    nspr
    nss
    pango
    stdenv.cc.cc.lib
    systemd
    vulkan-loader
    zlib
  ];

  # These libraries are loaded by Chromium at runtime rather than via DT_NEEDED.
  runtimeDependencies = map lib.getLib [
    gtk4
    libGL
    libappindicator-gtk3
    libnotify
    libpulseaudio
    libsecret
    vulkan-loader
  ];
  dontUnpack = true;
  dontBuild = true;
  dontStrip = true;
  dontWrapGApps = true;
  dontAutoPatchelf = true;

  installPhase = ''
    runHook preInstall

    mkdir -p "$out/lib/orca-ide" "$out/bin" "$out/share/applications"
    cp -a ${contents}/. "$out/lib/orca-ide/"
    chmod -R u+w "$out/lib/orca-ide"
    # Nix supplies the runtime libraries; the AppImage launcher is not used.
    rm -r "$out/lib/orca-ide/AppRun" "$out/lib/orca-ide/usr/lib"

    install -Dm644 ${contents}/orca-ide.desktop "$out/share/applications/orca-ide.desktop"
    substituteInPlace "$out/share/applications/orca-ide.desktop" \
      --replace-fail 'Exec=AppRun' "Exec=$out/bin/orca-ide-desktop"
    cp -a ${contents}/usr/share/icons "$out/share/"

    runHook postInstall
  '';

  preFixup = ''
    # Keep the bundled CLI's Node-mode dispatch and native-module ABI intact.
    makeWrapper "$out/lib/orca-ide/resources/bin/orca-ide" "$out/bin/orca-ide" \
      "''${gappsWrapperArgs[@]}" \
      --suffix PATH : ${runtimeTools} \
      --unset APPIMAGE --unset APPDIR
    makeWrapper "$out/lib/orca-ide/orca-ide" "$out/bin/orca-ide-desktop" \
      "''${gappsWrapperArgs[@]}" \
      --suffix PATH : ${runtimeTools} \
      --unset APPIMAGE --unset APPDIR
  '';

  postFixup = ''
    autoPatchelf "$out"
    # ANGLE dlopens graphics libraries from these shared objects, not the executable.
    for library in "$out/lib/orca-ide/libEGL.so" "$out/lib/orca-ide/libGLESv2.so"; do
      ${lib.getExe patchelf} --add-rpath ${
        lib.makeLibraryPath [
          libGL
          vulkan-loader
        ]
      } "$library"
    done
  '';

  passthru.tests.smoke =
    runCommand "orca-ide-smoke"
      {
        nativeBuildInputs = [
          desktop-file-utils
          patchelf
        ];
        ORCA_BACKGROUND_LAUNCH = "1";
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        unset DISPLAY WAYLAND_DISPLAY
        package=${finalAttrs.finalPackage}
        test "$("$package/bin/orca-ide" --version)" = ${version}
        "$package/bin/orca-ide" --help > "$TMPDIR/help"
        grep -q serve "$TMPDIR/help"
        desktop-file-validate "$package/share/applications/orca-ide.desktop"
        test -x "$package/bin/orca-ide-desktop"
        test ! -e "$package/bin/orca"
        for library in libEGL.so libGLESv2.so; do
          rpath=$(patchelf --print-rpath "$package/lib/orca-ide/$library")
          [[ ":$rpath:" == *":${lib.getLib libGL}/lib:"* ]]
        done
        APPIMAGE=/inherited.AppImage APPDIR=/inherited ELECTRON_RUN_AS_NODE=1 \
          "$package/bin/orca-ide-desktop" -e '
          const assert = require("node:assert/strict");
          assert.equal(process.env.APPIMAGE, undefined);
          assert.equal(process.env.APPDIR, undefined);
          const modules = process.argv[1] + "/lib/orca-ide/resources/node_modules/";
          require(modules + "node-pty");
          require(modules + "@parcel/watcher");
        ' "$package"
        # Remote payloads must not acquire this machine's Nix interpreter paths.
        diff -r ${contents}/resources/relay "$package/lib/orca-ide/resources/relay"
        touch "$out"
      '';

  meta = {
    description = "IDE for orchestrating AI coding agents across terminals and worktrees";
    homepage = "https://github.com/stablyai/orca";
    license = lib.licenses.mit;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
    platforms = builtins.attrNames sources;
    mainProgram = "orca-ide-desktop";
  };
})
