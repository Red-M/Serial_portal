{ # This isn't made to be run by other people
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    outoftree = {
      url = "path:/home/redm/git/dotfiles/NixOS/pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      ...
    }@inputs:
    let
      forAllSys = nixpkgs.lib.genAttrs nixpkgs.lib.platforms.all;
    in
    {
      devShell = forAllSys (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          unstable_pkgs = import inputs.nixpkgs-unstable {
            inherit system;
            config.allowUnfree = true;
          };
        in
        pkgs.mkShell {
          buildInputs = with pkgs; [
            inputs.outoftree.outputs.pkgs.${pkgs.system}.redexpect
            python3Packages.pyyaml
            socat
          ];
        }
      );
    };
}
