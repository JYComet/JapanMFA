# Galgame 预计算 CTC 时间戳输入

`tools/galgame_mfa_from_ctc.py` 从游戏目录的 `wav/`、`txt/`、`ctc/` 按文件名配对，默认选最前 10 个 WAV。`txt/` 是原文，`ctc/` 是同名、包含 `words` 与 `zero_duration` 轨道的 Qwen ForcedAligner TextGrid。零时长词点保留在词序列中；预检拒绝文本不一致、时间戳重叠或时长不匹配。

CTC 坐标以原 WAV 为时间轴。适配器只接受单声道、16 kHz、PCM16 WAV，逐字节复制到 MFA 工作区，保留长静音和样本数。默认 `--alignment-strategy hybrid` 在**一次 MFA 调用**中对所有完整 WAV 预生成整段与 CTC `speaker` 锚点两种候选；先逐条复核整段，只对边界/时间戳明显不合格的条目读取锚点候选。回退阶段也不裁剪 WAV。MFA 后的逐词融合只在 CTC/Sudachi 词界可对应、偏差 0.15–0.30 秒且声能支持时移动边界；大错位与零时长锚点不做音素比例拉伸。所有候选仍经声能、标点和四轨审计。此法参考旧项目 `scripts/run_pipeline.py::_build_native_anchor_corpus` 和 `scripts/postprocess_textgrids.py::_snap_to_ctc`，但未照搬中文特有的 `<unk>`/NVV/英文规则。保留 `--alignment-strategy timed` 供旧流程复查，不作为默认发布路径。这批 MFA v3 实测 G2P 对应的假名规则已补入音素映射表。词尾 `ッ` 在 G2P 完全漏出时补 `ʔ` 闭塞音候选，其他候选不改动。

示例：

```bash
PATH=/home/user/JapanMFA/.runtime/envs/mfa/bin:$PATH \
MFA_ROOT_DIR=/home/user/JapanMFA/.runtime/mfa-root \
JAPANMFA_TDMELODIC_COMMAND='docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb' \
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python tools/galgame_mfa_from_ctc.py \
  /mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu \
  --limit 50 --alignment-strategy hybrid \
  --config runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml \
  --output /mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/mfa \
  --run-dir runs/galgame-hybrid-next-run
```

合格结果以同名 `.TextGrid` 和原始 `.wav` 配对发布到 `--output` 指定的目录；此参数必须显式给出，且不得指向源游戏目录内部。`run-dir/input` 是输入快照；`batch-dual/combined/` 是一次 MFA 调用的双候选语料；`pipeline-whole/`、`pipeline-anchored/` 分别保存被审查的候选及其后处理诊断；`preflight.json` 记录输入哈希，`hybrid-report.json` 记录单次 MFA 耗时、逐条状态、候选选择和发布状态。输出目录中的 `hybrid_run_report.json` 是该报告的副本。未通过管线或发布审计的样本不冒充合格结果；已有合格 TextGrid/WAV 会保留，即使新试跑退化。当前累计发布状态应以 `mfa/current_status.json`、`mfa/mfa_run_report.json` 及 `mfa/mfa_audit.json` 为准，单次 `hybrid_run_report.json` 只描述该次试跑。

2026-09-29 扩测按文件名选源目录前 **50** 条：复用哈希未变化的前十条，新增四十条实际运行，结果为 **37 组发布、13 条筛选**。共享成品及总报告在 `/mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/mfa/`；未通过项、原 WAV/TXT/CTC 和逐条证据在同项目 `filtered/`；本轮完整运行归档在 `diagnostics/first50-20260929.tar.zst`。总报告 `mfa_run_report.json` 有完整 50 条选择顺序、输入哈希、每次尝试和失败原因；`mfa_audit.json` 对 37 组成品复核为 0 失败。问题与声能时间坐标持续记录在[统一问题台账](alignment-issues.md)。

本轮按用户要求把 `<15 ms` 的音素改为诊断项，不再仅因该门槛筛除；`postprocess.json.short_phone_issues` 仍保留。原先仅因此被筛掉的 `air_0008` 重跑后通过，旧失败证据移至 `diagnostics/historical-filtered/`。停顿漏声和 CTC/MFA 时间戳冲突仍会拒绝发布。对前 50 条扩展后的 MFA v3 音素映射已用新增四十条的 442 个词项、206 种读音核对，未映射项为 0。

若将样本拆成多个**并行进程**，每个进程必须使用独立的 `MFA_ROOT_DIR`；MFA 会在该目录解包模型和维护 G2P 工作文件。该批第一次并行尝试共用目录，曾使 `air_0020`、`air_0043` 的命令失败；使用独立根目录重跑后未复现。单进程按 `--limit 50` 顺序执行不涉及此并行冲突。

2026-09-30 尾词声能延伸定向重跑后，`air_0045`、`air_0049` 新增为合格配对，阶段状态为 39 组发布、11 条筛选。随后整段优先、完整 WAV 加 CTC 锚点回退试跑新增 `0016`、`0024`、`0025`、`0033`、`0037`、`0043` 六组；单进程双候选重跑又修复 `0020` 的两处短停顿漏声。**当前累计 46 组发布、4 条筛选**，共享审计 **46 files / 0 failed**，原 45 组哈希未变。旧失败包移至 `diagnostics/historical-filtered/`；当前四条失败的源 WAV、文本、CTC 和原因仍在 `filtered/`。上面的 37/13、39/11、45/5 均为历史回执。详细复现和比较见[统一问题台账](alignment-issues.md)。
