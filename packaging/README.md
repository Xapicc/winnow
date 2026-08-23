# Packaging: deleted, and how to get it back

**Winnow publishes to no package channel.** The only supported install is from source; the container
image is [docs/FORK.md](../docs/FORK.md) phase 4's. This directory holds no recipes, and this file is
the record of the ones that were removed — deleting another project's release process is worth being
explicit about.

The decision is [docs/FORK.md](../docs/FORK.md) §3, not a preference formed here. Its three reasons,
shortest first: PyPI `winnow` and npm `winnow` are both taken by unrelated projects, so there is no
name to rename these recipes *to*; every recipe pinned a sha256 of an upstream sdist that winnow will
never produce; and the release workflow published under a PyPI trusted-publisher registration held by
a GitHub repository winnow does not control.

## What was deleted, and from where to recover it

Everything below is recoverable from **`d114fc8`**, the last commit that contained it. Retrieve a
single file with `git show d114fc8:packaging/homebrew/cozempic.rb`, or the whole set with
`git checkout d114fc8 -- packaging npm claude-opus-1m.sh`.

| Path | Channel | Declared |
| --- | --- | --- |
| `packaging/homebrew/cozempic.rb` | Homebrew, via the tap `Ruya-AI/homebrew-cozempic` | 1.8.39, sha256 `4c6a73…`, of a PyPI tarball URL |
| `packaging/aur/PKGBUILD` | AUR | `pkgver=1.8.19`, sha256 `14ff2a…` |
| `packaging/aur/.SRCINFO` | AUR | `pkgver = 1.8.18`, sha256 `da2c37…`, source line pinning **1.7.1** |
| `packaging/macports/Portfile` | MacPorts, `python/py-cozempic` | 1.8.34, rmd160 + sha256 + size |
| `packaging/nix/default.nix` | nixpkgs `pkgs/by-name/co/cozempic` | 1.8.34, SRI hash `sha256-WhzGI5…` |
| `packaging/nix/flake.nix` | Nix flake, `nix run github:Ruya-AI/cozempic?dir=packaging/nix` | wrapper over `default.nix` |
| `packaging/ci/publish.yml` | PyPI, on GitHub Release | trusted publisher, owner `Ruya-AI`, repository `cozempic`, environment `pypi` |
| `npm/package.json`, `npm/bin/cozempic.js`, `npm/install.js` | npm | package and binary `cozempic` 1.8.39, `postinstall: node install.js` |
| `claude-opus-1m.sh` | not a channel | upstream author's launcher; deleted with the same reasoning as `scripts/` |

Four different versions across five channels, and three sha256 values that disagree with each other,
is the state they were inherited in. None of them ever published anything from this repository:
`publish.yml` was never installed as a workflow — there is no `.github/` here — and no tap, AUR repo,
port or nixpkgs entry exists under winnow's name.

`npm/install.js` was the one file here that was executable code rather than metadata, and it is the
reason this run existed at all. As a `postinstall` hook it pip-installed the `cozempic` distribution
through a five-way ladder (`uv`/`pip`/`pip3`/`python3 -m pip`/`python -m pip`), pinged
`https://api.counterapi.dev/v1/cozempic/installs/up`, appended a global `SessionStart` hook running
`cozempic guard --daemon` into `~/.claude/settings.json`, and ran `cozempic init --quiet` in any
directory containing `.claude` — each step wrapped in a bare `catch {}`. The install ping is the same
class of outbound call the phase-2 run removed from the runtime.

## What publishing later would take

Restoring the files is the small part. In order:

1. **Choose a distribution name that is free.** `winnow` is not. Free on 2026-08-23, checked against
   the live registries: `winnow-cli`, `winnowctl`, `winnow-context`, `winnow-claude`, `nms-winnow`.
   Re-check before relying on any of them. The Python import name can stay `winnow` either way, at
   the cost documented in [docs/FORK.md](../docs/FORK.md) §3: a machine with both this project and
   the existing PyPI `winnow` installed gets one of them and a broken one.
2. **Set `[project.name]` in `pyproject.toml` to that name**, and the console script with it. It is
   `winnow` today, which is the name PyPI has already given to somebody else.
3. **Publish an artefact first, then write the recipes against it.** Every field these recipes got
   wrong is downstream of pinning a hash for a tarball that did not exist. Per channel that means:
   `url`/`source` pointing at the real sdist, a `sha256` computed from the file that was actually
   uploaded (MacPorts also wants `rmd160` and `size`; Nix wants the SRI form), `homepage`,
   `repository` and `changelog` at `github.com/Xapicc/winnow`, `license` matching `LICENSE`, and a
   maintainer who has agreed to be one — the deleted recipes named upstream's author in three
   different formats.
4. **Register the publisher yourself.** A trusted-publisher registration names an owner and a
   repository. Winnow's would have to be created against `Xapicc/winnow` on the PyPI project it
   actually owns; the deleted workflow's registration cannot be inherited, borrowed or pointed at
   this repository.
5. **Decide separately whether an npm shim should exist at all.** If one does, it publishes nothing
   in a `postinstall`: no cross-ecosystem install, no counter, no writes to `~/.claude`.

A restored recipe with a hash left as a placeholder is fine and honest. A restored recipe carrying
one of the hashes in the table above is not — those checksums belong to somebody else's artefacts.
