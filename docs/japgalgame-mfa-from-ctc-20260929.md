# Galgame 预计算 CTC 时间戳输入

`tools/galgame_mfa_from_ctc.py` 从游戏目录的 `wav/`、`txt/`、`ctc/` 按文件名配对，默认选最前 10 个 WAV。`txt/` 是原文，`ctc/` 是同名、包含 `words` 与 `zero_duration` 轨道的 Qwen ForcedAligner TextGrid。零时长词点保留在词序列中；预检拒绝文本不一致、时间戳重叠或时长不匹配。

CTC 坐标以原 WAV 为时间轴。适配器只接受单声道、16 kHz、PCM16 WAV，逐字节复制到 MFA 工作区，保留长静音和样本数。管线使用已有分段 MFA、声能审计、标点与停顿同步逻辑；这批 MFA v3 实测 G2P 对应的假名规则已补入音素映射表。词尾 `ッ` 在 G2P 完全漏出时补 `ʔ` 闭塞音候选，其他候选不改动。

示例：

```bash
PATH=/home/user/JapanMFA/.runtime/envs/mfa/bin:$PATH \
MFA_ROOT_DIR=/home/user/JapanMFA/.runtime/mfa-root \
JAPANMFA_TDMELODIC_COMMAND='docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb' \
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python tools/galgame_mfa_from_ctc.py \
  /mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu \
  --limit 10 \
  --config runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml \
  --run-dir runs/galgame-akabei-first10-20260929
```

合格结果以同名 `.TextGrid` 和原始 `.wav` 配对发布到游戏目录下的 `mfa/`。本地 `run-dir/input` 是 10 条输入快照，`pipeline/` 保存每条中间产物，`preflight.json` 记录输入哈希，`report.json` 记录逐条状态与发布哈希。未通过管线或发布审计的样本不冒充合格结果；如果覆盖不同的旧发布文件，旧文件先保存到 `run-dir/before/`。
