# Development environment setup

The nominal path is Homebrew (macOS or Linux). If Homebrew's bottles need a
newer OS/Xcode than you have (common on older macOS, where it falls back to
building from source and often fails), use the fallbacks further down.

## Nominal install (Homebrew)

Homebrew works on both macOS and Linux:

```
brew install bazelisk git-lfs gh
git lfs install
```

- `bazelisk` provides the `bazel` command -- it downloads the pinned Bazel on
  first run. It's the only hard prerequisite for building.
- `git-lfs` is needed to fetch `MODULE.bazel.lock` (stored in LFS).
- `gh` (optional) drives the PR workflow.
- Optional: `brew install node` only if you use Node-based tooling (e.g. Claude
  Code plugins) -- it is not a build prerequisite.

## Git hooks (optional)

A pre-commit hook auto-formats staged Python with ruff (via `bazel run //:ruff`).
Enable it once per clone:

```
git config core.hooksPath .githooks
```

## Fallbacks without Homebrew

On older macOS, Homebrew's bottles often need a newer OS/Xcode than you have and
fall back to building from source. Use these instead.

### Bazel (bazelisk) from source

If Homebrew isn't an option (e.g. its bottles need a newer Xcode Command Line
Tools version than you have installed), build bazelisk yourself -- it's a
small pure-Go binary with no C dependencies, so it only needs a Go toolchain,
not a C/C++ compiler.

1. Download Go's official archive directly from go.dev (not Homebrew) and
   verify its checksum:

   ```
   curl -LsS -o go.tar.gz https://go.dev/dl/go1.26.5.darwin-amd64.tar.gz
   echo "6231d8d3b8f5552ec6cbf6d685bdd5482e1e703214b120e89b3bf0d7bf1ef725  go.tar.gz" | shasum -a 256 -c -
   ```

   (Check https://go.dev/dl/?mode=json for the current release and its
   `sha256`/filename for your OS/arch if `go1.26.5`/`darwin-amd64` is stale.)

2. Extract it somewhere in your home directory -- no sudo needed:

   ```
   mkdir -p ~/.local/go-sdk
   tar -xzf go.tar.gz -C ~/.local/go-sdk
   ```

3. Clone bazelisk's source and build it with that toolchain:

   ```
   git clone --depth 1 --branch v1.29.0 https://github.com/bazelbuild/bazelisk.git
   cd bazelisk
   ~/.local/go-sdk/go/bin/go build -o bazelisk .
   ```

4. Install the resulting binary as `bazel` somewhere on your PATH:

   ```
   mkdir -p ~/.local/bin
   cp bazelisk ~/.local/bin/bazel
   ```

`bazel` (really bazelisk) then downloads the genuine, official prebuilt Bazel
release binary on first run -- building bazelisk from source doesn't mean
building Bazel itself from source (which does need a C++ toolchain and is a
much bigger undertaking).

### git-lfs (prebuilt binary)

Homebrew builds git-lfs from source on older macOS (needs a Go toolchain, often
fails). Skip it -- git-lfs ships standalone prebuilt binaries.

1. Download the latest build for your arch (check
   https://github.com/git-lfs/git-lfs/releases for the current version; use
   `arm64` instead of `amd64` on Apple Silicon):

   ```
   curl -sSL -o git-lfs.zip https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-darwin-amd64-v3.7.1.zip
   unzip -oq git-lfs.zip -d git-lfs-dl
   ```

2. Install the binary somewhere on your PATH (no sudo if you own the dir, e.g.
   `/usr/local/bin` on an Intel Homebrew layout):

   ```
   cp git-lfs-dl/git-lfs-*/git-lfs /usr/local/bin/git-lfs
   chmod +x /usr/local/bin/git-lfs
   ```

3. Register its git hooks/filters and verify:

   ```
   git lfs install
   git lfs version
   ```

If Gatekeeper blocks it, clear the quarantine flag:
`xattr -d com.apple.quarantine /usr/local/bin/git-lfs`.

### gh (prebuilt binary)

`gh` is a Go binary too -- grab the official prebuilt from
https://github.com/cli/cli/releases (`arm64` on Apple Silicon):

```
curl -sSL -o gh.zip https://github.com/cli/cli/releases/download/v2.97.0/gh_2.97.0_macOS_amd64.zip
unzip -oq gh.zip && cp gh_*_macOS_amd64/bin/gh /usr/local/bin/gh
```

### node (prebuilt binary, optional)

Don't build node from source (a long C++ build). Use the official prebuilt
tarball from https://nodejs.org/dist (`arm64` on Apple Silicon):

```
curl -sSL -o node.tar.gz https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-x64.tar.gz
tar xzf node.tar.gz
cp -R node-v24.19.0-darwin-x64/{bin,lib,include,share} /usr/local/
```
