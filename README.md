# HipFire on RX 7900 XTX — 76.71 tok/s at 99,855 populated tokens

Grouped draft attention and DeltaNet capture raised mean sampled decode throughput from **73.39 to 76.71 tok/s (+4.52%)**. Both candidate runs beat both controls on this coding fixture.

## Project background

The original goal was to reach 100 sustained sampled decode tokens/s at approximately 100K populated prompt tokens on a single RX 7900 XTX, running natively on Windows.

The project started with llama.cpp experiments on Vulkan and ROCm, testing Q4 and Q8 KV caches and DFlash2 and MTP speculative decoding. In one early Vulkan DFlash2 Q4 KV series, llama.cpp reported 54.45 and 52.62 decode tok/s at 3,980 and 15,992 populated tokens. These are historical server-reported rates; the HipFire results below use client-side streaming timing.

The first HipFire Windows builds failed to link on POSIX symbols such as `mmap`, `dlopen`, and `clock_gettime`. The Windows beta branch built the CLI and daemon successfully, and a subsequent release build succeeded after normalizing HIP source files to LF. Long-context testing used legacy KV because the Windows VMM product gate was still in place.

The earliest verified HipFire benchmark series are shown below in recorded order. All three used sampled native MTP K3.

| Legacy KV | Allocated capacity | Short coding runs (populated tokens → decode tok/s) | Long coding run (populated tokens → decode tok/s) |
|---|---:|---|---|
| Q8 | 114,688 | 3,533 → 79.42; 14,279 → 74.94 | 99,854 → 63.16 |
| FWHT4 | 114,688 | 3,536 → 87.23; 14,278 → 70.98 | 99,851 → 45.59 |
| Q8 | 106,496 | 3,537 → 83.39; 14,283 → 83.89 | 99,855 → **65.85** |

The retained configuration returned to Q8 and reduced the allocated capacity from 114,688 to 106,496 tokens. The recorded launcher used batch size 1, native MTP K3, n-gram enabled and FA2 split verification disabled. A later baseline audit confirmed the Q8X projection and WMMA attention routes. The 65.849713 tok/s run generated 1,024 tokens with zero cache hits. These historical runs differed in input and conditions, and the original environment record is incomplete; the receipts establish the configuration sequence without assigning a speedup to any one change.

The subsequent research investigated where sampled K3 spent its time. Two long diagnostic runs reached 68.03 and 70.23 tok/s under differing conditions, with no verified software change accounting for those rates. The final same-binary comparison measured the combined effect of grouped draft attention and DeltaNet capture: 73.39 to 76.71 tok/s (+4.52%) at 99,855 populated tokens.

After 26 numbered engineering reviews, the investigation concluded at this reproducible result. Neither the original 100 tok/s target nor the revised 80 tok/s milestone was reached, but the target context and sampled decoding were preserved.

## Test system and final configuration

