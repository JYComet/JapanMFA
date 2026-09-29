# 0922jap 原生 Qwen ForcedAligner 回归（2026-09-28）

> 后续已修复 0110 的 Qwen 硬裁剪导致的漏音，并在独立输入目录重跑七条。当前交付状态以 [Qwen 裁剪边界修复复核](test-report-acoustic-context-0922jap-20260928.md) 为准；下文保留初次批次和首次撤回的历史证据。

> 复核更正：人工查看 0110 波形后，发现原批次误把真实声音标为静音。1.20–1.92 s 和 2.88–3.805 s 的合成静音段分别含 0.35 s 和 0.36 s 的高能量帧。原检查只审计 MFA 显式静音，遗漏了分段后补出的静音。已增加声学覆盖检查；在同一 0110 工作 WAV 和原始音素区间上复核，现以 `alignment_acoustic_coverage` 拒绝；0080 仍通过。0110 TextGrid 已从共享成品目录撤回。下文的 `summary.json` 与运行结果是修正前的历史记录。

## 范围与模型

源数据为 `/mnt/Raw/0922jap` 的七条 OGG/TXT；源目录保持只读。最终独立运行结果在 `runs/0922jap-native-qwen-final-20260928/`，其中 `summary.json`、`manifest.jsonl`、各样本的 `asr.json`、`mfa.json`、`postprocess.json` 和 MFA 原始 TextGrid 可逐项核对。运行使用 `configs/0922jap-reading-overrides.yaml`、`dither=1.0` 和原有 Japanese MFA v3 声学/G2P 模型。

本次从官方 `Qwen/Qwen3-ForcedAligner-0.6B` 获取原生检查点，固定提交 `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`，安装于 `.runtime/models/qwen3-forced-aligner-0.6b`。`model.safetensors` 大小 1,835,544,544 字节；本地 SHA-256 与官方 LFS 元数据相同，均为 `47831d0e82f96b20e9034dba01a075ee06436654719f6a68289e49f1b65ce0e7`。`japanmfa check` 的 11 项运行与模型检查全部通过。真实 0060 的原生推理得到 `世界 0.48–1.20 s`、`大丈夫 2.00–2.88 s`。

## 实现与验证

默认 Qwen 模型自动读取项目 `.runtime/models` 的原生检查点，也保留显式环境变量和 Hugging Face 缓存路径。检查点预检校验 `qwen3_forced_aligner` 类型，避免把 ASR 或转换后的 `-hf` 模型误认为原生对齐器。

MFA 现在按 Qwen 词时间规划裁剪：长停顿在锁定词边界处分组；连续语音只在两侧有足够时长时细分；零时长词并入相邻语音。被长停顿隔开的极短词可获得受限上下文，但原始 Qwen 边界仍用于审计。即使整句只有一个词，也按其时间范围裁剪。MFA 决定裁剪内的音素边界，结果恢复到工作 WAV 时间轴；缺失、越界或文本不匹配的原生时间戳明确失败。相邻裁剪恢复全局时间时统一到微秒，消除了 0100 曾出现的 `4.640000000000001 > 4.64` 浮点伪重叠。

原生模型会把 `うぅ～ん` 对应到一个跨越内部 `～` 的词项。现在把 `～` 记为位置不精确的 `lexical_span` 标点证据，完整保留该词时间与原文；此前该情况使 0050 在 MFA 前直接报错。ASR 批量词读音合并也接受这种词内标点。

修正后测试：`PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q -m 'not real_models'`，**368 passed，15 deselected**；`git diff --check` 通过。另有原生 ForcedAligner 对真实 0060 的直接推理、原生工作进程对 0050 的推理，以及上述七条完整音频流水线回归。测试通过不等于人工音素金标验证。

## 七条最终结果

| 样本 | 状态 | 关键证据 |
| --- | --- | --- |
| 0050 | `timestamp_mfa_disagreement` | Qwen 整词 0.00–1.92 s，MFA 词 0.50–1.28 s；工作 WAV 前约 0.5 s 近静音。原生模型与标点投影均已运行。 |
| 0060 | `timestamp_mfa_disagreement` | `大丈夫` Qwen 2.00–2.88 s，MFA 到 2.56 s，尾部差 −0.32 s。2.65–2.85 s 仍有高能量。 |
| 0070 | `timestamp_mfa_disagreement` | 由 3 个语音组运行，短音素检查通过，但 `てるぅ／あぅ` 组 MFA 起点 4.75 s 对 Qwen 3.20 s，差 +1.55 s。 |
| 0080 | `aligned` | 单词 `風邪` 按 Qwen 裁剪后，`z/e` 分界 0.97 s；低能量音素与时间戳审计均无问题。 |
| 0090 | `timestamp_mfa_disagreement` | 短词 `うわ` 获得上下文后 MFA 词尾 5.54 s、Qwen 5.28 s，差 +0.26 s；5.30–5.45 s 仍有较高能量。上一轮无上下文的通过结果截短了此词，不能作为最终质量结论。 |
| 0100 | `timestamp_mfa_disagreement` | Qwen 给 `はぁ` 仅 0.48–0.56 s，原始 80 ms 裁剪使 MFA 无法生成特征；受限上下文修复后 MFA `/h aː/` 到 1.13 s，词尾与 Qwen 差 +0.57 s，短音素和低能量检查均无问题。 |
| 0110 | 历史 `aligned`，现已撤回 | 合成静音中有两段明显未覆盖的声音；修正后的质量检查拒绝发布。 |

历史批次汇总是 **2 aligned / 5 failed / 0 skipped**；经本次复核，可保留的成品只有 0080。五条历史失败均到达 MFA，随后在词边界一致性检查被拒绝。没有通过放宽阈值或延长 MFA 音素边界提高通过数。

0060 另做了单变量读音对照：保持同一裁剪音频与声学模型，只把 `大丈夫` 的 G2P `d a i ʑ oː ɯ b ɯ` 改为官方词典 `d a i ʑ oː b ɯ`。两次 MFA 词尾都在裁剪内 0.56 s，即全局 2.56 s。多余 `/ɯ/` 是读音错误，但单独删除它不能修复这条尾部错位。实验文件保存在 `.runtime/artifacts/0060-official-pron-20260928/`。

0110 另做了隔离裁剪实验：保持同一工作 WAV、词典、模型与 `dither=1`，仅将第二句 MFA 输入范围从 Qwen 的 1.92–2.88 s 扩为 1.75–3.36 s。MFA 的 `ない` 到 3.10 s，显式静音邻接边界的原有声能修正将最后 `/i/` 延至 3.25 s。实验保存在 `.runtime/artifacts/0110-tail-investigation-20260928/`。这说明原 Qwen 裁剪丢失了尾部声音，但实验结果没有人工音素金标，尚不能重新发布 0110。

## 仍需判断

原生模型已经正确接入，但这些游戏语音中的部分 Qwen 词时间也明显偏离声能。0050、0070、0100 的时间冲突不能靠强制拉伸音素边界解决；0060 尾部高能量是否全部为目标语音仍需听辨。需要人工词/音素金标或可信的独立声学锚点，才能决定失败样本应如何发布。共享成品目录目前只保留 0080 的 TextGrid。
