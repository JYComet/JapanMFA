# ASRMFA 后处理日文移植与 0922jap 实测（2026-09-24）

## 来源与范围

旧项目依据：[ASRMFA--Pure](https://github.com/JYComet/ASRMFA--Pure/tree/c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85)，固定提交 `c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85`。逐项对照了 `scripts/trim_silence_batch.py`、`scripts/pad_silence_edges.py`、`scripts/postprocess_textgrids.py`、`scripts/finalize_textgrids.py` 和 `REGRESSION_ARCHIVE.md`。适用于日语 MFA 的原生采样率裁剪、首尾静音补全、静音等级、短音素/结构/BGM/词能量检查和首条 `<sp1>` 规则已接入。MFA 音素边界不凭空移动。

正式 TextGrid 有 `original`、`kana`、`words`、`phones`、`phone_kana`、`phone_tone` 六轨。`original` 和 `kana` 的完整标签前加 `<sp1>`；`words` 按真实 MFA 词间正时长间隙，使用原文本标点代替原 `<spN>`。没有间隙的原标点留在全文标签并记入 `postprocess.json.punctuation_unplaced`。下三轨共用原 MFA 音素边界和静音标签。发布时配套保存与 MFA 输入字节相同的处理后 WAV。

日语 MFA G2P 的多个候选现在全部写入同一 occurrence alias 的词典，由 MFA 选择，投影必须与实际选中音素精确相等。音素映射仅添加本批语料真实 G2P/MFA 输出证实的日语规则。常见日语波浪号 `～`、`〜` 视作标点，其他未支持 Unicode 符号仍显式跳过。

## 输入和运行环境

- 用户指定的 `\\RS3621\Research_TTS\Data\Raw\0922jap` 挂载为 `/mnt/Raw/0922jap`，本次有 **7 组 OGG/TXT**，不是先前报告里的五条 WAV。
- 有参考文本：直接读取该目录的 OGG/TXT；原 TXT 为权威文本，Qwen 仅作语言/差异审计。
- 无参考文本：把七条 OGG 按原字节复制到项目自有的 `/home/user/JapanMFA/.runtime/0922jap-no-reference-20260924`，不放 TXT，由 Qwen3-ASR 提供文本。
- 运行时使用已有 Qwen3 1.7B、tdmelodic 容器 `japanmfa-tdmelodic:e7fdb63f85bb`、MFA 3.3.9 与本地 `MFA_ROOT_DIR`。MFA/OpenFST 的 bin 目录加入 PATH。
- 所有读入 OGG 与输出 WAV 的 SHA-256 与 `audio.json` 收据匹配；七条无参考副本与原 OGG 哈希相等。原始目录无写入。

## 最终全量结果

| 样本尾号 | 有参考文本 | 无参考文本 |
|---|---|---|
| 0050 | failed: `reading_mismatch` | aligned |
| 0060 | failed: `bgm_suspect` | failed: `bgm_suspect` |
| 0070 | failed: `reading_mismatch` | aligned |
| 0080 | aligned | aligned |
| 0090 | failed: `malformed_output` | failed: `malformed_output` |
| 0100 | failed: `reading_mismatch` | aligned |
| 0110 | failed: `bgm_suspect` | failed: `bgm_suspect` |

- 有参考文本输出：[runs/0922jap-upstream-ref-final-v2-20260924](/home/user/JapanMFA/runs/0922jap-upstream-ref-final-v2-20260924)，**1 aligned / 6 failed / 0 skipped**。
- 无参考文本输出：[runs/0922jap-upstream-no-ref-final-v2-20260924](/home/user/JapanMFA/runs/0922jap-upstream-no-ref-final-v2-20260924)，**4 aligned / 3 failed / 0 skipped**。
- 每一条完成状态都有独立 manifest 行；所有失败项没有最终 TextGrid 或完成标记。没有把模型/对齐失败冒充成功。

参考模式 `0080` 的 `original` 是 `<sp1>風邪？`，`words` 为 `<sp1>`、`風邪`、`？`；无参考 `0050` 则由 Qwen 识别为 `うん。`，`words` 为 `<sp1>`、`うん`、`。`。两模式语义不同，未用参考 TXT 替换 ASR 输出。

## 静音、结构及异常记录检查

将旧仓库的裁剪和首尾静音函数与本仓库移植函数直接运行在七条解码 OGG 的相同原生采样率数组上，七条的裁剪数组及补全数组均逐样本相等。最终五份合格 WAV 均为单声道 PCM16、16 kHz；按照旧检测阈值在最终 WAV 上复测，首尾静音均为约 0.448–0.512 秒（1024 样本帧分辨率）。五份 TextGrid 都可独立解析并通过完整分区/六轨校验；原文前缀、原标点、三条音素轨边界、WAV 帧数/时长和哈希均与 JSON 收据一致。

旧 `REGRESSION_ARCHIVE.md` 的正式索引共 257 条（编号 1–258，原文缺 242），已在 [适用性清单](upstream-regression-applicability-20260923.md)逐行保留。与本次相关的 19–22、25、27–29、39、221、223 和 BGM 条目有针对性核查；Case 221 的 15 ms 序列化微秒边界已有红绿测试。Case 223 的 `--dither 0.0` 命令有契约测试，但 MFA 日志未暴露实际 MFCC 参数，因此没有把历史生产级结果标为已验证。

## 仍未完成的旧管线能力

旧项目的 CTC/Qwen ForcedAligner 时间侧车、NVV 证据、CTC 锚点边界修正和 CTC 间隙 BGM fallback 不存在于当前日语管线，不能直接运行其依赖这些数据的原始步骤。当前只在 MFA 提供真实词间静音时给原标点时长；其他原标点不猜测时长。参考模式里 `うぅ`、`てるぅ` 等被 tdmelodic 改写了小假名读音，`熱` 输出重复降调标记，这些没有擅自变成 H/L。0060 和 0110 的 MFA 显式静音含明显能量，BGM 检查保留拒绝。仍需独立的模型读音/时间证据和人工复核，才能安全增加合格率。
