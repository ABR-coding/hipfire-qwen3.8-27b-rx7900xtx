# Build HipFire for RX 7900 XTX on Windows

This guide builds the source patch for sampled native MTP on the RX 7900 XTX (`gfx1100`). See the [benchmark report](README.md) for the measured results, hardware, methodology, and correctness disclosures. The release patch carries the qualified dispatch routes with the research diagnostics removed. The reported runs used the research build. Build validation of this package covers compilation and linking.

## Prerequisites

- Native 64-bit Windows and a Radeon RX 7900 XTX with an AMD driver compatible with the HIP runtime. The measured system used Windows 11 Pro build 26200 and AMD driver `32.0.32029.2010`.
- Git, PowerShell, and Rust/Cargo for `x86_64-pc-windows-msvc`. The isolated build used Rust `1.100.0`.
- Visual Studio C++ Build Tools with the x64 MSVC linker and a Windows SDK. The isolated build used MSVC `14.29.30133` and Windows SDK `10.0.19041.0`. Use an x64 Developer PowerShell or make those tools available through the Rust MSVC toolchain.
- TheRock `10.1.0` for Windows (`HIP 7.16`), including the HIP DLLs, `hipcc`, the LLVM tools, and AMDGPU device bitcode. The first launch can compile missing kernels into the selected cache. Obtain the SDK for your card from [TheRock](https://github.com/ROCm/TheRock).
- The Qwen3.8-27B MQ4-XTS trunk, native MTP sidecar, and vision sidecar used by the recorded launcher. Place them together under `models` alongside the report checkout. These are available from [HipFire’s Qwen3.8-27B model repository](https://huggingface.co/hipfire-models/qwen3.8-27b). Keep the filenames shown below so native MTP can discover its adjacent sidecar. Allow about 16.2 GB for these files, plus space for the SDK, checkout, Cargo dependencies, and build output.
- Python 3 is needed only for the optional example using the report’s fixture and measurement scripts.

The following SHA-256 values are from `registry/v1.json` at the pinned source revision. Inspect the files with `Get-FileHash -Algorithm SHA256` before launch.

| File | SHA-256 |
|---|---|
| `qwen3.8-27b.mq4-xts` | `3e38ccbae3776470eb5a89344d300e9279d6b9ab6c31fd40ca1758c4f7c6f8ae` |
| `qwen3.8-27b.mtp` | `f0d46d07ded75abc095ebfdbccc167c68418a6515b187bf810395faa460bd32e` |
| `qwen3.8-27b-vision.hfq` | `269457cb42adc9d2fd20b33d2911e1b3015a30ef2033927f500c7fbe508753c9` |

## Get the source and build

From the directory containing this guide, run the following in PowerShell. Use a new `hipfire-src` directory and place the unpacked Windows SDK in `therock-10.1.0` alongside it, or set `$sdk` to your SDK directory. Paths derived from the working directory here are local to your machine.

```powershell
$release = (Get-Location).Path
$source = Join-Path $release 'hipfire-src'
$sdk = (Resolve-Path (Join-Path $release 'therock-10.1.0')).Path
$patch = Join-Path $release 'patches\hipfire-gfx1100-mtp.patch'
$revision = '981e78248112b90f9cdae88fe8f6df34dc9cc827'

git clone --no-checkout -c core.autocrlf=false https://github.com/warpfront/hipfire.git $source
if ($LASTEXITCODE) { throw 'Clone failed' }
git -C $source checkout --detach $revision
if ($LASTEXITCODE -or (git -C $source rev-parse HEAD) -ne $revision) { throw 'Pinned checkout failed' }
git -C $source apply --check --whitespace=error $patch
if ($LASTEXITCODE) { throw 'Patch check failed' }
git -C $source apply --whitespace=error $patch
if ($LASTEXITCODE) { throw 'Patch application failed' }

$env:HIP_PATH = $sdk
$env:ROCM_PATH = $sdk
$env:HIPFIRE_ROCM_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = Join-Path $sdk 'lib\llvm\amdgcn\bitcode'
$env:Path = "$sdk\bin;$sdk\lib\llvm\bin;$env:Path"
$env:CARGO_TARGET_DIR = Join-Path $source 'target'

Push-Location $source
try {
    cargo fetch --locked
    if ($LASTEXITCODE) { throw 'Dependency fetch failed' }
    cargo build --offline --locked --release -p hipfire-cli -p hipfire-daemon
    if ($LASTEXITCODE) { throw 'Release build failed' }
} finally {
    Pop-Location
}
```

Git is configured to preserve the upstream LF source files on checkout. If the locked Cargo dependencies are already cached, skip `cargo fetch`. The two resulting binaries are `hipfire-src\target\release\hipfire.exe` and `hipfire-src\target\release\daemon.exe`. Use them as a pair.

## Start the combined configuration

Continue in the same PowerShell. Stop any existing HipFire service you own that holds the GPU, then choose a free localhost port. Keep the original HipFire installation and model files in place. The commands below use a new state directory and kernel cache.

```powershell
$bin = Join-Path $env:CARGO_TARGET_DIR 'release'
$modelDir = Join-Path $release 'models'
$model = (Resolve-Path (Join-Path $modelDir 'qwen3.8-27b.mq4-xts')).Path
$vision = (Resolve-Path (Join-Path $modelDir 'qwen3.8-27b-vision.hfq')).Path
$mtp = Join-Path $modelDir 'qwen3.8-27b.mtp'
if (!(Test-Path -LiteralPath $mtp -PathType Leaf)) { throw 'Native MTP sidecar is missing' }

$env:HIPFIRE_HOME = (New-Item -ItemType Directory -Path (Join-Path $release 'combined-home') -Force).FullName
$env:HIPFIRE_KERNEL_CACHE = (New-Item -ItemType Directory -Path (Join-Path $release 'combined-kernels') -Force).FullName
$env:HIPFIRE_DAEMON_BIN = Join-Path $bin 'daemon.exe'
$env:HIPFIRE_NO_REGISTRY_FETCH = '1'
$env:HIPFIRE_MTP_K = '3'
$env:HIPFIRE_MTP_NGRAM = '1'
$env:HIPFIRE_GFX1100_Q8X_VERIFY = '1'
$env:HIPFIRE_GFX1100_WMMA_VERIFY_ATTN = '1'
$env:HIPFIRE_GFX1100_FA2_SPLIT_VERIFY = '0'
$env:HIPFIRE_MTP_SNAPSHOT_OVERLAP = '0'
$env:HIPFIRE_EXPERIMENT_DRAFT_GQA = '1'
$env:HIPFIRE_EXPERIMENT_NATIVE_MTP_GDN_CAPTURE = '1'
Remove-Item Env:HIPFIRE_PROFILE,Env:HIPFIRE_MTP_TRACE,Env:HIPFIRE_LOCK_DIR -ErrorAction SilentlyContinue

& (Join-Path $bin 'hipfire.exe') serve 127.0.0.1:8080 --model $model --vision $vision `
    --kv-backend legacy --kv-mode q8 --max-seq 106496 --spec mtp --continuous-batch-size 1
```

Keep the service in the foreground. Once it is ready, send requests to `http://127.0.0.1:8080/v1/chat/completions` with the preloaded model path as the selector. From another PowerShell at the report checkout, the following is an optional synthetic example. The block count is a starting point. Use returned `prompt_tokens` and `cached_tokens` to confirm the actual depth and cache behavior. The synthetic workload has its own token distribution and acceptance behavior.

```powershell
$model = (Resolve-Path '.\models\qwen3.8-27b.mq4-xts').Path
python .\make_fixture.py $model .\synthetic-request.json --blocks 200
python .\measure.py .\synthetic-request.json --port 8080
```

## Same-binary control and rollback

- **Control.** Stop the service with Ctrl+C and wait for the launcher and daemon to exit. Set both `HIPFIRE_EXPERIMENT_DRAFT_GQA` and `HIPFIRE_EXPERIMENT_NATIVE_MTP_GDN_CAPTURE` to `0`, then rerun only the final `serve` command with the same binaries and options. For a comparison, give each arm a fresh `HIPFIRE_HOME` and verify zero cached prompt tokens. The two flags also default to off when unset.
- **Rollback.** Stop the patched service with Ctrl+C, wait for the port and GPU reservation to be released, and close this PowerShell to discard its environment changes. In a fresh shell, start the original HipFire CLI and its matching original daemon with your original launcher and configuration. Keep the separate source, cache, and home directories if you plan to use the patched build again.

The patch reuses upstream HipFire kernels and preserves the source-file notices. See [LICENSE](LICENSE), [LICENSE-APACHE](LICENSE-APACHE), [LICENSE-MIT](LICENSE-MIT), [NOTICE](NOTICE), [CREDITS.md](CREDITS.md), and [PRIOR-ART.md](PRIOR-ART.md).
