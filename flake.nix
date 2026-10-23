{
  description = "Dupot File Browser — Rust GTK4/Libadwaita application";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        nativeBuildInputs = with pkgs; [
          pkg-config
          wrapGAppsHook4
          copyDesktopItems
        ];

        buildInputs = with pkgs; [
          glib
          gtk4
          libadwaita
        ];

        dupot-file-browser = pkgs.rustPlatform.buildRustPackage {
          pname = "dupot-file-browser";
          version = (builtins.fromTOML (builtins.readFile ./Cargo.toml)).package.version;
          src = ./.;
          cargoLock.lockFile = ./Cargo.lock;
          inherit nativeBuildInputs buildInputs;

          # Shown in the About dialog (the Nix sandbox has no .git).
          env = {
            DUPOT_BUILD_PACKAGE = "nix";
            DUPOT_BUILD_DATE =
              let d = self.lastModifiedDate or "";
              in if d == "" then "" else
                "${builtins.substring 0 4 d}-${builtins.substring 4 2 d}-${builtins.substring 6 2 d}";
          };

          desktopItems = [
            (pkgs.makeDesktopItem {
              name = "org.dupot.filebrowser";
              desktopName = "File Browser";
              comment = "Browse your files";
              exec = "dupot-file-browser";
              icon = "org.dupot.filebrowser";
              categories = [ "Utility" "FileTools" "FileManager" ];
            })
          ];

          postInstall = ''
            install -Dm644 src/assets/logo512.png \
              $out/share/icons/hicolor/512x512/apps/org.dupot.filebrowser.png
          '';

          meta = {
            description = "A simple, lightweight file browser for the Linux desktop";
            license = pkgs.lib.licenses.lgpl21Only;
            mainProgram = "dupot-file-browser";
          };
        };
      in
      {
        packages.default = dupot-file-browser;

        apps.default = flake-utils.lib.mkApp { drv = dupot-file-browser; };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ dupot-file-browser ];
          packages = with pkgs; [
            cargo
            rustc
            clippy
            rustfmt
            rust-analyzer
            gettext
          ];

          RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";

          shellHook = ''
            export XDG_DATA_DIRS="${pkgs.gtk4}/share/gsettings-schemas/${pkgs.gtk4.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:''${XDG_DATA_DIRS:-}"
            echo "Rust GTK4/Libadwaita development environment" >&2
            rustc --version >&2
          '';
        };
      }
    );
}