- AMD Radeon RX 7900 XTX (gfx1100, 24 GB VRAM), 64 GB system RAM.
- Native Windows 11 Pro build 26200, AMD driver 32.0.32029.2010, TheRock 10.1.0 / HIP 7.16.
- [HipFire](https://github.com/warpfront/hipfire) experimental build based on revision 981e78248112b90f9cdae88fe8f6df34dc9cc827.
- Qwen3.8-27B dense MQ4-XTS, legacy Q8 KV, 106,496 allocated sequence capacity, sampled native MTP K3, continuous batch size 1.
- Q8X projection verification and WMMA attention verification enabled. N-gram enabled and unused on this fixture. FA2 split verification, snapshot overlap and diagnostic profiling disabled. Probability readbacks remain dense.

On the experimental build, set `HIPFIRE_EXPERIMENT_DRAFT_GQA=1` and `HIPFIRE_EXPERIMENT_NATIVE_MTP_GDN_CAPTURE=1`. The former selects grouped Q8 attention for eligible serial compressed native draft steps. The latter selects the existing DeltaNet capture preamble for eligible single-lane verification. Ineligible shapes retain the incumbent paths, and replay is unchanged. These flags require the experimental dispatch changes.

Use matching CLI and daemon binaries, the existing HIP runtime and model files, and a separate HipFire home. Launch on localhost with `--kv-backend legacy --kv-mode q8 --max-seq 106496 --spec mtp --continuous-batch-size 1`. Set `HIPFIRE_MTP_K=3`, `HIPFIRE_MTP_NGRAM=1`, `HIPFIRE_GFX1100_Q8X_VERIFY=1`, `HIPFIRE_GFX1100_WMMA_VERIFY_ATTN=1`, `HIPFIRE_GFX1100_FA2_SPLIT_VERIFY=0`, and `HIPFIRE_MTP_SNAPSHOT_OVERLAP=0`. Set both experimental flags to zero for the same-binary control. For rollback, stop the experimental service and start the original installation in a fresh shell.

## Benchmark method and results

Four localhost runs used the same binary and frozen coding request in A/B/B/A order, with a fresh HipFire home per arm. A disabled both experimental flags. B enabled both. Every request populated 99,855 prompt tokens, hit zero cached tokens, and generated 1,024 tokens. Sampling used seed 1234, temperature 1.0, top-p 0.95, top-k 20, and min-p 0. Client decode throughput is 1,023 divided by elapsed seconds from the first streamed text or reasoning event to SSE completion.

| Run | Configuration | Decode tok/s | TTFT (s) | Total (s) | Peak edge / hotspot / memory (°C) |
|---|---|---:|---:|---:|---|
| A1 | Control | 73.799011 | 166.083 | 179.945 | 55 / 78 / 88 |
| B1 | Combined | 75.868125 | 125.551 | 139.035 | 55 / 80 / 88 |
| B2 | Combined | 77.556545 | 129.286 | 142.476 | 56 / 80 / 90 |
| A2 | Control | 72.988696 | 125.506 | 139.522 | 57 / 81 / 90 |

Mean throughput was 73.393854 tok/s for A and 76.712335 for B. Paired decode savings were 0.370 and 0.807 ms per token. B2 took about 3% longer to first token than A2 and had slightly higher total request time. These four requests measure the combined effect on one machine and fixture. They leave individual contributions, broader workload variance, and sustained 80 tok/s open.

The original installation previously recorded 65.849713 tok/s at the same actual depth under unmatched build and run conditions. The 68.034814 and 70.233852 tok/s observations were diagnostic runs. The +4.52% figure uses only the matched controls above.

## Investigated approaches and negative results

| Handoffs | Findings |
|---|---|
| 001–004 | K4 was slower in short sampled screens, so K3 stayed. Windows VMM remained gated and the working legacy-Q8 WMMA route stayed in use. |
| 005–008 | Fine-grained HIP event timing intermittently reported negative intervals during inference. The cause remained unresolved, limiting what the timings could establish. |
| 009–010 | Target probability compaction cut payload roughly 482× without a meaningful served-throughput gain. Waiting for the producer first showed that most of the original readback bracket was queued work. Dense reads stayed. |
| 011–015 | Host timing yielded two unmatched long observations. Two guarded attempts stopped during prefill and yielded no decode rate. The MLP and target WMMA QT2 audits found no sufficiently supported rewrite. Direct dispatch receipts identified the plain Q8 route actually used by the serial draft. |
| 016–021 | Grouped draft attention and DeltaNet capture passed their respective isolated correctness checks but each missed its standalone timing gate. Q8X geometry caching measured about 35 µs of host time per full window. Draft readback batching showed no repeatable removable millisecond. |
| 022–023 | The observed prefill path already released the widened scratch owner. Decode-entry residency remained unresolved, and the four-row projection layout audit did not establish grounds for a rewrite. |
| 024–026 | The two opt-in routes passed short integration together and then won both matched long pairs. The experiment measured their combined effect. Individual contributions and sustained 80 or 100 tok/s remain unestablished. |

The final offline assessment found no sufficiently supported low-risk route to the remaining 80 tok/s milestone. This is a practical stopping point, not an established hardware ceiling.

## Correctness

All four long runs matched streamed text, reasoning, finish status, usage and standard speculation counts (1,059 drafted, 669 accepted per run). Short integration checks covered forced fallback, retained-prefix depths, EOS, rollback, cancellation and extension of the retained prefix. The long comparison did not record full token-ID or recurrent-state traces. Results cover this fixture and sampling seed.

## AI assistance

Codex and ChatGPT helped with research, benchmark setup, review, and writing this README.

## Reproduction files

- [results.csv](results.csv) contains the four measured runs. The decode interval is reconstructed from the recorded rate.
- [measure.py](measure.py) measures one streamed localhost request using the same timing boundaries.
- [make_fixture.py](make_fixture.py) creates a shareable synthetic coding request with the same sampling parameters. Vary the block count and use returned usage to confirm the actual populated depth. This fixture has a different token distribution and acceptance behavior from the measured request.

The [Windows build guide](BUILD.md) covers the [source patch](patches/hipfire-gfx1100-mtp.patch), dependencies, configuration, launch, and rollback. The benchmark results above were recorded on the research build. See the [upstream license terms](LICENSE) and [NOTICE](NOTICE) for attribution.
