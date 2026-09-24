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
