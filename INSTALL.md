# Installing bazelisk from source

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
