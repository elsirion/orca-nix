{
  description = "Orca IDE for NixOS and Linux";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      forAllSystems = nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
      ];
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          orca-ide = pkgs.callPackage ./nix/package.nix { };
        in
        {
          inherit orca-ide;
          default = orca-ide;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.orca-ide}/bin/orca-ide-desktop";
          meta.description = "Launch the Orca desktop app";
        };
        cli = {
          type = "app";
          program = "${self.packages.${system}.orca-ide}/bin/orca-ide";
          meta.description = "Run the Orca CLI";
        };
      });

      checks = forAllSystems (system: {
        inherit (self.packages.${system}.orca-ide.tests) smoke;
      });

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt);
    };
}
