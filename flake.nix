{
  description = "netplay-relay: RetroArch's netplay tunnel (MITM) server with a session listing";

  inputs = {
    # The nixpkgs homelab pins (github:imkarrer/homelab flake.nix), so the
    # python3 this wraps is the one arcade-box already has. home-arcade's
    # flox environment installs this package by `.flake` reference; its CI
    # pushes the output to the CI cache, and the box substitutes it.
    nixpkgs.url = "github:NixOS/nixpkgs/c5c4a43b0e8056328ec4529f735cabdb8f1942bb";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      lib = pkgs.lib;
      src = lib.fileset.toSource {
        root = ./.;
        fileset = lib.fileset.unions [ ./retroarch_tunnel_server.py ./test_relay.py ];
      };
    in
    {
      packages.${system} = rec {
        netplay-relay = pkgs.stdenvNoCC.mkDerivation {
          pname = "netplay-relay";
          version = "1.0.0";
          inherit src;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontBuild = true;
          installPhase = ''
            install -Dm644 retroarch_tunnel_server.py $out/share/netplay-relay/retroarch_tunnel_server.py
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/netplay-relay \
              --add-flags "-SOO $out/share/netplay-relay/retroarch_tunnel_server.py"
          '';
          doInstallCheck = true;
          installCheckPhase = ''
            $out/bin/netplay-relay --version | grep -q netplay-relay
          '';
          meta = {
            description = "RetroArch netplay tunnel server with a GET /sessions listing";
            license = lib.licenses.gpl3Plus;
            mainProgram = "netplay-relay";
          };
        };
        default = netplay-relay;
      };

      # The protocol tests over loopback, which the build sandbox allows.
      checks.${system}.tests = pkgs.runCommand "netplay-relay-tests" { nativeBuildInputs = [ pkgs.python3 ]; } ''
        cp -r ${src}/. .
        python3 -m unittest -v 2>&1
        touch $out
      '';
    };
}
