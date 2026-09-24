# 0922jap 声能边界微调复查（2026-09-24）

## 旧代码依据和实现范围

依据旧仓库固定提交 `c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85` 的 `scripts/postprocess_textgrids.py`：`_refine_boundaries_by_energy` 使用全音频 10 ms RMS、低能量分位数、局部起点/终点搜索；末端 BGM 检测在处理后的静音区间使用 50 ms 窗口、25 ms 步长，并要求至少 20% 窗口超过阈值。旧代码的 CTC 锚点和中文词修复不具备本项目所需的日语词级定时证据。

本项目在 `postprocess_annotations` 中对**显式 MFA 静音与相邻语音音素**做声能微调：静音后的语音起点最多回拉 120 ms；语音后的静音起点最多在 500 ms 内寻找连续能量回落。必须观察到边界附近连续有声及三帧连续低能量，且不能跨越明显静音段。内部语音音素边界不动。修正同时写入 `postprocess.json.energy_boundary_refinement`、三条音素轨和最终 `words` 轨。BGM 检测使用修正后的显式静音区间及旧仓库的逐帧规则；没有 MFA 显式静音时不把合成分区当成可否决证据。

这是旧管线声能规则的**日语音素级适配**，不是把旧 `_refine_boundaries_by_energy` 的整个中文词级逻辑直接运行。逐帧能量只能定位明显起落，不能确定长距离错位中每个词或音素的归属。

## 两种模式的最终全量复跑

输入仍是 `\\RS3621\Research_TTS\Data\Raw\0922jap` 挂载 `/mnt/Raw/0922jap` 的 7 组 OGG/TXT。无参考模式使用先前按原字节复制的仅 OGG 目录 `.runtime/0922jap-no-reference-20260924`。使用同一 `/tmp/japanmfa-real-config.yaml`、tdmelodic 容器、MFA/OpenFST 环境分别完整执行 `japanmfa run`。

| 样本 | 参考文本 | 无参考文本 |
|---|---|---|
| 0050 | `reading_mismatch` | `bgm_suspect` |
| 0060 | `bgm_suspect` | `bgm_suspect` |
| 0070 | `reading_mismatch` | aligned |
| 0080 | aligned | aligned |
| 0090 | `malformed_output` | `malformed_output` |
| 0100 | `reading_mismatch` | `bgm_suspect` |
| 0110 | `bgm_suspect` | `bgm_suspect` |

- [参考模式完整输出](/home/user/JapanMFA/runs/0922jap-energy-ref-final-20260924)：**1 aligned / 6 failed / 0 skipped**。
- [无参考模式完整输出](/home/user/JapanMFA/runs/0922jap-energy-no-ref-final-20260924)：**2 aligned / 5 failed / 0 skipped**。

较旧版平均能量 BGM 检查，无参考模式的 0050、0100 新增拒绝：0050 的 0.98–2.38 秒显式静音有 22.2% 高能量帧；0100 的 2.67–4.10 秒和 5.41–6.27 秒分别有 32.1% 和 24.2%。这些是修复漏检造成的结果变化，不能解释为模型退化。参考模式的 3 条 `reading_mismatch` 和 0090 的 `malformed_output` 是上游读音/重音问题，声能边界步骤无法改变它们。

## 失败原因实测

- **0060**：MFA 显式静音 0–1.22 秒和 1.44–2.64 秒覆盖大段高能量内容。回拉后第二段起点只到 2.60 秒，两段仍有 **40.4% / 46.7%** 高能量帧。旧函数的局部搜索也不足以给这些远离相邻音素的内容确定词和音素标签，因此保留失败。
- **0110**：尾部静音起点原为 **2.91 秒**，声能持续至约 **3.29 秒**；新步骤将末尾 `i` 音素终点和静音起点同步改为 3.29 秒。但中间显式静音 **1.28–2.43 秒** 仍有 **31.1%** 高能量帧，故仍是 `bgm_suspect`。仅修好尾部不能发布整条结果。
- **0070 无参考**：末尾边界 3.35→3.71 秒，最终 `words` 的 `お` 和末尾标点 `。`、三条音素轨共用修正后的边界；该样本通过检查。0080 无边界修改。

旧 `REGRESSION_ARCHIVE.md` 中 Case 25 的长静音内持续内容漏检、Case 45 的末音素无条件拉长、Case 66 的派生轨不同步和 Case 205/207–210 的 BGM/CTC 证据分别用于检查：逐帧 BGM 测试覆盖持续能量，局部扫描和连续回落约束避免无条件延长，六轨输出与修正音素同步；CTC 缺失能力仍未宣称恢复。

## 验证

`python -m pytest -q`：**323 passed, 4 skipped**；`python -m compileall -q src` 与 `git diff --check` 通过。单元测试包括局部尾部延长、远处能量不强行归属、静音内持续声能不被平均值掩盖，以及 `words`/音素边界同步。失败样本保留 `postprocess.json` 诊断，不发布最终 TextGrid 和完成标记。

## 交付后复查：0070 时间戳失配

用户在共享目录查看 TextGrid 时报告严重偏移。复查确认本报告上方的“0070 无参考 aligned”是**当时程序的误放行结果**，不能当作有效对齐：无参考 Qwen 文本为 `目の前がぐるぐるしてお。`，而源 TXT 为 `目の前がぐるぐるしてるぅ……あぅ`；MFA 最后一个词原始结束于 3.35 秒，局部声能延长后为 3.71 秒，但工作 WAV 在 3.905–4.14 秒、4.82–5.165 秒等区间仍有持续声能。旧 BGM 阈值没有覆盖较轻的末尾内容。

新增旧管线 `find_speech_in_silence` 参数启发的末尾覆盖检查：在最后一个 MFA 语音音素后的显式静音里，按 5 ms RMS、局部噪声 2.5 倍和峰值 15% 阈值查找与前词分离的连续声能；命中时记录 `postprocess.json.unowned_speech_regions` 并以 `alignment_acoustic_coverage` 拒绝发布。对保存的 0070 原始 MFA/音频产物回放后得到该原因；两种模式的 0080 均未误触发。共享目录中此前复制的 0070 TextGrid 及配套 WAV 已核对哈希后撤回；0080 随后也因下述音素错位撤回。历史运行目录保留供诊断，尚未用并行开发中的 Qwen ForcedAligner 变更重新执行全管线。

另一个独立的时间轴问题：MFA 处理的是经过静音补全的工作 WAV，不是源 OGG。原生音频数组比对显示 0080 的工作音频相对 OGG 前移入约 **0.384 秒**补全静音，0070 约 **0.407 秒**。因此以上 TextGrid 必须与同目录的处理后 WAV 配对；直接套用在原 OGG 上会产生近似该幅度的整体偏移。最终词区间来自 MFA 原始 `words` 轨，Qwen 在该批输出里提供的是识别文本；当时没有用 Qwen 词级时间戳覆盖 MFA 边界。

## 再次复查：0080 MFA 音素落在空白

用户提供的 Praat 截图显示总时长 **1.590625 秒**，即配套工作 WAV 的时间轴；因此这次问题不能归因于误用原 OGG。参考和无参考模式的 MFA 原始音素区间完全一致：`k` 0.50–0.53 秒、`a` 0.53–1.08 秒、`z` 1.08–1.11 秒、`e` 1.11–1.14 秒。`postprocess.json.edits` 为空，边界微调未移动它们。实测 `/a/` RMS 为 **0.106899**，`/z/` 为 **0.000660**，`/e/` 为 **0.000134**；末尾音素确实由 MFA 放到了接近静音的位置。整体 OGG/WAV 偏移只解释另一种查看方式，不解释截图中的词内错误。

新增窄范围 `phone_in_silence` 检查：在显式静音前的末尾 `/a,e,o/` 音素若相对同词先前元音明显低能量，则拒绝发布；`/i,ɯ/` 可能清化，不以同一规则推断。两种 0080 保存产物回放均得到 `phone_in_silence`，0070 仍为 `alignment_acoustic_coverage`。共享目录里两种模式的 0080 TextGrid 和 WAV 已核对哈希后撤回，**当前共享目录没有可发布的 TextGrid**。此前全量运行的 `aligned` 数量是当时检查器的历史记录，已被这些实测证据否定；需要带可信词级时间锚点的新对齐及重新全量验收，不能把旧结果继续交付。
