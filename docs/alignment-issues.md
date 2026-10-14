# 对齐问题与校对记录（持续追加）

本文件是 JapanMFA 对齐、音素、标点、停顿及发布结果的统一问题台账。后续发现的问题均在此追加：同一根因追加复现与验证记录，不另建互相冲突的问题清单；保留已关闭问题及历史错误结论，不覆盖原始证据。独立测试报告可以作为附件链接。

每条记录至少包含：编号、发现日期、样本/路径、症状与时间坐标、原始证据、根因、调整规则、测试命令、复现结果、当前状态及未解决范围。自动声能检查通过不代表每个词内音素边界均有人工金标。

## 本次范围和证据

- 日期：2026-09-28；用户截图样本：`01-00-a00-0110__0verflow_Shiny_Days`。
- 用户目录：`\\RS3621\Research_TTS\Data\Raw\0922jap\textgrid_native_qwen_20260928`；本机挂载：`/mnt/Raw/0922jap/textgrid_native_qwen_20260928`。
- 修复前快照及 SHA-256：[before](../runs/0922jap-pause-review-20260928/before/)。包含七个 WAV 和两个已发布 TextGrid；原始 OGG/TXT 未改动。
- 基线审计：[audit-before.json](../runs/0922jap-pause-review-20260928/audit-before.json)。两个已发布文件均能复现本次结构问题。
- 当前共享文件与截图有版本差异：截图 0110 尾音提前落入 sp；本次开始时共享文件已将末音素延到 3.29 s。不能把新旧结果混为同一版本。
- 上游参考：[操作交接](</mnt/local_E/MFA_Pause/repo/handoffs/20260917T112752Z-qwen3-0915all-operational-handoff.md>)、`scripts/postprocess_textgrids.py::_resolve_visual_short_silence_merges`、`scripts/audio_energy.py`。上游按完整连续停顿作决定、保护标点归属、同步派生轨道并保存原始坐标。日语项目沿用这些原则，不照搬中文读音规则，也不凭低能量重划清辅音、清化元音或词内相邻音素。

## 问题索引

| 编号 | 问题 | 样本 | 状态 |
| --- | --- | --- | --- |
| JA-001 | 尾音落在静音内 / 裁剪丢失声学上下文 | 0110 | 已修复；历史版本可复现，新版不复现 |
| JA-002 | 显式静音与补出的静音相邻，重复 sp | 0080、0110 | 已修复；回归通过 |
| JA-003 | words 标点未同步到三条音素轨 | 0080、0110 | 已修复；回归通过 |
| JA-004 | 静音分片使尾音延伸被跳过 | 0050、0090、构造用例 | 连续停顿与长衰减规则已修复；0090 独立声岛仍拒绝 |
| JA-005 | 合成句首静音没有参与起音回拉 | 0110 | 已修复；回归通过 |
| JA-006 | Qwen/MFA 词时间冲突 | 0050–0110 | 最终四条通过、三条声能覆盖失败；原始冲突保留 |
| JA-007 | 单个 TextGrid 缺轨导致审计整批中断 | 构造缺少 phones 的文件 | 已修复，CLI 回归通过 |
| JA-008 | 全停顿声能审计与流水线局部检查覆盖不同，遗漏具体漏声边界 | 0050、0060、0070、0090 | 已修复检查盲区；剩余三条拒绝并记录具体坐标 |
| JA-009 | 历史 0080 Qwen 词尾无法由当前原生模型复现 | 0080 | 旧记录来源未确认；修复成品使用本轮原生 0.88 秒锚点 |
| JA-010 | 长尾音初版规则误吞较低音量的连续平台 | 构造反例 | 设计复核发现并修复；平台/阶跃下降回归通过 |
| JA-011 | MFA 尾元音多占短静音，造成时间戳误拒绝 | 0080、0100 | 已按可测安静边界回收，保留原始 MFA 坐标 |
| JA-017 | 无句尾标点的原文使末尾四条时间轨仍显示 sp | 0110 | 已修复；七条回放及发布后声能审计通过 |
| JA-018 | 旧项目短停顿向前合并规则未移植，0100 残留内部 sp0 | 0100 | 已修复；七条回放、四组声能审计通过 |
| JA-019 | 句中 sp1–sp3 的标点显示及原文插入遗漏 | 0100：2.58–2.79 s | 已按用户新规则修复；四轨及原文/假名同步 |
| JA-020 | 外部 CTC 使用原音频坐标，原预处理会改变时间轴 | Galgame 前 10 条；0004 长句首静音 | 已增加原轴输入适配与哈希校验 |
| JA-021 | 新语料的 MFA G2P 音素/莫拉规则覆盖不足 | Galgame 前 50 条 | 扩展至新增 40 条的 206 种读音；442 个词项复核 0 未映射 |
| JA-022 | 短停顿连续有声与分片起音被声能门槛误拒 | Galgame 0002、0003、0009、0011 | 已修复；四条真实 MFA 重跑、发布后审计通过 |
| JA-023 | CTC 文本未覆盖独立声段或 MFA 音素短于校验下限 | Galgame 0004、0007、0008 | 0008 已通过；0004 疑似原文外语气声、0007 为台词起点偏晚，仍拒绝 |
| JA-024 | Galgame MFA 成品误放在源游戏目录 | 首十条共享输出 | 已迁到 0922jap；原址误放目录已清理 |
| JA-025 | 并行 MFA 共用模型工作目录导致命令失败 | Galgame 0020、0043 | 独立 MFA_ROOT_DIR 重跑，命令错误未复现 |
| JA-026 | 扩测发现 CTC/MFA 词尾冲突及停顿漏声 | Galgame 0013–0049 | 0045/0049 已修复发布；当前 39 发布、11 筛选，其余逐项证据保留 |
| JA-027 | 时间戳冲突先拒绝，短独立声岛未进入停顿告警 | Galgame 0015：2.56–2.66 s | 新发现；保留拒绝，需改进诊断覆盖与重对齐 |

## JA-001：尾音与静音边界

历史根因是将 Qwen 1.92–2.88 s 当作硬裁剪，MFA 看不到后续声音。先前已扩大实际输入上下文为 1.77–3.33 s，保留 Qwen 原锚点，MFA 末音素原到 3.10 s，再按连续声能延伸至 3.29 s。见[上下文修复报告](test-report-acoustic-context-0922jap-20260928.md)。

本次直接测量配套 WAV：2.88–3.10 s RMS=0.187439；3.10–3.29 s RMS=0.064911；3.29–3.33 s RMS=0.000439，3.29 s 后完整 10 ms 帧最大 RMS=0.000665。尾部应保留到 3.29 s，不能把余下的安静段全延长给最后一个音素。截图选中的 2.21–2.30 s `/a/` 后为 `/s/`，属于相邻发音音素边界，不能仅凭 `/s/` 能量较低把它吞进 `/a/`。

历史错误版本也已实际重跑审计：[audit-historical-0110.json](../runs/0922jap-pause-review-20260928/audit-historical-0110.json)。确认其 `2.88–3.8045625 s` 静音内含 **0.34 s 连续强声能**；句首与第二句起音也被审计识别，共三个疑似漏音停顿。新检查能抓住已发生的问题，并非仅在修复后文件上自证通过。

## JA-002：连续 sp

修复前 0080：`1.09–1.12 <sp0>` 紧邻 `1.12–1.590625 <sp1>`。0110 句间：`1.17–1.20 <sp0>`、`1.20–1.77 <sp2>`、`1.77–1.83 <sp0>`；句尾：`3.29–3.33 <sp0>`、`3.33–3.8045625 <sp1>`。

根因：MFA 裁剪内的显式静音和全音频补齐的静音直接逐段导出，每段分别分类。修复在发布阶段合并连续静音；不删除/合并发音音素。按总时长分类，句首保持 `<sp1>`，有标点归属则显示原文标点。原始静音片段仍留在 `postprocess.json`，发布的 `alignment.json` 使用最终合并区间。

## JA-003：标点不一致

根因：`build_word_intervals` 只在 words 投影标点，音素导出器把每个静音重新写成 sp；旧校验只检查三条音素轨彼此一致，没检查 words 标点。

修复：先以最终音素归属构建 words，再由同一停顿区间投影 phones、phone_kana、phone_tone。标点必须匹配整个真实静音区间，不能覆盖语音；当时的规则是原文没有标点则保留 sp。此句尾规则已按用户后续要求由 JA-017 修订。original/kana 继续保留整句原文及读音。无实际间隙的标点仍记入 `punctuation_unplaced`，不为显示标点切走真实语音。发布校验拒绝相邻停顿、跨轨标点/停顿标签或坐标不一致。

## JA-004：静音分片阻止延伸

根因：原能量扫描只检查紧邻的单个显式静音；第一片不足 50 ms 即跳过，即使后面紧接静音且波形连续。

规则：以连续显式静音片段形成的完整范围扫描；沿用全局 10 ms RMS，阈值 `max(3 × 全音频第15百分位RMS, 0.001)`。边界两侧需至少两个连续活跃帧，候选终点需三个连续安静帧，最多向后扫描 0.5 s，至少移动 20 ms，保留至少 30 ms 静音。消耗掉的静音碎片移除，未消耗区间保留；不越过下一发音音素或安静间断去捕获另一声岛。候选坐标必须用实际全局帧原点计算，不用非整帧旧边界加帧偏移。

## JA-005：起音漏入合成句首静音

复现：0110 句首静音到 0.56 s，里面有约 30 ms 达到语音强度的帧，10 ms 帧峰值 RMS=0.092030。现有后处理只看显式 MFA 静音，漏掉首个音素前补出的静音。

规则：仅为首音素创建临时句首静音候选，用既有起音规则向前检查最多 120 ms：三帧安静后紧接两帧活动，音素内也需活动支持，移动至少 20 ms。只复制回音素起点；临时静音不冒充 MFA 显式静音，仍接受合成静音覆盖检查。不得全局补齐后无条件延伸句尾，否则会把裁剪丢失的一整段话错误拉进最后一个音素。

## JA-006：未通过样本

历史 0050、0060、0070、0090、0100 均因 `timestamp_mfa_disagreement` 未发布。五条的逐项原因见[原生 Qwen 报告](test-report-native-qwen-0922jap-20260928.md)和[上下文复核](test-report-acoustic-context-0922jap-20260928.md)。本轮应重新记录这五条的状态，不以降低能量或时间戳门槛提高通过数。是否重新进行词内声学对齐属于后续校对工作，不能把本次停顿修复等同于这些样本已经合格。

## JA-007：审计坏文件隔离

代码复核发现审计器在缺失 phones/phone_kana/phone_tone 时先读取字典而抛 KeyError，使整个目录没有报告。已在读取轨道前检查必需轨道，把坏文件记录为单文件失败，并继续检查其余文件。两文件缺轨 CLI 回归已证明会生成 `files=2, failed=2` 报告并返回非零状态。

## 复现与防回归命令

```bash
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q -m 'not real_models'
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python tools/audit_textgrid_pauses.py \
  /mnt/Raw/0922jap/textgrid_native_qwen_20260928 \
  --output runs/0922jap-pause-review-20260928/audit-published.json
```

审计同时检查配套 WAV 时长、连续停顿、四轨标点归属、停顿中的持续声能，以及停顿边缘至少 20 ms 的活跃帧。能量阈值为 `max(0.02, 0.25 × 已归属语音帧RMS中位数)`，用于发现可能漏音，不用于凭空识别音素。非零退出码或新发现必须追加到本文件，不得仅覆盖上一份 JSON。

## 2026-09-28 旧时间戳回放验证与交付回执

- 自动测试：**388 passed / 15 deselected**（未运行该组 real_models 测试；另执行下述真实 MFA 回归）。[测试日志](../runs/0922jap-pause-review-20260928/tests.log)，`git diff --check` 通过。
- 七条原始样本的 OGG/TXT 共 14 个输入与源目录逐一哈希相等：[输入哈希](../runs/0922jap-pause-review-20260928/input-hashes.json)。复用已保存的原生 Qwen 时间戳，重新运行真实 MFA、投影和后处理：[运行汇总](../runs/0922jap-pause-fix-replay-20260928/summary.json)。结果为 **2 aligned / 5 failed**；0080、0110 通过，其余五条仍为 `timestamp_mfa_disagreement`，本轮没有将它们发布为合格结果。
- 最终代码再次从本轮真实 MFA 结果重放。重用前逐字节校验每个裁剪 WAV、LAB 和词典，两个新 TextGrid 与首次回放字节相同：[最终代码重放日志](../runs/0922jap-pause-review-20260928/verify-fresh.log)、[已验证产物](../runs/0922jap-pause-fix-verified-20260928/)。这里使用记录的模型输出，不宣称重新调用了 Qwen 推理。
- 0080 的 `1.09–1.590625 s` 现在四轨统一为 `？`。0110 的 `1.17–1.83 s` 四轨统一为 `。`；`3.29–3.8045625 s` 四轨统一为单个 `<sp2>`。
- 0110 首音素 **0.56→0.50 s**：0.50、0.51、0.52 s 帧 RMS 分别约 0.001150、0.001361、0.002637，0.53 s 起强起音明显；回拉后句首静音的最大 10 ms RMS 约 0.000556。末音素仍按能量从原 MFA **3.10→3.29 s**。原始 Qwen/MFA 坐标和调整原因均保留于 `postprocess.json`。
- [声能与边界对照图](../runs/0922jap-pause-review-20260928/0110-energy-comparison.png)。图中橙色区域为发布停顿，灰色为波形，蓝色为 10 ms RMS；展示当前共享基线与修复结果，不能误称为历史截图那一版的完整对比。
- 修复前两个文件均失败；修复后和共享目录重新打开检查均为 **2 files / 0 failed**：[修复后审计](../runs/0922jap-pause-review-20260928/audit-after.json)、[发布后审计](../runs/0922jap-pause-review-20260928/audit-published.json)。相邻停顿对数、跨轨标点不一致数、疑似漏音停顿数全部为 0。保护用例还确认：不得吞并音素、不得把标点覆盖到语音、不得跨安静段去合并独立声音、合成尾部缺失整段语音仍拒绝发布。
- 已更新用户共享目录中的 **0080、0110 两组 TextGrid/WAV**；原版在 `before/`，发布前后哈希在[发布回执](../runs/0922jap-pause-review-20260928/publication.json)。重建 WAV 与旧 WAV 采样率、样本数完全一致，最大差异为 2 个 PCM16 整数单位；为确保配套字节一致，发布本轮实际用于对齐的 WAV，未混用旧 WAV。详见[音频差异测量](../runs/0922jap-pause-review-20260928/working-audio-comparison.json)。差异具体来自哪一步解码/重采样尚未单独归因，不视为时间轴漂移。
- 运行环境记录：首次回放缺少 `JAPANMFA_TDMELODIC_COMMAND`，七条在 accent 阶段以 `command_start_failed` 退出；接回既有 `docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb` 后完成回归。初次日志保留在 `replay-runtime-setup-failure.log`，不计入最终对齐质量统计。
- 已在仓库 `AGENTS.md` 和 README 写入统一台账入口，后续新增问题及复现均应追加至本文件。

本轮真实回放复现命令（再次运行会更新对应项目运行目录；复查已发布成品优先使用上面的只读审计）：

```bash
PATH="$PWD/.runtime/envs/mfa/bin:$PWD/.runtime/envs/orchestrator/bin:$PATH" \
MFA_ROOT_DIR="$PWD/.runtime/mfa-root" \
JAPANMFA_TDMELODIC_COMMAND='docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb' \
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python \
  runs/0922jap-pause-review-20260928/replay.py
```


## 2026-09-28 13:45 UTC：全部七条原始音频全新推理与边界审计

**本次端到端结果为 1 aligned / 6 failed / 0 skipped，只有 0110 通过。** 与上一轮复用旧 Qwen 记录的 2/5 结果不同；两者口径必须区分。0080 本次也被时间戳冲突拒绝。六条失败均没有作为正式 TextGrid 发布。

### 范围与可复现证据

- 从 `/mnt/Raw/0922jap` 顶层重新复制全部七组 OGG/TXT；不将派生目录的补静音 WAV 重复作为原始输入。[输入及哈希](../runs/0922jap-full-boundary-audit-20260928T134532Z/input-hashes.json)。
- 使用新建的独立缓存，实际执行原生 Qwen ASR/ForcedAligner、tdmelodic、G2P、MFA、投影与后处理，没有注入之前的 Qwen/MFA 输出。[配置](../runs/0922jap-full-boundary-audit-20260928T134532Z/config.yaml)、[运行脚本](../runs/0922jap-full-boundary-audit-20260928T134532Z/run.py)、[最终汇总](../runs/0922jap-full-boundary-audit-20260928T134532Z/output/summary.json)、[逐条记录](../runs/0922jap-full-boundary-audit-20260928T134532Z/output/manifest.jsonl)、[代码哈希](../runs/0922jap-full-boundary-audit-20260928T134532Z/code-hashes.json)。
- 对全部七条 `postprocess.json.final_phones` 运行与主管线相同的 words/四轨导出函数，生成明确标记 **NOT_FOR_PUBLICATION** 的诊断候选；六条失败仍保持失败。这样可审计拒绝样本的声能/轨道，而不是将缺少最终 TextGrid 误算作检查通过。[诊断脚本](../runs/0922jap-full-boundary-audit-20260928T134532Z/analyze.py)、[七条完整分析 JSON](../runs/0922jap-full-boundary-audit-20260928T134532Z/diagnostics/analysis.json)。
- 0110 诊断候选与主管线正式 TextGrid 字节相同；正式 `alignment.json` 的音素标签与时间轴也逐项相同。
- 检查项目包括完整覆盖、正时长、重叠/空洞、相邻 sp、四轨标点及停顿边界、三条音素轨边界、word 与所属 phones 的包络、配套 WAV 时长、静音中的强声能，以及 `/a,e,o/` 元音中至少 50 ms 的连续低能量段。

### 逐条实测结果

| 样本 | 本轮流水线 | 停顿内声能 / 其它边界发现 | 轨道结构与同步 |
| --- | --- | --- | --- |
| 0050 | 拒绝：时间戳冲突 | 末音素到 1.28 s，但尾部仍有衰减声能；1.28–1.50 s 范围内累计 0.19 s 强帧，连续最长 0.13 s | 诊断候选同步 |
| 0060 | 拒绝：时间戳冲突，另有 BGM 疑点 | 2.65–2.86 s 的连续 0.21 s 声能落在末尾停顿；在约 2.56–2.60 s 的安静间断后重新起音，不能直接拉长前音素吞掉 | 诊断候选同步 |
| 0070 | 拒绝：时间戳冲突，另有 BGM 疑点 | 2.86–3.36 s 连续 0.50 s 声能落在中间停顿；另有弱些的活动，总计 0.60 s；末尾 5.12–5.15 s 又有 30 ms 活跃尾部 | 诊断候选同步 |
| 0080 | **本次新增拒绝：时间戳冲突** | Qwen 0.48–0.88 s，MFA 0.48–1.10 s；尾差 0.22 s。停顿能量检查未见漏声 | 诊断候选同步 |
| 0090 | 拒绝：时间戳冲突，另有 BGM 疑点 | 1.18–1.44、2.23–2.54、3.20–3.56、3.78–3.89 s 均有声能落入停顿；两个停顿累计强帧分别 0.57 s、0.47 s | 诊断候选同步 |
| 0100 | 拒绝：时间戳冲突 | `はぁ` 原 Qwen 词尾 0.56 s、MFA 1.13 s，差 0.57 s；本次停顿能量检查未发现额外漏声 | 诊断候选同步 |
| 0110 | **通过** | 首音素 0.50 s、末音素 3.29 s；此前起音、相邻 sp 与跨轨标点问题未复现 | 正式成品及 JSON 同步 |

全体候选的相邻停顿、跨轨标点不一致、word/phone 归属包络不一致及最终时间轴结构错误均为 **0**。没有命中上述 `/a,e,o/` 连续低能量筛查，但这不证明每个词内音素分界都准确，清辅音和清化元音也不能按能量最低点随意切分。

0050 的词内 `～` 与 0070 的一处 `……` 没有可分配的正时长词间隙，仍保留在 original/kana，并记录在 `punctuation_unplaced`；这与同一真实停顿四轨标签不同的 JA-003 是不同情况，不能为了让每处标点都有区间而切走语音。

[七条波形、RMS、频谱及音素边界图](../runs/0922jap-full-boundary-audit-20260928T134532Z/plots/)。橙色是停顿，红色是疑似停顿中的强声帧，第三行是实际候选音素区间。0050 的连续尾部、0060 的尾部声岛以及0090 的多段有谐波声音均可在图上复核。

### JA-004 补充复现：0090 裁剪边缘不足以确认静音

0090 的第一段显式静音为 1.18–1.55 s；末尾声音逐渐衰减，到 1.54 s 帧才降至约 0.0006 RMS。当前尾音调整只扫描显式静音范围，需要三个安静帧确认终点并保留 30 ms 静音；裁剪在 1.55 s 截止，后面实际安静的合成区间未参与确认，因此 1.18 s 的过早词尾没有移动。

这是上次“连续显式静音碎片”修复尚未覆盖的组合。后续应允许从完整连续停顿读取候选终点的安静证据，同时分别保留显式/合成来源；候选不得因此跨越新的发音段，也不能将整段合成尾部直接交给最后一个音素。

### JA-008：声学检查仍有覆盖盲区（待修复）

四条失败候选共出现六个疑似漏声停顿。主管线的 `synthetic_silence_speech_regions` 与 `unowned_speech_regions` 在本批全部为空；0060、0070、0090 虽另有 `bgm_suspect`，它们未以统一的覆盖问题记录这些实际边界。0050 连 BGM 疑点也没有，最终仅因时间戳冲突被挡住。

已定位到几种条件：

1. 合成静音检查先扣除显式 MFA 静音，因此显式静音中的漏声不在它的范围内。BGM 的整段比例/全局噪声规则不能替代按连续语音岛的覆盖审计。
2. `_unowned_tail_speech_regions` 只看最后语音之后的显式静音，并要求先有 40 ms 安静；它不负责 0050 连续被截掉的尾音，也不覆盖 0070/0090 的中间漏声。
3. 0050 在 1.28 s 后还有声音，按 0.001 阈值约到 1.89 s 才能确认安静；原 0.5 s 搜索到 1.78 s 即停止。保守地不移动不等于该边界已经正确，应该明确记录无法安全修复的覆盖错误。
4. 0070 的尾部 30 ms 小于合成静音检查的 150 ms 活跃时长门槛；本轮独立审计通过至少 20 ms 的边缘活跃检查发现它。

后续应在发布前对合并后的所有停顿运行统一覆盖检查，保留各原始来源；有持续强声能却不能安全修正时必须保留失败及具体声能坐标。对于 0060、0070、0090 的分离声岛和明显词内挤压，应重新做词组/音素声学对齐，不能只放宽时差阈值或一律延长最后一个音素。本轮记录了问题与证据，未将诊断候选当作已修复成品。

### JA-009：0080 旧原生时间戳无法复现（待核查来源）

旧回放记录中 `風邪` 为 0.48–1.12 s，本轮原生模型输出 0.48–0.88 s。对新工作 WAV 和上一轮工作 WAV 各独立调用两次同一原生检查点，**四次全部为 0.48–0.88 s**：[重复调用结果及输入哈希](../runs/0922jap-full-boundary-audit-20260928T134532Z/0080-repeat.json)、[复测脚本](../runs/0922jap-full-boundary-audit-20260928T134532Z/repeat_0080.py)。已有原文/假名对照实验也记录了 0.88 s。

因此不能把差异归因于新 WAV 的几个 PCM 量化单位，也不能用旧记录回放声称当前端到端仍可通过。旧 1.12 s 的具体运行来源尚未厘清；当前重复结果本身是稳定的。新 MFA 末端 1.10 s 与旧末端 1.09 s 相差 10 ms，两版停顿审计都未见漏声；新增失败是 Qwen/MFA 审计锚点不一致，而不是轨道不同步。0070 的 `ぐるぐる` 词尾也从旧记录 2.56 s 变成 2.48 s，但本轮分组范围及总体拒绝状态未改变。

### 验证范围与当前成品状态

- 非真实模型自动测试：**388 passed / 15 deselected**，[本次日志](../runs/0922jap-full-boundary-audit-20260928T134532Z/tests.log)；上述七条另实际完成真实模型全流程。
- 已有共享目录中的两个历史成品复查：**2 files / 0 failed**，无相邻 sp、轨道不一致或停顿能量异常：[共享目录审计](../runs/0922jap-full-boundary-audit-20260928T134532Z/shared-audit.json)。这只是当前成品的结构/能量检查，不抵消本轮 0080 的端到端时间戳失败。
- 本轮审计产物独立保存于 `runs/0922jap-full-boundary-audit-20260928T134532Z/`；未用失败候选覆盖共享成品。唯一新通过结果在 `output/01-00-a00-0110__0verflow_Shiny_Days/`。
- 逐音素发音真值没有人工金标；当前可以确认结构同步、上述声能落入停顿的问题及时间戳冲突，不能由 RMS 单独证明所有相邻发音音素的切点都正确。

## 2026-09-28：JapGalgame 批量时间戳问题

### JA-010：混合日英文本中的独立标点被误判为词

样本：`/mnt/Raw/JapGalgame/0verflow_Shiny_Days/{wav,txt}/02-00-b30-0170__0verflow_Shiny_Days`，原文为 `さ、Let's go!`。首轮工作进程两次记录 `forced aligner lexical mismatch with Japanese text`，未生成该条 TextGrid。Qwen 输出的项目依次含 `さ`、`Let`、独立的零时长撇号、`s`、`go`；旧的词序投影把撇号当作需要声学对齐的词，因而拒绝了合法的其余词序。

修复：仅将含词汇字符的 Qwen 项交给词序投影；标点仍由同名 TXT 原文保留，不为独立标点制造声学时长。回归测试覆盖这组输出。修正后重新对该条真实 WAV/TXT 调用原生模型，工作进程报告 `done=1, failed=0`；共享目录中的同名 TextGrid 可由 `praatio` 解析，`words` 的四个非空区间分别为 `さ` 0.48–0.72 s、`Let` 1.20–1.44 s、`s` 1.68–1.84 s、`go` 1.84–2.56 s。此项只证明模型词级时间戳被完整保存，未人工核对词内音素边界。证据保存在 `.runtime/jobs/japgalgame-ctc-punctuation-canary-20260928/`。

同根因复现于 `AKABEiSOFT3_CharaBration_Otome_wa_Koi_shite_Charabureru/txt/ali_10195__AKABEiSOFT3_CharaBration_Otome_wa_Koi_shite_Charabureru.txt` 的 `Let's go!`：旧批次拒绝独立撇号。修正代码对真实 WAV/TXT 单独重跑报告 `done=1, failed=0`，同名 TextGrid 可读取；正时长词为 `Let` 0.96–1.12 s、`s` 2.32–2.48 s，`go` 是 2.48 s 零时长点。它解决的是词序解析错误，`go` 的零时长仍需后续声学复核。运行证据在 `.runtime/jobs/japgalgame-ctc-english-canary-20260928/`。

### JA-011：重复台词的 Qwen 时间戳超出音频边界

样本：`/mnt/Raw/JapGalgame/Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei/{wav,txt}/AME010356_E02__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei`。TXT 为七次 `兄さん`，WAV 为 169152 帧、16 kHz，实长 **10.572 s**。八卡试验的工作进程记录 `Qwen word exceeds audio duration`。单独加载同一原生模型重跑，前五次 `兄さん` 全部为 0–0 s，后两次词项落在 12.32–14.72 s；最大越界 **4.148 s**。这不是毫秒级量化误差，不能截断到末尾或把零时长项拉长后当作有效时间轴。

当前处理：严格拒绝该条 TextGrid，保留失败记录供文本与音频内容复核。生成器错误信息已加入词、词尾和 WAV 时长，便于批量定位同类问题。其它可对齐的条目继续处理；若要修复这条，需要先确认实际语音与七次重复文本一一对应，再做局部声学重对齐。目前没有人工金标，尚不能确定是源文本不匹配、重复词导致模型退化，还是音频中有特殊声学干扰。

同一批次的 `CTS022527__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei` 也属于重复音节退化：WAV 为 6.6891875 s，TXT 连写十四个 `あ`；模型把最初两个字分配到 0.48–6.16 s，把多数后续字压成 6.16/6.24 s 的零时长，末尾还给出 6.88 s，超过音频约 0.191 s。该条继续拒绝，不按 0.191 s 的表面越界量简单裁剪，因为整条词级分配已经退化。

旧批次中同游戏 `ali_11649` 的重复 `行く`、`来ちゃう`、`ああ` 也触发越界；单独复测 WAV 6.833125 s，而模型给最后 `ああ` 6.88 s 且 14 个词项中 10 个为零时长，仍拒绝。`aka_10119` 旧批次报越界，单独复测的最大词尾变为 10.32 s（WAV 10.847125 s），但多个词被压成零时长并留下数秒空档。说明批次上下文可能影响该条模型输出，尚不能仅凭单条复测的未越界就认定可发布；具体机制未确认。

### JA-012：较长台词中 Qwen 词序错位，句读分段只能局部缓解

样本：同游戏的 `CTS060084__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei`，WAV 7.913625 s，TXT 为 `いつまでもお尻かかめてないで、ささと射精したらどうなの。`。整句推理在 `で、ささと射精` 附近输出 `で`、`と`、`ささ射精`，与原文词汇顺序不符，原始 TextGrid 因此拒绝。以 4.7 s 切分音频，分别对两段原文调用同一 Qwen 模型，可以让两段词序投影通过；但 `で`、`射精`、`たら` 仍被压成零时长。4.45–4.60 s 与 4.70–4.75 s 的 50 ms 帧 RMS 明显升高，4.7 s 恰在活动声段，不能把这次试验切点当作可信语音边界。

因此尚未发布该条分段候选。需先定位实际停顿或人工确认词边界，再决定是否用局部 Qwen 重对齐；不能因词序投影通过就认定时间戳准确。诊断裁剪音频位于 `.runtime/jobs/japgalgame-ctc-diagnostics-20260928/`，原始失败见 wave2 各卡错误日志。

同根因复现于 `AKABEiSOFT3_CharaBration_Otome_wa_Koi_shite_Charabureru/txt/ali_12018__AKABEiSOFT3_CharaBration_Otome_wa_Koi_shite_Charabureru.txt`。原文 `てめはささとお茶...`，模型在词汇字符第 12 位期望 `さ` 时输出 `と`，随后把 `ささ` 移到 `お茶` 后，属于词序错位而非标点问题。共享投影函数现会在失败日志写出首个分歧位置和两侧词汇片段，便于后续批量定位；该条仍拒绝。

### JA-013：音频主名带点时的输出名截断（代码发现，语料待复核）

合成复现：`game/wav/voice.alt.wav` 与 `game/txt/voice.alt.txt` 应生成 `game/ctc/voice.alt.TextGrid`；旧清单代码对去扩展名后的 `voice.alt` 再调用 `Path.with_suffix('.TextGrid')`，误得到 `voice.TextGrid`，可能与另一条音频冲突。修复为在完整主名后追加 `.TextGrid`；已经运行的旧清单由后续 `reshard` 步骤按 `stem` 自动修复，并在汇总中记录 `repaired_ctc_paths`。单元测试分别覆盖新清单和旧清单迁移。完整 6,423,108 对语料的重分片结果为 `repaired_ctc_paths=0`，本批未触发；这仍是已修正的代码缺陷。此问题只涉及文件映射，无语音时间坐标。

### JA-014：微秒取整后词尾可能超出 TextGrid 上界（代码发现）

合成复现：WAV 时长 1.0000004 s、Qwen 词尾 1.0000009 s，旧校验容许 1 微秒差，但序列化把文件上界写成 1.000000 s、词尾写成 1.000001 s；`praatio` 会暗中扩大读取结果的上界。修复为从音频时长和有效词尾统一向上取 6 位小数作为各轨上界，并避免取整后零长度的尾部空白区间。测试同时检查原始文件中的 `xmax` 和重新打开的词区间。实际 Qwen 时间戳通常以更粗刻度输出，本轮真实失败不是这个微秒问题；修复用于保证后续边界文件结构一致。

### JA-015：零时长词比例高的 TextGrid 不能直接作 MFA 声学锚点

样本：`/mnt/Raw/JapGalgame/Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei/ctc/CTS022013__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei.TextGrid`，对应 WAV 2.8750625 s、TXT `あ、あふん。`。Qwen 对两个词只给出 1.36 s 与 2.24 s 的零时长点；`words` 轨全程为空白。这是按原模型证据成功写出的结构有效文件，但无法提供正时长词段。wave2 已保存文件中固定种子抽取 256 条，21 条的零时长词占比至少 50%，6 条至少 75%；该样本是其中一条全零。抽样只覆盖一个游戏附近，不可外推全量。

处理：保留零时长点，不凭空扩充成词段；操作说明明确将“文件已生成”和“适合作 MFA 锚点”分开。后续使用这些 TextGrid 时，应先筛除没有正时长词段的文件，并对零时长比例高的文件做人工或声学复核。本轮未把它误报为 Qwen 词边界准确，也未修改其原始结果。

### JA-016：全角数字与半角模型输出的等价匹配

样本：`/mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/{wav,txt}/air_1600__AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu`。全量作业最初记录 `at character 4: expected='５' got='5'`，属于同一个数字的宽度形式差异，并非语音词序冲突。词序投影现只对单字符全角 ASCII 字母和数字做 NFKC 比较，返回的词面仍使用原 TXT 字符，不扩展任意兼容汉字或改变原文。单元测试覆盖 `５`/`5`，真实 WAV/TXT 重跑得到 `done=1, failed=0`；共享 TextGrid 可重新解析，`５` 的正时长区间为 2.88–3.20 s。全量监督器已平稳重启以加载修复；已生成文件按原子发布与目录缓存跳过。证据在 `.runtime/jobs/japgalgame-ctc-width-canary-20260928/`。

## 2026-09-29：修复方案与执行记录

本轮根据 2026-09-28 七条全新推理证据修复，旧产物保留不覆盖。代码修改前快照与哈希见 [本轮 before](../runs/0922jap-boundary-repair-20260929T062934Z/before/)。用户已要求自主设计、修复并测试。

### 方案

1. **统一停顿视图，保留来源。** 边界判定查看相邻发音音素之间的完整停顿，包括显式 MFA 静音及合成间隙；只修改有声能支持的音素边缘。记录原始坐标、显式区间和消耗范围，不把合成区间冒充 MFA 输出。
2. **区分连续尾音与独立声岛。** 声音必须从原边界连续延伸，遇到连续安静帧即终止，不能跨过安静间断吞并后一声岛。短合成边缘可有限修正；无法安全归属的活动保留具体坐标并拒绝发布。0050 长衰减尾部与 0090 显式/合成接缝作为回归样本。
3. **强声确认、弱声收尾。** 裁剪阶段用强声帧确认语音存在，以更低的噪声相关门槛确认连续尾部结束，避免把 0080/0100 的正常衰减误判成 Qwen/MFA 冲突。保留 Qwen 原锚点及 0.2 秒冲突阈值；以具体声学证据解释修正，不统一放宽门槛。
4. **所有停顿统一检查。** 发布前扫描完整合并停顿，检测中间持续声能和边缘短截音，同时保留 BGM 等独立诊断；流水线与独立 TextGrid 审计采用一致判定口径。
5. **分离声岛先验证重新对齐。** 对 0060 等进行隔离真实 MFA 试验，验证能否恢复音素分配；未通过声能、归属和轨道同步检查的候选不作为修复成品。
6. **从一个最终时间轴派生所有轨道。** words/phones/phone_kana/phone_tone 共享最终音素归属与停顿标点，不分别修补坐标。保留 raw/final 两套证据并检查 JSON 与 TextGrid 一致。

验收包括构造失败回归、全套非模型测试、七条真实音频重新推理、各样本波形/频谱与声能复核、相邻停顿/标点/轨道同步检查。尚未得到本轮验证结果前不标记上述问题已关闭。

### 已完成的实现与隔离试验

- `postprocess.py` 使用完整连续停顿作搜索窗口，保留原始音素索引与显式静音来源。纯合成尾部最多检查 120 ms；显式停顿通常为 500 ms；更长尾部只在 500 ms 后的 50 ms 平滑 RMS 持续低于原边界能量一半、且 800 ms 内确认连续三帧安静时允许延伸。静音两侧同时移动时使用已更新的有效边界，保留至少 30 ms，禁止交叉。
- 裁剪的强声支持后追加最多 200 ms 弱尾音检查，以 `max(3 × 全局15百分位RMS, 0.001)` 确认三帧安静。原始 Qwen 锚点及 0.2 秒阈值保持不变。
- 新增 `mfa/timing_review.py`：校验最终音素归属的词边界，同时在 `raw_timestamp_alignment` 保存原始 MFA 冲突。向内缩短 Qwen 区间只有在被移除范围全为安静帧、保留边界附近存在连续声能时才可获得支持；不会清除已有声学失败。0050 的 0–0.5 秒确实是全零补静音。
- 流水线和独立 TextGrid 审计共用 `_pause_acoustic_coverage`，报告完整停顿、全部活跃坐标、门槛及来源重叠。BGM 诊断仍保留，覆盖错误独立否决发布。TextGrid 本身不能恢复原始显式/合成来源，独立工具不伪造这些来源字段。
- 0060 两次真实 MFA 隔离试验：[降低静音声学权重](../runs/0922jap-boundary-repair-20260929T062934Z/probe0060.log)仍为末音素到 2.56 秒；[禁止可选静音](../runs/0922jap-boundary-repair-20260929T062934Z/probe0060-nosil.log)得到 `/b/` 2.53–2.85 秒、`/ɯ/` 2.85–2.88 秒，将声岛硬塞进长塞音，不能据此认定音素边界正确。这两组参数均未进入生产代码。
- 0070 [按锁定词拆分的隔离试验](../runs/0922jap-boundary-repair-20260929T062934Z/probe0070-split/result.json)将 `てるぅ` 恢复到 2.83–3.12 秒，再作能量后处理，仍在 3.71–4.67 秒停顿中累计发现 0.29 秒强声能。[试验后处理证据](../runs/0922jap-boundary-repair-20260929T062934Z/probe0070-split/postprocess.json)为 `alignment_acoustic_coverage` 失败；未把手写裁剪坐标当作通用修复。
- 自动化验证：`PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q` 为 **430 passed / 4 skipped**。四项跳过是需要显式配置的真实后端测试；本轮另跑全部七条真实端到端音频。[完整测试日志](../runs/0922jap-boundary-repair-20260929T062934Z/tests-full.log)。初次测试收集误扫 `before/tests` 备份而出现同名模块冲突，已把备份后缀改为 `.py.snapshot` 并保留路径映射、原始哈希；该失败不计为模型或对齐回归。


### JA-010：长衰减规则复核与修正

初版 800 ms 例外仅要求后半段能量低于原边界一半；复核构造了先较响、后接 700 ms 恒定低音量声段的反例，发现它会被误吞进前一个音素。因此初版及其运行结果不作为最终验收版本。

最终规则还要求从旧边界到候选安静边界至少十个非重叠 50 ms RMS 块：对数能量拟合斜率为负、R²≥0.8、末块/首块≤0.1、任意相邻块增幅≤1.5 倍，并继续满足 800 ms 上限、三帧安静和 30 ms 剩余静音。平台和末尾突然阶跃降低的两个反例均拒绝；实际 0050 的 R²约 0.931、末首比约 0.024，符合连续衰减。每次采用该分支均记录这些实测指标。能量形状仍不是逐音素人工金标。

### JA-011：短静音尾部回收

全新 MFA 中 0080 的 `/e/` 到 1.10 秒，但实测稳定安静从 1.08 秒开始；0100 的 `/aː/` 到 1.17 秒，但稳定安静从 1.15 秒开始。前者与 0.88 秒 Qwen 原锚点产生 0.22 秒偏差，不能通过简单扩大容差来掩盖。

最终只允许停顿前 `/a,e,o/`（含长元音）回收 20–80 ms 已确认静音，并保持至少 30 ms 音素：候选点前最后一帧必须活跃、前三帧至少两帧活跃，之后至少三帧安静且持续覆盖旧边界。允许衰减中一个弱帧，不把该弱帧单独当成结束点；候选也不能从窗口中间的既有长静音随意开始，以免把超出限制的错误部分回收。`/i,ɨ,ɯ/`、塞音及音素相邻边界不适用。本轮修正后分别到 1.08、1.15 秒；原始 1.10、1.17 秒仍在 `raw_phones` 和 `raw_timestamp_alignment`。

### 最终验收结果与证据

**七条最终结果为 4 aligned / 3 failed / 0 skipped。三条失败均为 `alignment_acoustic_coverage`，没有伪造全通过。**

本轮先在独立空缓存实际执行七条 Qwen ASR/ForcedAligner、tdmelodic、G2P、MFA，保留[原生推理阶段结果](../runs/0922jap-boundary-repair-20260929T062934Z/output/summary.json)。该阶段代码仍处于修订过程，结果为 2/5，不能拿它冒充最终规则结果。随后用最终完整流水线消费本轮原生模型输出：[最终执行脚本](../runs/0922jap-boundary-repair-20260929T062934Z/final_pipeline.py)、[最终汇总](../runs/0922jap-boundary-repair-20260929T062934Z/final/output/summary.json)、[最终代码哈希](../runs/0922jap-boundary-repair-20260929T062934Z/final-code-hashes.json)。复用前逐字节验证七个工作 WAV、十七个裁剪 WAV/LAB 和对应词典，共 58 条哈希证据，全部匹配[本轮真实模型输入](../runs/0922jap-boundary-repair-20260929T062934Z/final/model-input-verification.json)。这里没有使用 0928 的旧 Qwen 时间戳来替代本轮原生推理，也不宣称最后的后处理重放再次调用了 Qwen/MFA。

| 样本 | 最终状态 | 实测修正或剩余问题 |
| --- | --- | --- |
| 0050 | 通过 | 连续衰减尾音 1.28→1.89 秒；Qwen 起点 0.00→实际 0.50 秒之间全为零值补静音，有独立裁去静音的证据 |
| 0060 | 拒绝 | 2.65–2.86 秒连续声音仍落入末尾停顿；两次 MFA 参数试验未给出可靠音素归属 |
| 0070 | 拒绝 | 中间停顿含 2.86–3.36 秒连续声能及后续弱活动；尾部 5.12–5.15 秒强帧也被记录。其低能量尾部持续超过纯合成 120 ms 修正上限，不能只追到强帧终点就宣称正确 |
| 0080 | 通过 | `/e/` 从 1.10→1.08 秒；使用本轮原生 Qwen 0.48–0.88 秒。最终偏差 0.20 秒，未放宽阈值 |
| 0090 | 拒绝 | 第一尾音 1.18→1.54 秒已修正；2.23–2.54 秒仍在停顿内。第二词组更完整上下文令 MFA 的 `/i/` 到 3.57 秒，但这不证明词内重分配正确；另有 3.78–3.89 秒较短活动，保留全部活跃坐标，未据总计门槛未触发而认定无问题 |
| 0100 | 通过 | `/aː/` 从本轮原 MFA 1.17→1.15 秒；Qwen 0.56 秒之后的连续弱尾音有声学支持 |
| 0110 | 通过 | 首音素 0.56→0.50 秒，末音素 3.10→3.29 秒；此前 sp/标点不同步未复现 |

- 最终 `pytest -q`：**439 passed / 4 skipped**，[完整日志](../runs/0922jap-boundary-repair-20260929T062934Z/tests-final.log)。`git diff --check` 通过。四项环境显式启用测试的跳过与上述七条真实运行是两种验证，不混计。
- 对七条最终候选都导出诊断 TextGrid 并审计：[完整分析](../runs/0922jap-boundary-repair-20260929T062934Z/diagnostics/analysis.json)。四条通过者与流水线正式 TextGrid 字节相同，JSON 音素标签/坐标逐项相同；七条的相邻停顿、跨轨标点、结构和 word/phone 归属包络错误均为 0。三条失败中共四个停顿触发覆盖否决，未发布为合格数据。
- 已逐张查看[七条波形、RMS、频谱和音素边界图](../runs/0922jap-boundary-repair-20260929T062934Z/plots/)。这些是自动声能和结构校验及图形复核；仍不能保证所有词内音素分界均有人工作为金标确认。
- 合格成品写入新目录 `/mnt/Raw/0922jap/textgrid_native_qwen_20260929_fixed`（NAS：`\\RS3621\Research_TTS\Data\Raw\0922jap\textgrid_native_qwen_20260929_fixed`），包含 0050、0080、0100、0110 四组 TextGrid/WAV 及七条终态 manifest。原 0928 目录保留；[旧文件备份及哈希](../runs/0922jap-boundary-repair-20260929T062934Z/publication-before-hashes.json)、[发布回执](../runs/0922jap-boundary-repair-20260929T062934Z/publication.json)可追溯。

复核新目录：

```bash
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python tools/audit_textgrid_pauses.py \
  /mnt/Raw/0922jap/textgrid_native_qwen_20260929_fixed \
  --output runs/0922jap-boundary-repair-20260929T062934Z/audit-published.json
```

剩余范围明确为 0060、0070、0090 的音素/词归属恢复。通用边界修正与漏检问题已实现；这三条的重新对齐试验不足以建立可靠归属，继续保留失败与原始证据，不能把“阻止错误发布”写成“这三条已经对齐正确”。

发布后重新打开 NAS 文件审计为 **4 files / 0 failed**：[发布后审计](../runs/0922jap-boundary-repair-20260929T062934Z/audit-published.json)。最终复核同时确认 14 个原始输入哈希、58 条模型输入证明、七张分析图、四组发布文件哈希及旧目录文件哈希全部一致。

### JA-017：原文无句尾标点时，末尾停顿应显示标点（2026-09-29）

- 样本与复现：`01-00-a00-0110__0verflow_Shiny_Days` 的原始 TXT 为 `ううん。おなか空いてない`，没有句尾标点。先前发布成品在 `3.29–3.8045625 s` 这一真实安静区间的 words、phones、phone_kana、phone_tone 均为 `<sp2>`；这是四轨一致却仍不符合用户句尾标点要求的独立问题。旧 TextGrid/WAV、审计及 SHA-256 保存在[本轮发布前快照](../runs/0922jap-terminal-punctuation-20260929T081114Z/before/)和[哈希清单](../runs/0922jap-terminal-punctuation-20260929T081114Z/before.sha256)。
- 根因与规则：旧发布逻辑仅投影原文已有标点，缺句尾标点时按停顿长度分类为 sp。现在仅当原文无句尾标点、最终 words 区间确实为正时长安静停顿时，在**发布文本**的 original/kana 末尾补默认句号 `。`，重建 words 并投影到三条音素轨。原始 TXT、ASR 与前端词片段保持原样；已有 `？`、`……` 等句尾标点原样保留，没有末尾静音时不切走语音来制造标点。`postprocess.json` 的 `publication_terminal_punctuation` 记录推断的 `。`。
- 验证：新增回归先复现缺少句尾标点，再验证六轨末尾与四轨坐标一致。完整测试 **441 passed / 4 skipped**，`git diff --check` 通过。使用上一轮七条原生 Qwen/MFA 结果作哈希/PCM 核验回放，58 项模型输入对照通过；本轮没有重新推理 Qwen/MFA。七条终态仍为 **4 aligned / 3 failed**，失败样本 0060、0070、0090 均仍为 `alignment_acoustic_coverage`。四条候选中 0050、0080、0100 的 TextGrid 与发布前逐字节相同，只有 0110 改动：original/kana 以 `。` 结束，`3.29–3.8045625 s` 的四条时间轨均为 `。`。[回放结果](../runs/0922jap-terminal-punctuation-20260929T081114Z/verified/output/summary.json)、[模型输入证据](../runs/0922jap-terminal-punctuation-20260929T081114Z/verified/model-input-verification.json)、[回放声能审计](../runs/0922jap-terminal-punctuation-20260929T081114Z/replay-audit.json)。声能审计为 **4 files / 0 failed**，相邻停顿、跨轨标点错误、疑似漏音均为零；自动检查不等于逐音素人工金标。
- 交付：更新既有目录 `/mnt/Raw/0922jap/textgrid_native_qwen_20260929_fixed`（NAS：`\\RS3621\Research_TTS\Data\Raw\0922jap\textgrid_native_qwen_20260929_fixed`）。配套 WAV 的 PCM 与本轮回放完全相同，因此保留旧 WAV 的发布字节；[发布回执](../runs/0922jap-terminal-punctuation-20260929T081114Z/publication.json)和[发布后审计](../runs/0922jap-terminal-punctuation-20260929T081114Z/published-audit.json)记录实际文件哈希。原 `textgrid_native_qwen_20260928` 历史目录仍保留。

### JA-018：内部 `<sp0>` 向前合并规则遗漏（2026-09-29）

- 样本/旧结果：0100 的 `4.82–4.89 s` 在 words、phones、phone_kana、phone_tone 四轨仍为 `<sp0>`；其前一个词 `も` 截止 4.82 s，前一个音素 `/o/` 截止 4.82 s，后一个词 `作ろう` 从 4.89 s 开始。[发布前快照及哈希](../runs/0922jap-sp0-merge-20260929T081938Z/before.sha256)保留了这一结果。
- 旧项目规则与根因：参考交接文件规定“非开头、短于 200 ms 的空隙等价于 sp0：前一个词向后延伸覆盖该空隙”；实现位于 `scripts/postprocess_textgrids.py::_resolve_visual_short_silence_merges`，其中内部 canonical sp0 可合并到词，原始证据和可视边界分开保存。本项目此前只移植了连续静音归并与标点同步，把 `merge_short_silences` 整体标为会破坏原始 MFA 音素归属，漏掉了**发布层可视短停顿合并**。这是移植范围判断错误。现仅把原始声学归属留在 postprocess 证据中，在发布层对无标点归属的内部 `<sp0>` 向前延伸上一个词/音素；句首和句尾、真实标点不被吞掉。词内短空隙也由上一个音素承接。新边界重新生成四条时间轨和 `alignment.json`；`publication_sp0_merges` 记录原坐标、前音素及声能。
- 声能证据：0100 原停顿最大 10 ms RMS **0.000857**，低于活动阈值 **0.02**，活跃时长 **0**。因此将 4.82–4.89 s 用作上一个词/音素的可视延伸不会掩盖可测连续语音；声学原边界 4.82 s 仍由 `postprocess.json` 的合并前停顿与音素记录追溯。新成品 `も` 为 **4.64–4.89 s**，其末音素 `/o/` 为 **4.76–4.89 s**，下一个词仍从 4.89 s 开始。
- 验证与交付：回归覆盖词间、词内和标点保护；完整测试 **444 passed / 4 skipped**，`git diff --check` 通过。七条原生模型输出回放仍是 **4 aligned / 3 failed**，失败仍为 0060、0070、0090 的 `alignment_acoustic_coverage`，未把问题样本发布。[七条回放](../runs/0922jap-sp0-merge-20260929T081938Z/verified/output/summary.json)、[模型输入核验](../runs/0922jap-sp0-merge-20260929T081938Z/verified/model-input-verification.json)、[四组声能审计](../runs/0922jap-sp0-merge-20260929T081938Z/replay-audit.json)保留。四组合格 TextGrid 中只改 0100，0050、0080、0110 与发布前逐字节相同；四组均无剩余 `<sp0>`。更新原共享目录，原有 WAV 的 PCM 与本轮回放逐样本一致，保留原有发布 WAV 字节。[发布回执](../runs/0922jap-sp0-merge-20260929T081938Z/publication.json)及[发布后审计](../runs/0922jap-sp0-merge-20260929T081938Z/published-audit.json)可追溯。

### JA-019：内部 `<sp1>` 可视归属仍与旧项目不同（2026-09-29，待处理）

- 只读复现：当前发布的 0100 在 `2.58–2.79 s` 保留 `<sp1>`，前词“ご飯”为 `2.11–2.58 s`、末音素 `/ɴ/` 为 `2.48–2.58 s`，后词“食べ”从 `2.79 s` 开始。四组发布 TextGrid 的 words 轨仅此一个内部 `<sp1>`。可用 `praatio` 读取[0100 成品](/mnt/Raw/0922jap/textgrid_native_qwen_20260929_fixed/01-00-a00-0100__0verflow_Shiny_Days.TextGrid)复现；[发布声能审计](../runs/0922jap-sp0-merge-20260929T081938Z/published-audit.json)给出该停顿最大 10 ms RMS `0.000538`、阈值 `0.02`、活跃时长 `0`。
- 差异根因：旧项目 `scripts/postprocess_textgrids.py::_resolve_visual_short_silence_merges` 还处理小于 500 ms 的内部 canonical `<sp1>`，结合 CTC 词归属或局部能量判定左/右词的可视所有权，缺乏明确方向时有向前回退。本项目本轮仅移植了无标点内部 `<sp0>` 向前合并，没有对应 `<sp1>` 决策器。现有低声能证明这是安静区间，**不能单独证明应给左词还是右词**，因此本次只登记差异，不擅自移动 210 ms 边界。
- 相关能力盘点：完整词级声能边界重估、CTC 词边界吸附及 CTC 词间隙 BGM 归因仍未移植；当前 Qwen 词时间戳用于裁剪窗口与外侧锚点审计，并非旧项目的逐帧 CTC 所有权证据。旧项目 `fix_short_words` 的中文虚词专用分支不适用于日语，但其中“低于 50 ms 的通用内容词”分支也尚无日语等价修复；本批四个合格 TextGrid 的 words 轨没有此类短词。原始 MFA `sil` 按能量直接吞并的旧式改写未移植；本项目仅做可视 `<sp0>` 合并并保留合并前声学归属。以上是**已确认的边界后处理能力缺口**，不是声称旧项目全部 257 条历史回归都应直接照搬，也不是声称 0060、0070、0090 的词/音素归属已修复。
- 2026-09-29 盘点时状态：尚未修改 0100 的这处 `<sp1>`；旧项目的“选择左/右词所有权”与本项目的“停顿显示为标点”是不同操作，不能由低声能直接推断所有权。其它能力的适用性继续以具体日语样本与模型证据判断。

后续用户明确指定新发布规则：**句中 `<sp1>`、`<sp2>`、`<sp3>` 静音均改为 `……`，original/kana 对应位置也插入 `……`**。因此不再移动该 210 ms 停顿的左右边界；只改变其标点归属和六轨显示。已有原文标点优先，句首 `<sp1>` 和句尾标点保持原样，原始 TXT/ASR/MFA 输出不变。对于词内有长静音却没有可对应的词间隙的情况，发布阶段明确失败，不能留下不同步的轨道。

- 0100 新结果：`2.58–2.79 s` 的 words、phones、phone_kana、phone_tone 均为 `……`；original 为 `<sp1>はぁ……ご飯……食べた？おかゆでも作ろうか？`，kana 为 `<sp1>ハア……ゴハン……タベタ？オカユデモツクロウカ？`。`postprocess.json.publication_internal_ellipsis` 记录原标签 `<sp1>`、区间、相邻词序号、最大 RMS `0.000538`、阈值 `0.02` 和活跃时长 `0`。这只是声能支持其为安静区间，不把它伪装为逐音素金标。
- 防回归：单元测试覆盖 `<sp1>`、`<sp2>`、`<sp3>`、重复词定位以及已有标点/句首句尾保护；完整测试 **450 passed / 4 skipped**，`git diff --check` 通过。使用已保存并核验模型输入的七条完整流水线回放，仍为 **4 aligned / 3 failed**；0060、0070、0090 仍因 `alignment_acoustic_coverage` 拒绝。四组合格候选声能/结构审计 **4 files / 0 failed**；只有 0100 TextGrid 与发布前不同，配套四个 WAV 的 PCM 全部与回放一致。[发布前快照及哈希](../runs/0922jap-internal-ellipsis-20260929T084752Z/before.sha256)、[回放汇总](../runs/0922jap-internal-ellipsis-20260929T084752Z/verified/output/summary.json)、[回放审计](../runs/0922jap-internal-ellipsis-20260929T084752Z/replay-audit.json)、[发布回执](../runs/0922jap-internal-ellipsis-20260929T084752Z/publication.json)、[发布后审计](../runs/0922jap-internal-ellipsis-20260929T084752Z/published-audit.json)。

### JA-020：预计算 CTC 的时间轴与零时长词（2026-09-29）

新输入位于 `/mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu`，含分开的 `wav/`、`txt/`、`ctc/`。原管线的 `AudioNormalizer` 会缩短长静音、改动头尾，不能直接消费以原 WAV 为坐标的 CTC。0004 的 CTC 首词在 2.8 s；如果默认裁去前段长静音，坐标必然错位。0002 的 `zero_duration` 轨另有 2.0 s 的「た」，只读取 `words` 区间会使文本流少一个字。

增加 `PrecomputedCTCClient`：按时间顺序合并词区间与零时长点，验证 CTC/TXT 字符流、重叠和 WAV 时长；`OriginalAxisWav` 仅接受单声道 16 kHz PCM16，逐字节复制，验证 SHA-256、帧数和时长。批处理工具按文件名选前十，平铺输入到独立运行目录，只将审计通过的 TextGrid 与原 WAV 配对发布到游戏目录 `mfa/`。输入清单与逐条 SHA-256 在[预检记录](../runs/galgame-akabei-first10-20260929/preflight.json)，使用说明见[CTC 输入文档](japgalgame-mfa-from-ctc-20260929.md)。


2026-09-30 全量输入读入复现：`0verflow_Shiny_Days/ctc/01-00-a00-0890__0verflow_Shiny_Days.TextGrid` 在 **3.20 s** 原始点序为 `ん`、`だ`、`けど`，原文为「あのね、光に聞いたんだけど」。`praatio.PointTier` 对同时间点按标签重排为 `けど`、`だ`、`ん`，导致 `read_ctc_words` 将正确 CTC 误拒为词序不一致；首批累计发现 7 条，源路径、旧错误及源 WAV/TXT/CTC 哈希见 `.runtime/jobs/galgame-mfa-all/zero-duration-order-recheck.json`，TXT/TextGrid 与修复前读入代码快照见 `reader-order-evidence/`。这与 JA-012 的真实模型词序错位不同，不能靠放松文本匹配处理。

修复只在存在同时间零时长点时用 `praatio.utilities.textgrid_io.parseTextgridStr` 读取序列化点顺序；保持原时间坐标、重复词点、正时长区间以及现有时长/重叠/原文匹配检查。新增测试覆盖同时间乱序标签、同时间重复标签及真实文本不一致仍拒绝。修复前回归 **1 failed / 1 passed**，失败内容准确复现「聞いたけどだんね」；修复后相关回归 **30 passed**，7 条真实输入均重新通过预检。完整非真实模型回归在正确工具 PATH 下 **493 passed / 15 deselected**。最初广测遇到另一个工作中的并行脚本测试尚缺模块、以及未配置 ffmpeg PATH 的两项 ASR 测试失败；模块完成并配置现有工具 PATH 后完整回归通过，未为这些问题修改旁支代码。

全量状态仅把这 7 条旧误拒项标为 `retry_required`，重新处理后仍须通过 MFA 和最终声能/停顿/标点/轨道审核才发布。原 NAS WAV/TXT/CTC 文件未改动。本条修复证明了读入词序正确，不等于七条已经声学通过，也不替代人工音素金标。启动先真实验证 50 条，再进入每批 500 条全量及 CTC 完成后补扫；进度以 `.runtime/jobs/galgame-mfa-all/live-status.json` 和 `progress.sqlite3` 为准。

### JA-021：新语料音素映射不足与首次运行环境错误（2026-09-29）

首次尝试十条均在 G2P 子进程失败，原因是 `fstcompile` 虽安装在 MFA 环境却不在进程 `PATH`。单独运行 G2P 复现错误；加入 MFA 环境 `bin` 后同一命令成功。保留[首次失败报告](../runs/galgame-akabei-first10-20260929/first-attempt-report.json)，不把其视为声学对齐失败。工具现在可从配置的绝对 MFA 可执行路径自动补全 `PATH`。

第二次尝试进入 G2P 后，多数新游戏读音被 `no_mappable_pronunciation` 拒绝；原因是映射表仅覆盖先前小批语料。用当前 MFA v3 对十条中的 56 种不同读音实际生成候选，补了所需假名、长音及鼻音变体规则。对于模型完全漏出的词尾「ッ」（如「ダッ」），只增补模型在其他词尾「ッ」已经使用的 `/ʔ/` 候选，原候选仍保留；其他读音不改。56 种读音重新逐项投影结果为 **0 未映射**，测试覆盖长音、鼻音、卷舌音与词尾促音；[第二次报告](../runs/galgame-akabei-first10-20260929/second-attempt-report.json)保留错误版本状态。


2026-09-30 全量首批换游戏复现：`0verflow_Shiny_Days` 前 50 条中，13 条在 G2P/莫拉投影阶段以 `no_mappable_pronunciation` 筛除；24 条另因声能覆盖或时间戳冲突筛除，13 条实际发布。对 13 条原 TXT 用锁定 Sudachi 和 MFA Japanese v3 模型独立批量诊断，得到 **197 个词项、102 种读音**。缺项与精确模型候选保存在 `.runtime/jobs/galgame-mfa-all/mapping-diagnostics/report.json`、`g2p/g2p_output.dict`，修改前完整映射表在 `phone-map.before.yaml`。例如「キッチン」模型为 `c i tɕː i ɴ`，「出勤」为 `ɕ ɨ cː i ɴ`，「可愛い」为 `k a w a iː`；原表缺少对应促音/长音跨度。「ウェイトレス」出现 `ɯ e ...` 和 `w e ...` 两种 MFA 候选。

新增 **12 条有本模型输出证据的精确规则**，明确促音覆盖相邻莫拉、长音覆盖两个莫拉以及「ウェ」「ジャ」的逐音素归属；没有删除 IPA 长度或改动审核门槛。14 个新增正例修复前全部失败、原 4 例及异常候选拒绝测试通过；修复后相关测试 **46 passed**，完整非真实模型回归 **511 passed / 15 deselected**。按真实候选复核，12 条样本已无映射阻碍，只有「すっごく」仍因候选中的异常 `pː` 拒绝，未为其添加兜底规则；见 `mapping-diagnostics/recheck.json`。这 12 条与 JA-020 的 7 条读入误拒组成 19 条定向真实 MFA 重试，随后继续全量 500 条批次。

首批已发布 13 份 TextGrid 在 NAS 读回并用原 WAV 再次完成完整输入配对、SHA-256、轨道/停顿/标点/声能审计，**13 files / 0 failed / 成品目录其他文件 0**；回执在 `.runtime/jobs/galgame-mfa-all/startup-published-audit.json`。映射修复不等于新样本已经通过声学审核，19 条重试仍须经现行管线与最终审核；旧 13 份成品保持原哈希，原 NAS 输入未修改。后续游戏的新读音变体应继续按实测证据补充，不能凭一个游戏的通过率推断全量完整覆盖，也没有人工音素金标。

### JA-022：短停顿连续有声与分片起音（2026-09-29）

首次真实 MFA 十条运行中，0002 在 `0.82–1.71 s` 停顿尾 `1.69–1.71 s` 以及 `4.05–4.08 s` 短停顿检出活动帧；0003 在首停顿尾 `0.51–0.54 s` 和 `2.85–2.88 s`，0009 在 `3.96–4.00 s`，0011 在 `1.25–1.28 s` 也有同类证据。旧起音规则不能使用首个显式静音前的合成安静段；在前一个尾音延长后，分片静音的原始起点又错误限制后续起音搜索。更短的内部停顿即使全部有声，也因为没有三帧安静而无法归给前元音。

修复只在起音前存在连续安静→活动转变时回拉起点；仅对 **≤50 ms、前后两侧与整段均有活动、前音素为元音、后面直接接发音** 的内部显式短停顿，按已有 `<sp0>` 向前归属将其给前音素。安静停顿、长停顿和独立声岛不适用。保留 `raw_phones` 原坐标，`energy_boundary_refinement.edits` 写出每次改动。对已保存的四条真实 MFA 音素及原 WAV 重新运行后处理，0002、0003、0009、0011 的声能覆盖均通过；0004 仍拒绝。单元反例验证安静 30 ms 停顿不会被声学分支吞并。真实模型定向重跑及发布结果见后续回执。

### JA-023：仍需校对的声学冲突（2026-09-29）

0004 的 CTC 首词在 2.8 s，但 `0.67–0.96 s` 已有约 290 ms 独立有声片段；该片段与首词相隔很长安静区，不能用有限起音回拉或尾音延伸归入它。0007 在 `2.11–3.80 s` 停顿内部出现 `3.38–3.73 s` 多段活动帧。0008 有一个 MFA `/h/` 仅 10 ms，低于既有 15 ms 音素下限。三条原始 TXT/CTC/WAV 不修改，失败记录与中间产物保留在[首轮运行目录](../runs/galgame-akabei-first10-20260929/)；不得以空白或未核实的 TextGrid 代替通过结果。自动声能证据不能判断 0004/0007 独立片段的文字内容，也不能把 0008 的 10 ms 音素认定为人工正确边界。

迁移后为了便于逐条复核，三条失败项另整理在 `/mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/filtered/`：各有原 WAV/TXT、输入 CTC TextGrid、`postprocess.json` 和 `failure.json`。其中 `ctc_source.TextGrid` 明确是输入时间戳，**不是**通过校验的 MFA 成品；完整 MFA 中间产物仍在同项目 `diagnostics/diagnostics.tar.zst`。`mfa/mfa_run_report.json` 的 `filtered_output` 字段指向各条目录。

短音素补充定位：0007 的 `/ɾ/` 位于「驚か」中的「ロ」，MFA 区间 `3.89–3.90 s`；CTC 把整个四拍「驚か」压在 `3.76–3.92 s`（仅 160 ms），而 `3.38–3.73 s` 的有声活动被标入它前面的静音。MFA 第三段从 3.76 s 才开始，因此更可能是 CTC 起点偏晚、裁剪缺少前段声学上下文，**不是**原词天生短到只应有 10 ms 的 `/ɾ/`。0008 的 `/h/` 属于「はじめ」词首，MFA 区间 `0.56–0.57 s`；CTC「はじめ」为 `0.56–0.96 s`（400 ms），整词不短，但 MFA 第一段恰从 0.56 s 开始。原 WAV 在 0.50–0.56 s 已有逐渐增强的低幅和高频能量，支持词首声学活动被裁剪窗排除的可能性；这些能量尚不能单独证明全部属于 `/h/`。因此两条短音素不能统一解释为“词太短”，也不能简单把 15 ms 校验门槛降低后发布。

### Galgame 前十条最终执行与发布回执（2026-09-29）

前十条按 WAV 文件名排序选定：`air_0001`、`0002`、`0003`、`0004`、`0006`、`0007`、`0008`、`0009`、`0011`、`0012`，均有对应 TXT/CTC。首轮真实 MFA 的结果是 **3 aligned / 7 failed**；针对 JA-022 的 `0002`、`0003`、`0009`、`0011` 使用修正规则重新执行完整 MFA，结果 **4 aligned / 0 failed**。合并后 **7 条发布、3 条失败**：未发布 `0004`、`0007`、`0008` 的具体声学证据及运行原因保留在[最终十条回执](../runs/galgame-akabei-first10-20260929/final-report.json)。首轮和定向重跑的逐条中间产物分别位于[首轮目录](../runs/galgame-akabei-first10-20260929/)和[重跑目录](../runs/galgame-akabei-repaired4-20260929/)。

共享输出位于 `/mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/mfa/`；七组 `.TextGrid` 与同名 `.wav` 已发布，WAV 字节 SHA-256 全部等于原 `wav/` 文件。发布后用 `tools/audit_textgrid_pauses.py` 对该目录实际七组重新扫描，结果 **7 files / 0 failed**，包括相邻停顿、标点同步、结构和声能覆盖检查，见[发布后审计](../runs/galgame-akabei-first10-20260929/published-audit.json)。非模型完整回归为 **451 passed / 15 deselected**，`git diff --check` 通过；15 个显式真实模型标记测试未纳入该命令，十条本身另作实际 MFA 运行。上述自动检查不等于每条音素边界均有人工作为金标确认。

### JA-024：共享输出目录纠正（2026-09-29）

用户明确要求本项目所有产出位于 `\\RS3621\Research_TTS\Data\Raw\0922jap`，不应留在源游戏目录。原先七组 TextGrid/WAV 与报告位于源游戏目录 `mfa/`，属于发布位置错误；上段为当时的历史发布记录，不再代表当前交付路径。

新位置为 `/mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/`：`mfa/` 保存七组配对、总报告与重新扫描的审计；`diagnostics/diagnostics.tar.zst` 保存首十条及四条定向重跑的**完整**中间产物。归档将重复的 MFA 模型文件以硬链接只存一次，并把内部绝对链接改成可移植的相对链接；归档 SHA-256 为 `301c1371562614928b27d29a6c0c172e1f2232621ec59378ff4b359c1bdb2bc4`，远端字节哈希相同且 zstd 完整性检查通过。七组新旧 TextGrid/WAV 哈希逐个相等，新位置重新审计仍为 **7 files / 0 failed**。[迁移回执](../runs/galgame-akabei-relocation-20260929/relocation_receipt.json)记录逐项哈希；目标验证完成后，源游戏目录的误放 `mfa/` 已删除，原始 `wav/txt/ctc` 未动。工具现在强制 `--output` 指向源游戏目录外，防止下次重跑又写回错误位置。

## 2026-09-29：同一游戏前 50 条扩测

按源目录 WAV 文件名字典序选择前 50 条，编号从 `air_0001` 到 `air_0055`，跳过源目录本来不存在的编号。前十条源 WAV/TXT/CTC 哈希与原回执相同，直接复用原结果；新增的 40 条均通过输入配对、音频格式、CTC 文本及原时间轴预检。[选择清单](../runs/galgame-akabei-first50-20260929/selection.json)、[最终报告](../runs/galgame-akabei-first50-20260929/consolidated-report.json)。

用户要求忽略过短音素。现在 `<15 ms` 的非静音音素仍记录在 `postprocess.json.short_phone_issues`，但不单独否决整条；结构、停顿声能、词时间戳与发布审计仍执行。真实重跑的 `air_0008` 仍有 `0.56–0.57 s` 的 10 ms `/h/`，其他检查通过，已发布；原筛选证据转存到 `diagnostics/historical-filtered/air_0008.../`。这只表示不再用时长阈值拒绝，**不是**人工确认该 `/h/` 切点。`air_0007` 同样可能有短音素，但 `3.38–3.73 s` 的停顿漏声仍使其拒绝。相关回归测试及全套非真实模型测试为 **468 passed / 4 skipped**，真实音频另完成 MFA 运行。

### JA-021 复现：音素映射表只覆盖旧小批读音

新增 40 条首次运行有 31 条因 `no_mappable_pronunciation` 停在 MFA 前。读取实际 MFA v3 G2P 候选与假名音拍，发现缺少如 `ヤ→j a`、`キュ→c ɨ`、`チョ→tɕ o`、`ヒ→ç i`、鼻音变体、长音及促音组合。只为本批实测候选加入精确规则，不推测未出现的读音；例如 `ケッコン` 的 `[ッ, コ]→[kː, o]` 明确把闭塞与辅音起点共同归属。首次失败记录保留在 `shard1`–`shard4`，修正后的 `retry1`–`retry4` 重新执行完整管线。新增 40 条的 **442 个词项、206 种读音**逐项检查后 **0 未映射**；[修前候选](../runs/galgame-akabei-first50-20260929/g2p-coverage.json)、[修后复核](../runs/galgame-akabei-first50-20260929/g2p-coverage-after.json)。

### JA-025：并行运行共用 MFA_ROOT_DIR

首轮的 `air_0020` 在 MFA align 阶段报 `Error opening input stream .../extracted_models/acoustic/japanese_mfa_acoustic/final.mdl`；`air_0043` 的 G2P 子进程也失败。四个批次同时共用 `.runtime/mfa-root`，而 MFA 会在该根目录解包模型及维护 G2P 工作文件；这是运行目录隔离不足，不能归为音频质量失败。重跑时四个批次分别使用独立的 `.runtime/mfa-root-first50-{1..4}`，其中 `final.mdl` SHA-256 均为 `eee0d60657af89c468ec47be97a55bda4513e4d7201d44761d518b31f08a77c9`；两条均进入后续声学流程，原命令错误未复现。`air_0020`、`air_0043` 最终因声能覆盖失败，原因应以重跑报告为准。并行重跑应各自指定 MFA_ROOT_DIR；单进程顺序处理不需要复制模型目录。

2026-09-30 全量作业并行隔离检查：发现另一个 `runs/galgame-throughput-canary-20260930/` 的 50 条试跑正在使用默认 `.runtime/mfa-root`。本次 `/mnt/Raw/JapGalgame` → `/mnt/Raw/GalgameMFA` 全量作业在发布任何结果前，仅停止并恢复自己的进程树；中断批次现场保存在 `.runtime/jobs/galgame-mfa-all/interrupted-work/`。为全量进程独立设置 `.runtime/mfa-root-galgame-all`，同时把该根目录的 `global_config.yaml::temporary_directory` 改为同一独立目录；只复制预训练模型包，另一试跑与 16 个 CTC 工作进程保持运行。现有全量/混合批次相关回归 **19 passed**，输入预览 `complete=3`。启动证据与代码哈希见 `.runtime/jobs/galgame-mfa-all/startup-provenance.json`，运行状态见 `live-status.json`。本次是预防已知共用目录风险，未观察到新的模型命令错误；真实首批运行与发布审核尚在执行，不能把启动和单测当作声学通过。

### JA-026：新增的边界及时间戳冲突

新增 40 条最终 **29 条通过、11 条拒绝**；连同前十条重评，前 50 条 **37 条发布、13 条拒绝**。13 条由旧样本 `0004`、`0007`，以及新增 `0013`、`0015`、`0016`、`0020`、`0024`、`0025`、`0033`、`0037`、`0043`、`0045`、`0049` 组成。新增失败中 10 条是 `alignment_acoustic_coverage`，1 条是 `timestamp_mfa_disagreement`。具体 WAV、原文、输入 CTC、后处理和 `failure.json` 均在目标目录 `filtered/`；`ctc_source.TextGrid` 是输入锚点，不能充作合格 MFA 输出。

典型证据：`0013` 的 `0–1.39 s` 停顿中有 `0.84–1.39 s` 活动，且 `1.45–4.96 s` 停顿中还出现 `3.02–3.12 s` 独立活动；`0045` 的 `2.08–4.27 s` 停顿在 `2.08–2.51 s` 有连续声能；`0049` 的 `1.26–2.839 s` 停顿有 `1.26–2.06 s` 活动。它们不能靠统一向前/向后延长边界安全地归属。`0015` 的第 0 段 CTC 词尾为 **2.72 s**，原 MFA 词尾 **2.33 s**，能量修正后仍仅 **2.45 s**，残差 **0.27 s** 超出 0.20 s 门槛，因此保留拒绝。其余声能坐标及各音频哈希见 `filtered/<stem>/failure.json` 和总报告。

目标 `mfa/` 中的 37 组 TextGrid 与原 WAV 同名配对；发布前及落盘后审计均通过。最终共享 `mfa/mfa_audit.json` 为 **37 files / 0 failed**，检查连续轨道、相邻停顿、标点同步、音频时长和停顿声能覆盖；没有人工音素金标，不能由此推断每个词内切点都精确。首十条历史完整归档仍在 `diagnostics/diagnostics.tar.zst`；本轮完整运行档案在 `diagnostics/first50-20260929.tar.zst`，SHA-256 为 `97c7e1394ad17f92d70d2d47f1fcf5f7f7566f648431a6cf2cb32e4d2e26b8c7`，已验证远端字节哈希与 zstd 完整性。归档把 316 个重复大文件改为硬链接并重写 474 个绝对链接，不覆盖旧证据。

## 2026-09-30：前 50 条的 13 个筛选项逐条复核（JA-023、JA-026 复现；JA-027 新发现）

复核范围为当时 `/mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/filtered/index.json` 的全部 13 条；该版清单已留在[发布前快照](../runs/galgame-tail-extension-canary3-20260930/before/index.json)。每条的 `source.wav` 是对应音频，`source.txt` 是原文，`ctc_source.TextGrid` 是**输入 CTC**，`postprocess.json` 是当时未发布的 MFA/后处理诊断，`failure.json` 记录拒绝原因与输入哈希；这些目录本身**没有合格 MFA TextGrid**。后续修复的 `0045`、`0049` 原失败包已迁到同项目 `diagnostics/historical-filtered/`；当前 `filtered/` 只保留 11 条未通过项。局部裁剪、10 ms 声能/频谱图和独立 Qwen3-ASR 复核记录在 [筛选复核附件](../runs/galgame-akabei-filtered-review-20260930/)。下表是修复前的逐条判断，当前发布状态见末尾回执；复核阶段没有改动源音频、原文、CTC。

判别标准：声段若与原文某词的读音、CTC 词区间及相邻发音连续对应，记为台词边界问题；与台词相隔明显安静区且原文没有对应内容的短促语气声/音效，按本批标注目标视为正常筛选；无法判定来源的独立短声保持待听审。短片段 ASR 只作旁证：`0004` 的 **0–0.4 s 数字静音对照**被同一 ASR 误识为「はい」，所以任何孤立 ASR 字词都不能充作声源真值。本轮无法直接进行人工听辨；下表的“正常”是基于文本、CTC、频谱、声能和对照推断的**暂定分类**，不是已听审金标。

| 样本 | 静音中声段 / 失败坐标（秒） | 复核结论及依据 | 处理状态 |
| --- | --- | --- | --- |
| `0004` | 句首停顿 `0–2.80` 内 `0.67–0.96` | **疑似正常筛选，待听审确认。** 原文仅「こちらの方は。」、首词 CTC 从 `2.80` 开始；该短促有声段与首词间有约 1.8 s 安静。局部 ASR 为「うん」，但静音对照也出现幻觉；目前只可判为原文外语气声/音效的可能性较高，不能向后拉「こちら」吞并。 | 继续筛选；语气声属于用户指定可正常过滤类型。 |
| `0007` | 停顿 `2.11–3.80` 内 `3.38–3.73` | **台词漏声。** 原文「驚かせた」；CTC 将「驚か」压到 `3.76–3.92`，局部 ASR 也给出相近的「驚く」。多拍有声段紧接该词，CTC/MFA 起点偏晚约 0.38 s；前半段长安静不能一起归词。 | 继续筛选；需要按实际起音重对齐该词。 |
| `0013` | 首停顿 `0.84–1.39`；另有 `3.02–3.12` | **确定有台词边界错误，另有独立声段未定性。** 原文及 CTC 首词「そう」在 `0.48–0.88`，局部 ASR 亦为「そう」，但 MFA 将对应末音素压到 `1.39–1.45`，使前面的发音错列静音。`3.02–3.12` 太短且与前后词相隔安静，局部 ASR 的「は」不可靠，可能是语气声/音效，不能强行并入台词。 | 继续筛选；首词需重对齐，独立声段待听审。 |
| `0015` | CTC 首段词尾 `2.72`，MFA 原尾 `2.33`、能量修正尾 `2.45`；停顿内 `2.56–2.66` | **台词/时间戳冲突，并触发 JA-027。** 差值仍为 `0.27 s`，超过 `0.20 s` 门槛；在原文「一回表」的 CTC 覆盖内另见约 100 ms 的谐波声岛。该岛与前音素间有短暂安静，不能仅把尾音盲目拉至 `2.72`。 | 因 `timestamp_mfa_disagreement` 继续筛选；需短语级重对齐。 |
| `0016` | `<sp0> 1.33–1.36` | **台词边界。** 前后为鼻音 `/ɴ/`、`/ɲ/`，30 ms 区间内发声/共振连续；现行只给前元音合并短停顿的规则不适用。 | 继续筛选；复核鼻音相邻短间隙规则。 |
| `0020` | `<sp0> 1.08–1.15`、`2.69–2.72` | **台词边界。** 第一处前后相邻发音且声能延续，其中还有 `1.08–1.12`、`1.12–1.15` 两个连续 `<sp0>` 片段；第二处为 `/ɴ/`→`/o/` 的 30 ms 误分空白。并非独立音效。 | 继续筛选；按完整停顿检查及重对齐，发布时不得保留连续 sp。 |
| `0024` | `<sp0> 7.16–7.23`，活跃 `7.16–7.18` | **台词边界。** 「を」末元音至「する」起音之间的连续衰减，未见独立声源证据。 | 继续筛选；局部边界复核。 |
| `0025` | `<sp0> 5.09–5.15`、`6.40–6.47`，各在起点约 20 ms 活跃 | **台词边界。** 分别邻接 `/i/`→`/d/`、`/o/`→`/ɡ/`，属于短语内前音素尾部；第一处有连续 `<sp0>` 分片。 | 继续筛选；局部边界复核。 |
| `0033` | `<sp0> 1.84–1.92`，活跃 `1.84–1.86` | **台词边界。** 「を」末 `/o/` 至后词起音的衰减，不支持判作音效。 | 继续筛选；局部边界复核。 |
| `0037` | 停顿末 `5.25–5.28` | **台词起点偏晚。** CTC「お袋」从 `5.28` 开始，频谱显示其起音略早；与前词 `4.83` 结束之间确有长安静，不能把整段给前词。 | 继续筛选；只回拉「お袋」起点并验证。 |
| `0043` | `<sp0> 2.88–2.95`，活跃 `2.88–2.90` | **台词边界。** 「見え」末 `/e/` 衰减到下一音节 `/tɕ/`，不是独立声效。 | 继续筛选；局部边界复核。 |
| `0045` | 停顿 `2.08–4.27` 内 `2.08–2.51` | **明确的台词尾部漏声。** 原文/CTC「思う」到 `2.56`，局部 ASR「と思う」；MFA 最后 `/ɯ/` 到 `2.08`，连续谐波尾部仍延约 0.43 s。 | 继续筛选；按 CTC 约束重对齐「思う」，不能跨全段安静。 |
| `0049` | 停顿 `1.26–2.839` 内 `1.26–2.06`（另 `2.10–2.13`） | **明确的台词尾部漏声。** 全句原文就是「うん。」、CTC 到 `2.24`，但 MFA `/ɯ/`、`/ɴ/` 只占 `1.20–1.26`；局部和整句 ASR 均为「うん」，后续约 0.8 s 连续发声应属该词，不能当作原文外「哎」类语气声。能量不能独自决定 `/ɯ/` 与 `/ɴ/` 的内部切点。 | 继续筛选；词级重对齐后再核音素。 |

**复现结论。** 12 条 `alignment_acoustic_coverage` 中，`0004` 有一处疑似原文外语气声，可按用户规则正常筛选但须注明未听审；其余 **11 条存在可定位的台词边界/归属问题**，其中 `0013` 还包含未定性的独立短声。第 13 条 `0015` 是时间戳冲突，同时有疑似台词声岛。这里的“问题”指声学归属，不等于每个声岛都已精确识别到音素。筛选动作本身阻止了这些候选误发布，是正确的；若要提高通过率，必须修正上游锚点或受证据约束地重对齐，不应整体关闭声能检查。

**根因与调整方向。** `0007`、`0037` 的 CTC/裁剪起点偏晚；`0013`、`0045`、`0049` 的 MFA 把可听词段压缩或截尾；`0016` 及多条 20–70 ms 间隙暴露了短停顿规则仅保护前元音、连续声能门槛较保守的问题。`src/japanmfa/postprocess.py::_refine_silence_phone_boundaries` 对合成尾停顿最多只扫 `0.12 s`，无法恢复 `0045`/`0049` 的长词尾；无论延长上限还是放松门槛，都必须先用 CTC、相邻词和安静间断约束，不能吞掉 `0004` 这样的独立声源。待修复时先对 `0007`、`0045`、`0049` 和各短间隙建立声学回归，再重跑全部 50 条，检查 words/phones/phone_kana/phone_tone 的共用时间轴和标点一致性。

### JA-027：时间戳先拒绝时的停顿诊断盲区

`0015` 的 `failure.json` 只报 `timestamp_mfa_disagreement`；其 `postprocess.json` 停顿声能记录中，`2.56–2.66 s` 约 100 ms 的活动声岛位于修正后的 `2.45–2.72 s` 停顿内，但 `suspect=false`。原因是 `src/japanmfa/postprocess.py::_pause_acoustic_coverage` 对非边缘声岛要求活跃总长至少 `0.15 s` 且最长连续 `0.08 s`；该岛不满足前一条件。时间戳拒绝本身正确，**诊断信息不完整**，容易使后续校对误以为差值后半段全是静音。后续应在失败报告中保留全部活动区间及其与 CTC 词区间的重叠，并对短岛提供待归因提示；不能把所有 ≥100 ms 活动一律改成发布否决，因为音效/原文外语气声可能与它同形。当前验证为原 WAV 的频谱和 10 ms 声能复核、`failure.json` 与 `postprocess.json` 坐标对照；尚未修改代码或发布该条，剩余 50 条外语料未扫描此盲区。

### JA-026 追加：与旧项目尾词声能延伸的逐项对照（2026-09-30）

旧项目 `/mnt/local_E/MFA_Pause/repo/scripts/adjust_ctc_boundaries.py::_search_energy_fall` 和 `adjust_boundaries` **确有词尾延长**：在 MFA 前，从 CTC 词尾向后搜索连续有声后的至少 30 ms 安静；普通扫描上限 `0.35 s`，有明确 Qwen 标点停顿归属时至多 `0.60 s`，同时将该标点/停顿起点移到新的词尾，并保护下一词起点及停顿末端。其 `tests/test_qwen3_energy_pause_extension.py` 覆盖连续尾音、安静后的独立声段不吞并、词尾/标点同移。这是**词级 CTC 锚点预处理**，不等同于把 MFA 最后一个音素无条件拉长。

本项目 `src/japanmfa/postprocess.py::_refine_silence_phone_boundaries` 已有 MFA 后的 `energy_tail_extension`，显式静音一般最多延 `0.50 s`，仅满足严格连续衰减形态时可至 `0.80 s`；只有合成尾停顿时上限 `0.12 s`。上游的 CTC 段末归属没有传进这一步，报告仍注明 `_refine_boundaries_by_energy_full_word`/`CTC_word_boundary_snap` 缺失。这里有两个不能混同的复现：

- `0045`「思う」末 `/ɯ/` 在 `2.08 s` 截断，但 10 ms RMS 从 `2.08` 到约 `2.57 s` 连续高于 `0.001` 门槛，`2.58 s` 起连续安静；输入 CTC 尾为 `2.56 s`。现行 `0.50 s` 判断把**三帧静音确认的结束**也计入延长上限，确认点约 `2.61 s`，故刚好拒绝了 `2.58 s` 的真实停声；随后长衰减分支又因 `0.50 s` 后没有可量的衰减窗口而拒绝。对这一条可把上限约束放在**候选声尾**、允许额外三帧作静音确认，再用 CTC/相邻词/安静断点保护；修正后仍须重跑 MFA/后处理并审计四轨，不能以本次量测冒充已发布结果。
- `0049` 原文仅「うん。」、CTC `1.20–2.24 s`，MFA 却只给 `/ɯ/ 1.20–1.23`、`/ɴ/ 1.23–1.26`。原 WAV 的声能先从 `1.26` 向 `1.60 s` **上升**，再逐渐减弱，约 `2.34 s` 才连续低于 `0.001`；这不是从 MFA 末边界开始的单调尾音衰减，超过当前 `0.50/0.80 s` 范围。旧项目词级扫描从 CTC `2.24 s` 出发可以寻找最后的衰减，但即使把整词尾延至约 `2.34 s`，也**不能**将多出的约 `1.08 s` 全归给最后 `/ɴ/`：音素内部 `/ɯ/`/`/ɴ/` 分界仍需重新声学对齐。应先在 MFA 前用带归属的 CTC 词段和声能确定裁剪/词尾，再重跑该词或短语的 MFA，并用声能、原文、跨轨坐标及完整停顿审计验收。未达到这些条件前保留筛选。

上述对照阶段只新增诊断和修复约束，当时**没有改变代码或共享 TextGrid**；随后已执行下述修复。`0045`/`0049` 的原失败包现位于 `diagnostics/historical-filtered/`，原 WAV/CTC 坐标和输入哈希均保留。

### JA-026 尾词延伸实施、真实 MFA 复测与共享发布（2026-09-30）

在 `src/japanmfa/mfa/timed.py::expand_timed_segments_with_audio` 增加 CTC 段末的**弱尾音确认**：既有高能量起落搜索若未触发，但 CTC 原锚点前两帧和锚点后一帧仍超过 `max(3×噪声底, 0.001)`，最多向后扫描 `0.35 s` 寻找首次连续三帧安静；允许额外三帧确认，不跨越下一段 CTC 锚点之间的中点，裁剪末端继续只在安静区补至多 `0.12 s` 上下文。原始 `anchor_end` 不改，`acoustic_end_limit` 和实际 crop end 单独记录。先写失败回归再实现；定向单测涵盖弱尾音、只有一帧跨越锚点及安静后独立声岛，`tests/unit/test_mfa_timed.py` **26 passed**，非真实模型测试 **460 passed / 15 deselected**。该规则是给 MFA 增加**受证据约束的输入上下文**，不直接把新增时长全部分配给末音素。

真实原 WAV/TXT/CTC 重跑见 [两条候选运行与发布回执](../runs/galgame-tail-extension-canary3-20260930/report.json)、[独立声段对照](../runs/galgame-tail-extension-controls-20260930/report.json)：`0045` 的第三个 CTC 段原尾 `2.56 s`，新 crop 尾 `2.69 s`、声学活动尾 `2.57 s`；重新 MFA 后「思う」末段在 `1.92–2.56 s`，具体 `/o/ 1.92–2.06`、`/m/ 2.06–2.42`、`/o/ 2.42–2.45`、`/ɯ/ 2.45–2.56`，后面 `2.56–2.69 s` 是实际安静上下文。`0049` 的原 crop 尾 `2.24 s`、新尾 `2.46 s`，声学活动尾 `2.34 s`；MFA 重新分出 `/ɯ/ 1.20–1.49`、`/ɴ/ 1.49–1.94`，既有 MFA 后尾音声能规则再把 `/ɴ/` 末尾延至 `2.34 s`，其后停顿的 10 ms 最大 RMS 低于 `0.001`。两条 `postprocess.json` 均 `passed=true`，当前四轨/标点及配套 WAV 的候选审计 **2 files / 0 failed**。这不是人工音素金标，尤其 `0045` 的 `/m/`/`/o/` 词内切点仍可听审；但“台词落在静音里”的声能问题已消失。

反例 `0004`、`0007` 用同一新代码重跑，仍分别因原文外独立声段和词首错位造成 `alignment_acoustic_coverage` 失败，均未发布。候选通过后，只向共享 `mfa/` 新增 `0045`、`0049` 的 TextGrid/WAV 同名配对；共享全目录 [发布后审计](../runs/galgame-tail-extension-canary3-20260930/shared-audit.json) 为 **39 files / 0 failed**，包括连续停顿、四轨标点/边界、配对 WAV 和停顿声能。两组 WAV 与源 WAV 的 SHA-256 相同，配对 SHA-256 见 [共享发布回执](../runs/galgame-tail-extension-canary3-20260930/shared-publication.json)。先前 37 组未覆盖；更新前的报告、审计和旧筛选索引留在该运行目录 `before/`。`0045`/`0049` 的失败证据移至 `diagnostics/historical-filtered/`，当前 `filtered/index.json` 为 **11** 条；共享 `mfa/mfa_run_report.json`、`mfa/mfa_audit.json` 和 `mfa/current_status.json` 已反映 **前 50 条累计 39 发布、11 筛选**。这是 37 条旧合格产物加两条本次定向重跑，并不声称本次再次运行了全部 50 条 MFA。

### JA-028：MFA 输入分组改变边界；整条与批量裁剪各有复现（2026-09-30）

用前 50 条相同 WAV、转写和 518 项锁定读音分别做“50 个整条 WAV 一批”和“188 个已有 CTC 裁剪段一批”，各真实运行 MFA 两轮。两组每轮均完成校验和对齐，约 **21–24 秒 MFA 时间**；原 188 次逐段启动累计约 **3845.7 秒**。完整方法、逐样本状态与原始 TextGrid 见[对照报告](../runs/galgame-mfa-strategy-compare-20260930/report.md)和[逐条表](../runs/galgame-mfa-strategy-compare-20260930/per-sample.csv)，共享副本放在同项目 `diagnostics/mfa-strategy-compare-20260930/`。测时不包含 CTC/ASR、后处理、四轨输出或网络复制。

**复现的边界问题：**整条方案可让 `0007`「驚かせた」词首回到 **3.33 s** 并覆盖 **3.38–3.73 s** 的真实起音，批量裁剪词首却在 **3.80 s**，把起音留在长停顿中；`0037` 整条词首 **5.20 s** 覆盖 **5.25–5.28 s** 的起音，裁剪词首 **5.28 s** 留下停顿尾漏声。反面，`0013` 整条第二词被放到 **2.78–2.94 s**，而 CTC 起点是 **4.96 s**，相差 **2.18 s**；`0055` 整条原始词 **0.47–0.53 s**，远离 CTC **0.72–0.96 s**。因此声能覆盖和时间戳约束必须同时保留，不能把整条对齐或裁剪结果作为无条件真值。

相同声学/时间戳诊断下，整条两轮 **36/50、38/50** 通过，批量裁剪两轮 **34/50**；整条可疑有声停顿样本 **3、2** 条，裁剪均 **12** 条；整条超过 200 ms 的原始段边界 **15、14/376**，裁剪 **7、8/376**。整条在两轮均恢复原筛选的 `0016`、`0024`、`0025`、`0033`、`0037`、`0043`，却使原已发布的 8–9 条退化；批量裁剪也使原已发布的 5 条退化。原因是裁剪对 MFA 施加局部词序/时间上下文限制，整条允许更多跨段迁移；把多个裁剪段放进一个 MFA 语料还会改变语料级归一化/抖动下的具体边界。后一点是基于相同输入与不同输出的**推断**，具体贡献尚未单独消融。

**处理状态与剩余范围：**实验只产生原始 MFA TextGrid 和按现行规则复算的诊断，未进行假名/声调四轨投影，也未改变共享 `mfa/` 的 39 组 TextGrid/WAV 或 11 条筛选。批量裁剪适合作为加速候选生成方式，整条可用于有声边界漏失的局部参考；逐条替换必须先过声能、CTC 例外证据、词内读音及完整四轨审计。未获人工音素金标，自动诊断通过不能证明词内每个切点精确。

### JA-028 追加：旧项目原生锚点机制、整段优先实现及 50 条复测

旧项目实际生产配置 `configs/qwen3_0915all_full_20260914.yaml` 启用 `mfa.native_anchor_fallback: true`。`scripts/run_pipeline.py::_build_native_anchor_corpus` 从已调整的 Qwen/CTC 词时间戳生成一个中性 `speaker` 轨的语料 TextGrid，`step_mfa_align` 用 `mfa align ... --audio_directory` 读取**完整 WAV**；MFA 在内部把 `speaker` 区间作为 utterance。正常词先各占一个窗口；短于 110 ms 的词先借用相邻静音，不够时才与最近词合并。原项目并非给每个时间戳手工裁出一份 WAV。原始时间轴上的静音因而仍可检查。证据为[旧项目实现](/mnt/local_E/MFA_Pause/repo/scripts/run_pipeline.py)、[旧配置](/mnt/local_E/MFA_Pause/repo/configs/qwen3_0915all_full_20260914.yaml)和[交接说明](/mnt/local_E/MFA_Pause/repo/handoffs/20260917T112752Z-qwen3-0915all-operational-handoff.md)。

本项目现已把默认 `--alignment-strategy hybrid` 改为：先对全部 50 条完整 WAV 做一次批量 MFA；仅对声能或时间戳明确拒绝的条目，依同一完整 WAV 与 CTC `speaker` 窗口再做一次批量 MFA；两种候选都经过相同的后处理、六轨生成和发布审计。回退窗口目前按已有 CTC **分段组**，不是旧项目逐词的 110 ms 借静音算法；这是剩余实现差异，不能声称完全移植旧项目。已接受的旧 TextGrid/WAV 即使新批次退化也保留，失败候选及原因留在运行目录。代码见 `src/japanmfa/mfa/hybrid_batch.py`、`src/japanmfa/pipeline.py`、`tools/galgame_mfa_hybrid.py` 与 `tools/galgame_mfa_from_ctc.py`；设计见[方案](hybrid-mfa-whole-first-20260930.md)。

用同一批已暂存输入与锁定词典、当前 `dither=1.0` 的真实 50 条整合运行[回执](../runs/galgame-hybrid-native-integrated50-20260930/hybrid-report.json)：整段批次 50 条 **22.20 s**，仅 14 条回退的原生锚点批次 **20.30 s**，含准备、后处理与本地发布的总流程 **66.95 s**；该时间不含最初 SMB 输入复制或 ASR/CTC 生成。单次候选 36 条整段通过、4 条锚点通过、10 条未通过。受 MFA 批次重跑差异影响，另一次相同配置的 14 条锚点复测为 3 条通过；因此不能把某一次的 40/50 当成恒定成功率。对照 `dither=0.0` 的同批试跑仅 **35/50** 通过、总流程 **68.18 s**，故保留当前 `dither=1.0`，不照抄旧项目中文模型的抖动参数。上述数字是试跑候选通过数，不等于当前共享目录的累计发布数。

本轮从整段候选新增发布 `0016`、`0024`、`0025`、`0033`、`0037`、`0043` 六组，旧 39 组 TextGrid 哈希均未改变；[发布回执](../runs/galgame-hybrid-native-first50-20260930/publication-receipt.json)显示共享审计 **45 files / 0 failed**，累计 **45 组 TextGrid/WAV 配对发布、5 条筛选**。当前 `filtered/index.json` 的五条为 `0004`、`0007`、`0013`、`0015`、`0020`；每条仍有 `source.wav`、`source.txt`、`ctc_source.TextGrid` 和失败证据。自动声能/结构审计不是人工音素金标。单次重跑曾拒绝已发布旧版的 `0030`、`0032`、`0042`、`0044`、`0050`，旧版因此未被覆盖；这些差异仍需以候选与旧版原始边界逐条听审/复核，不能以保留旧版推断新试跑错误。
最终非真实模型回归 **472 passed / 15 deselected**；共享目录重新运行 `audit_textgrid_pauses.py` 为 **45 files / 0 failed**，旧 39 组 TextGrid/WAV 哈希与发布前审计相同。完整运行摘要及共享副本见[报告](../runs/galgame-hybrid-native-first50-20260930/report.md)和目标项目 `diagnostics/hybrid-whole-first-20260930/`。

### JA-029：裁剪回退把有声静音写成合成空隙，造成假通过

`air_0030` 的旧式裁剪回退 `pipeline-timed/postprocess.json` 曾报 `passed=true`，把 **4.88–5.681 s** 尾停顿全记为 `synthetic_source_overlaps`，`unowned_speech_regions=[]`；但原 WAV 在 **4.99–5.13 s** 仍有活动。相同输入的完整 WAV + `speaker` 窗口回退 `pipeline-anchored/postprocess.json` 将该停顿保留为 `explicit_source_overlaps`，检出 `unowned_speech_regions` **4.99–5.13 s**，按 `alignment_acoustic_coverage` 拒绝。两份证据均在[50 条对照运行](../runs/galgame-hybrid-first50-20260930/)下，14 条回退[逐条表](../runs/galgame-hybrid-first50-20260930/anchored-fallback-comparison.json)可复核。它证明“通过”会受静音来源标记影响；声段是否属于台词还是音效仍需听审，不能凭本记录把它强行延进音素。

根因是裁剪 WAV 拼回原时间轴时产生合成空隙，后处理对合成与显式静音的归属检查不同，遗漏了原 WAV 的活动段。修复为默认回退保留原完整 WAV 和原时间轴，把 CTC 约束交给 `speaker` 轨；新增真实 50 条双方案对照与单测验证回退语料复制完整 WAV。旧裁剪模式仅供诊断复查，不再作为默认发布回退。剩余范围是历史已发布 39 组中可能有其他类似差异：当前共享审计 45/0 只证明已发布文件符合现行自动规则，不能替代对 `0030` 等重跑分歧的人工音素/声源校对。

### JA-030：逐词 MFA/CTC 融合尚未移植，直接照搬旧阈值会误移日语词界

旧项目 `scripts/postprocess_textgrids.py::_snap_to_ctc` 在 MFA 后逐词仲裁：0.3 s 门槛、0.15 s 中点、严重压缩/拉伸、`<unk>`/英文/NVV 特例、CTC 词界到音素的比例映射；但完整代码还含**争议区 MFA 音素证据、相邻 CTC 词界、标点/尾静音、长达数秒的膨胀锚点和词序不一致对齐**，不是单独四个数字阈值。本项目 `mfa/timing_review.py` 当前只审查 CTC **分段首尾**与最终音素拥有者的 0.2 s 差异，并对可证实的安静内缩放行；`postprocess.py` 已把 `CTC_word_boundary_snap` 列为未移植能力。缺少逐词仲裁会使词内大漂移只在段边界或声能失败时暴露。

对[整段优先 50 条试跑](../runs/galgame-hybrid-native-integrated50-20260930/hybrid-report.json)的原始 MFA、`asr.json` 和 `frontend.json` 做**只读**单位对照：38/50 条的 CTC 词与 Sudachi/MFA 词可逐项一一对应，另外 12 条词数或词界不同，不能按数组下标直接套旧规则；CTC 的 472 个内部词界中 463 个碰巧落在 Sudachi 边界。38 条的 356 个一一对应词里，26 个至少一端与 CTC 相差 >0.15 s，8 个 >0.30 s，19 个词的 MFA/CTC 时长比 >2（类别可重叠）。这些数字是**触发候选数量**，不是已证实错误数量。

反例 `0007`：「驚か」CTC **3.76–3.92 s**，完整 MFA **3.33–3.93 s**；原 WAV 在约 **3.38–3.73 s** 连续有声。简单按“>0.3 s 拉回 CTC”会把真实起音重新划进静音。`0013`：「例え」MFA **2.78–2.94 s**、CTC **4.96–5.28 s**，偏移超过 2 s，需重对齐相邻词，比例缩放旧音素不能提供新声段的真实内部切点。`0042` 的「男の子」CTC 为 **4.96 s 零时长点**，MFA 为 **4.31–5.19 s**；零时长锚点不能作正时长音素的缩放目标。`0015`「表」CTC 尾 **2.72 s**、MFA 原尾 **2.32 s**，附近另有 `2.56–2.66 s` 声岛，既不能盲信 MFA，也不能把整段静音线性拉成词尾。上述原始证据在试跑的 `pipeline-whole/<stem>/asr.json`、`frontend.json`、`mfa.json`（指向 `hydrated-whole/` MFA 原始 TextGrid）及 `postprocess.json`；`0007` 声能依据另见 JA-026。

可移植的是**逐词证据仲裁框架**：先按源文本字符跨度连接 CTC 单位与 Sudachi 词，跨界/零时长点只做约束而不直接缩放；每个争议边界同时检查原 WAV 声能、相邻词/标点归属与 MFA 音素；小幅、声学支持的词界修正可以重映射同词音素并重建 words/phones/phone_kana/phone_tone 共用时间轴；大幅错位、静音声岛或词序冲突应转入完整 WAV 锚点短语重对齐，复核未通过继续筛选。计划先用 `0007`、`0013`、`0015`、`0042` 等建立误移与漏声回归，再隔离试跑 50 条，比较旧发布与候选的声能/时间戳/四轨审计。**本条仅记录可行性和风险，未修改融合代码或共享产物；无人工音素金标。**

### JA-030 追加：声能约束的逐词融合已接入（2026-09-30）

在 `src/japanmfa/mfa/word_fusion.py` 新增源文本字符跨度匹配及逐词仲裁，并在整段/锚点 MFA 解析后、假名声调投影前应用。只有 CTC 词与 Sudachi 词恰好共用源字符区间、CTC 词为正时长、边界差在 **0.15–0.30 s**、原 WAV 10 ms 声能支持安静内缩或连续有声外延、相邻词不重叠且同词音素缩放比例在 **0.75–1.25** 时，才作中点修正。音素仍按原次序归属同词，并在后续从同一组最终注释生成 words/phones/phone_kana/phone_tone；报告保留原 MFA/CTC 差异、具体修正及大错位/零时长冲突。`0007` 的 >0.3 s 真起音、`0042` 的零时长点不会强拉。相关合成音频单测覆盖安静裁尾、有声尾保留、连续有声延长、零时长、大错位和不同分词；集成测试覆盖跨轨时间轴。

[正式 50 条隔离运行](../runs/galgame-fusion-singleload-first50-20260930/hybrid-report.json)中的**逐词自动修正为 0 处**：虽有 0.15–0.30 s 数值差异，但未同时满足声能与邻词条件。因而本轮不能声称靠逐词融合提升了实际 50 条的准确率；它已为后续有明确音频证据的输入提供安全路径。该隔离运行没有覆盖共享 `mfa/`；旧共享 45 对 TextGrid/WAV 与 5 条筛选仍保持原状态。剩余范围包括按真实人工音素金标调整声能门槛，以及更大错位时的短语级重对齐；不能用线性缩放代替声学重对齐。

### JA-031：一次 MFA 加载的速度收益及批次边界波动（2026-09-30）

现行双批次的前 50 条热缓存运行中，50 条整段 MFA **22.20 s**，14 条锚点 MFA **20.30 s**，管线总 **66.95 s**。[双批回执](../runs/galgame-hybrid-native-integrated50-20260930/hybrid-report.json)。在 `src/japanmfa/mfa/hybrid_batch.py::build_dual_batch_corpus` 把 50 个整段完整 WAV 和 50 个带 CTC `speaker` 轨的完整 WAV 放入一个全局唯一词典语料，`tools/galgame_mfa_hybrid.py` 只调用一次 `MfaRunner.align_many`；先复核整段，仅对失败项读取已生成的锚点结果。单次加载试验 **100 份候选 / 25.85 s MFA**，正式 50 条隔离重跑 **100 份候选 / 24.72 s MFA**，后者只审查 13 条锚点，总流程 **47.46 s**；对照旧 66.95 s 约快 **29%**。这两个总流程数字均使用已暂存 WAV/CTC 和热 G2P 缓存，不含初次 SMB 复制或 ASR/CTC。单次加载是真正的一次 MFA validate/align，模型只随该命令加载一次；不是让 MFA 的 `PretrainedAligner` 对象跨不同语料复用。

质量不能仅看总数：旧双批回执 **40/50** 候选通过；单次加载试验 **40/50**，正式隔离重跑 **39/50**，其 39 份 TextGrid/WAV 审计 **39/0 失败**。同一单次加载方案的两次试跑，`0020` 从通过变为 `alignment_acoustic_coverage` 拒绝；`0055` 在旧双批回执的锚点候选通过，在单次加载回退中因时间戳/声能冲突失败。整段原始词界也有 3 条较原双批结果变化 >50 ms（最大 `0046` 的 170 ms）。这些是语料组成或 MFA 抖动使边界变化的**观察**，各因素贡献尚未消融；不能把一次“通过”当成稳定金标。`0020` 在一次通过试验中原 WAV 停顿/标点审计为 0 失败，但正式重跑不稳定，因此没有向共享目录发布。保持 `dither=1.0`，已有合格旧结果不因新批次失败而覆盖。代码回归 **480 passed / 15 deselected**；用户输出仍应以共享 `mfa/current_status.json` 为准。

### JA-031 追加：去掉重复验证启动、单任务运行及 0020 发布

100 份内部构造的双候选语料仍会被旧 `MfaRunner.align_many` 先交给独立 `mfa validate`，随后启动 `mfa align`。因为准备阶段逐项验证文本/CTC/词典和完整 WAV 哈希，批次构造再次检查词别名及拷贝哈希，`BatchGridRunner` 逐条校验 MFA 输出词序，独立验证在这个专用入口属于重复冷启动。直接以默认并行数运行 `mfa align` 的隔离试验在 SQLite `word_interval_temp` 临时表处失败；指定 `--num_jobs 1` 后两次独立试验均生成 **100/100** TextGrid，分别约 **16.78 s** 和 **16.54 s**。两次原始 TextGrid 字节并不完全一致（75/100 不同，7 个文件词界差 >50 ms），表明 `dither=1.0` 的运行仍有边界波动；单任务只解决了本次 SQLite 错误，不能声称位级确定性。通用单文件/普通批次入口仍默认外部验证；仅双候选的受控入口采用 `external_validate=False, num_jobs=1`，完整 OOV/输出词序错误会在 MFA 运行或后续覆盖校验时拒绝，而不是直接发布。

[最终正式隔离重跑](../runs/galgame-fusion-singleprocess-first50-20260930/hybrid-report.json)用热 G2P 缓存和已暂存输入：**100 份候选一次 MFA 16.41 s**，先审 50 条整段、仅读取 12 条失败项的锚点输出，本地完整流程 **41.77 s**，自动候选 **40/50** 通过，六轨/WAV/停顿[候选审计](../runs/galgame-fusion-singleprocess-first50-20260930/audit.json) **40/0 失败**。与旧双批热缓存的 **66.95 s** 对照约快 **37.6%**；均不含首次 SMB 复制和 ASR/CTC。逐词融合仍是 **0 处实际边界修改**；此提速来自单语料、单 align 进程及去掉重复 validate。融合诊断的 `token` 字段一度被安全序列化误认成鉴权 token 而显示 `[REDACTED]`，已改为有明确豁免的 `token_index`，单测验证可保留整数下标。

`0020` 是新产物而非单靠总通过数判定：旧失败包在 **1.08–1.15 s** 与 **2.69–2.72 s** 各有显式 `<sp0>` 漏声，旧 `postprocess.json` 的两段最大 RMS 分别约 **0.0585**、**0.2771**。最终整段候选将第一段放入「し」末 `/i/ 1.05–1.13` 和「た」首 `/t/ 1.13–1.19`，第二段放入 `/ɴ/ 2.67–2.70` 与「を」`/o/ 2.70–2.91`；原 WAV 停顿声能、四轨标点及音频哈希审计均通过。经[发布脚本和回执](../runs/galgame-fusion-singleprocess-first50-20260930/publication-receipt.json)只新增 `0020` 同名 TextGrid/WAV，旧 45 对 TextGrid/WAV 哈希不变，共享全目录 **46 files / 0 failed**，累计 **46 发布 / 4 筛选**；原 `0020` 失败包转存 `diagnostics/historical-filtered/`。`0055` 的新试跑失败未覆盖其旧已发布合格对。最终代码回归 **483 passed / 15 deselected**，共享目录再次运行停顿审计 **46 files / 0 failed**。仍无人工音素金标，尤其 `0020` 的词内辅音切点不能由自动声能审计单独证明精确。

### JA-023/JA-026 追加：当前五条筛选项的临时候选 TextGrid（2026-09-30）

为便于在 Praat 中直接查看错位，按当前正式 `mfa/mfa_run_report.json` 与 `filtered/index.json` 的五条失败状态，从各条最后一次同原因失败运行的 `postprocess.json.final_phones` 重建标准六轨诊断候选，并复制字节一致的原 WAV。输出在 `/mnt/Raw/0922jap/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/filtered_diagnostic_textgrid_20260930_NOT_FOR_PUBLICATION/`；每条 `.TextGrid` 与 `.wav` 使用完全相同主文件名，逐条原因、哈希、声能和时间戳证据在同名 `.diagnostic.json`，总清单在 `index.json`。目录含 `NOT_FOR_PUBLICATION.txt`，这些候选没有写入正式 `mfa/`，不得当作通过结果。

当前五条为 `0004`、`0007`、`0013`、`0015`、`0020`。独立运行 `tools/audit_textgrid_pauses.py` 得到 **5 files / 4 failed**：五条结构错误、相邻停顿和跨轨标点不一致均为 0；`0004`、`0007`、`0013`、`0020` 按预期保留停顿漏声，分别可在 `0–2.80 s`、`2.11–3.80 s`、`0–1.39/1.45–4.96 s`、`1.08–1.15/2.69–2.72 s` 查看。`0015` 的 TextGrid 结构/停顿声能审计通过，但仍因 CTC 首段词尾 `2.72 s` 与能量修正后的 MFA 词尾 `2.45 s` 相差 `0.27 s` 而维持 `timestamp_mfa_disagreement`。因此审计的 4 个声能失败和 1 个时间戳失败共同解释五条筛选状态；不能将 `0015` 的声能审计通过误读为整个管线通过。

### JA-032：0verflow 首批出现新语料 G2P 不可映射（2026-09-30，待分析）

`/mnt/Raw/JapGalgame/0verflow_Shiny_Days/` 首批 50 条完整 WAV/TXT/CTC 的[本地运行报告](../.runtime/jobs/galgame-mfa-all/reports/bbf386d1ebdf4f819d7c711a732935e9.json)中，**13 条**在 MFA 输入准备阶段报 `no_mappable_pronunciation`，尚未得到 MFA 音素；例如 `wav/01-00-a00-0470__0verflow_Shiny_Days.wav`、同名 TXT/CTC，TXT 为「えー、ぶーぶー。」。该项尚无音素边界，时间坐标不适用。失败记录在本地 `filtered/0verflow_Shiny_Days/01-00-a00-0470__0verflow_Shiny_Days.json`，不能算作自动通过。根因尚未细化到具体读音/G2P 规则；需保留原输入、定位前端词读音与 MFA 音素映射的断点，修复后重跑这 13 条及相关读音回归。当前只验证了准备阶段明确拒绝、正式目录未为该失败项发布 TextGrid；尚无音素金标，也不能从这个游戏的 13/50 推断全库发生率。

### JA-023/JA-026 追加：0verflow 首批停顿漏声复现（2026-09-30）

同批运行有 **17 条**整段候选报 `alignment_acoustic_coverage`，部分锚点回退仍失败。例：`0verflow_Shiny_Days/wav/01-00-a00-0390__0verflow_Shiny_Days.wav` 的整段候选把 **1.65–2.77 s** 作为显式停顿，但原 WAV 在 **2.22–2.27、2.34–2.47、2.58–2.77 s** 有活动声能，最长连续 **0.19 s**，最大 10 ms RMS 约 **0.2161**；[whole 后处理证据](../.runtime/jobs/galgame-mfa-all/filtered/0verflow_Shiny_Days/01-00-a00-0390__0verflow_Shiny_Days.whole-postprocess.json)和同名 anchored 证据均为 `passed=false`。CTC/MFA 分段边界还存在 0.2 s 以上冲突，不能盲目把整个停顿吞进邻词。正式输出未发布此条。当前修复方向是逐条分辨台词、语气声与音效，再决定声学归属或维持筛除；自动能量仅证明停顿中有声音，不能证明它属于哪个音素。50 条中自动通过 13、筛除 37 是该游戏当前试跑，不代表整个 50 万目标集的质量比例。


### JA-033：单条 MFA 未生成 TextGrid 时错误中止全批（2026-09-30）

19 条定向重试中，16 条达到 MFA，整段/锚点双候选共 32 份。MFA 命令退出 0，实际输出 30 份；整段候选 `wb0009`（`uce24172ed1cd5a20dd0a8d43`）和 `wb0011`（`udbf810c7144e0837c1e5cae1`）没有生成 TextGrid。MFA 日志记录 89 段中 84 成功、5 错误，属于可按样本记录的对齐失败；旧 `MfaRunner.align_many` 的严格全覆盖检查把整批转成 `output_coverage_mismatch`，导致正常候选也无法得到最终报告。原批现场完整保留在 `.runtime/jobs/galgame-mfa-all/interrupted-work/add1b8c4c5044e2d8587b9e21277f58a/`，缺失候选的别名/输入哈希在 `partial-output-evidence/coverage-before.json`；具体源 WAV/TXT/CTC、原时间轴与时长见批次 `run/preflight.json`。

受控混合批次现在显式允许 MFA 返回预期输出的子集，`BatchGridRunner` 把具体缺失候选转为该条的 `missing_output` 失败；其余候选继续原文/别名、声能、时间戳、停顿及最终轨道审核。一般 MFA 调用仍默认要求全覆盖，意外文件、非零命令和错误路径仍停止，不伪造或发布缺失 TextGrid。新增 5 项回归覆盖缺失全部、缺失部分、意外输出及逐条失败，修复前全失败，修复后相关回归 **29 passed**，完整非真实模型回归 **516 passed / 15 deselected**。19 条已按同一状态目录恢复真实重试；不能把单测通过当作真实重试全部通过。原 13 份已发布成品仍保留原哈希。


JA-033 真实恢复验证：19 条重试完整生成逐条报告，**4 发布 / 15 筛除 / 0 输入预检失败**，其中缺失整段输出按 `missing_output` 记为失败，未中止正常候选审核。批次 `b1803ce3ff2c4744b0531c7f9f29bcff` 的报告在 `.runtime/jobs/galgame-mfa-all/reports/`；全量账本现为 **17 passed / 40 filtered / retry_required=0**，自动继续 `available-ctc` 全量阶段。发布后对累计 17 份成品用原 NAS WAV 完成完整配对、SHA-256 和停顿/声能/标点/轨道审核，**17 files / 0 failed / 成品其他文件 0**，原首批 13 份 SHA-256 不变；回执见 `verified-published-audit.json`。剩余筛除条目不是通过，音素边界仍无人工金标；CTC 仍运行，后续须在其所有分片终结后补扫。


### JA-021 追加：首个 500 条全量批次的真实映射缺项（2026-09-30）

批次 `cf70f94031c048f999f5321b82d2e842` 完整报告为 **204 新增发布 / 296 筛除**，累计发布 221、筛除 336。其中 118 条新输入报 `no_mappable_pronunciation`，另 5 条为 G2P `malformed_output`；这与 JA-032 首批 13 条是同类输入准备问题，前次 12 项修复的真实恢复结果已在 JA-033 回执。当前诊断用原 TXT 经同一前端、同一 token/model/adapter 指纹定位真实 G2P 缓存，没有从音频或文件名补写文本。完整断点见 `.runtime/jobs/galgame-mfa-all/mapping-diagnostics-batch500/report.json`、`proposed-rules.json`，例如 `0verflow_Shiny_Days/wav/01-00-a00-0670__0verflow_Shiny_Days.wav` 的对应 TXT/CTC；尚无 MFA 音素边界，时间坐标不适用。

只追加 36 条实际出现且能完整覆盖原莫拉的精确规则：フェ/ギ/シャ/チェ/ボ/ザ、双唇音前鼻音 m、プ/チュ/ニュ、长元音与鼻音/促音共用辅音的明确跨度；保留缺音、额外插音、异常读音及尚未解释的候选拒绝。68 个真实正例修复前全部失败，41 个负例保留拒绝；修复后相关回归 **146 passed**，全套非真实模型回归 **625 passed / 15 deselected**。所有 token 的真实缓存重查为 **91 条准备阶段可通过 / 27 条仍拒绝**，5 条 malformed_output 尚须独立保留模型输出诊断。规则、原 phone map、原失败 JSON 与缓存路径均保存在该诊断目录。

91 条改为 `retry_required`，定向清单为 `repair-batch500-mapping.jsonl`，账本暂为 **221 passed / 245 filtered / 91 retry_required**。健康的当前第二批继续运行，不重复启动 MFA；已确认 `run_all` 不跳过 retry_required，强制最终补扫会重试这些完整输入，后续监控须核对重试回执，不能把缓存映射和单测通过算作声学通过。

发布读回全审计见 `published-audit-batch500.json`：**221 files / 0 failed**，账本/输出数量 221 一致，源 WAV/TXT/CTC 配对完整，成品目录只有 TextGrid，原 17 份哈希全部不变。自动停顿/声能/标点/轨道检查不等于人工音素金标。本批另有 1 条管线 aligned 但最终发布审计拒绝，维持 filtered，未把其局部通过当作成品；还需保留最终拒绝原因诊断。

JA-021 本轮 G2P 格式异常补查：对原 5 条的完全相同读音请求逐条在独立 `mapping-diagnostics-batch500/mfa-root` 运行，5/5 返回且原莫拉全部可映射，真实输入/原模型输出保存在 `malformed-exact-rechecks/` 与 `malformed-exact-rechecks.json`。旧失败输出被原批清理移除，因此不能据重跑成功确定其原始根因；仍须监测复发并保留当前准备日志。5 条也改为待声学重试，同一清单共 **96 条**；最新账本为 **221 passed / 240 filtered / 96 retry_required**。此独立 G2P 检查没有发布任何成品，没有占用生产 MFA root 或干扰 CTC。


### JA-034：内部空格被作为读音词导致 tdmelodic 退出（2026-09-30，修复已暂存未应用）

第二个 500 条批次 `496a305523794dfd8ee64a29f4a37c0c` 完成 **280 新增发布 / 220 筛除**，累计 **501 passed / 460 filtered / 96 retry_required**。三条 `command_failed`（`0verflow_Shiny_Days/wav/02-00-a00-0770__0verflow_Shiny_Days.wav`、`0800`、`1160`）在 accent 阶段失败，尚无 MFA 时间边界。保留原 TXT、CTC 路径和前端证据见同名批次报告与 `batch-evidence/496a305523794dfd8ee64a29f4a37c0c/`。原 TXT 内部空格被 Sudachi 返回为 surface=" "、reading="キゴウ"；前端只跳过标点，导致空白送入 tdmelodic，实际重跑三条都复现卷积 `AssertionError: Output sizes should be positive`。完整请求和 stderr 在 `accent-failure-recheck.json`。

诊断时仅排除空白请求，三条均不再发生上述命令退出，声调解析结果逐项见 `whitespace-accent-diagnostic.json`，不等于完整准备或声学通过。最小修复是在已校验字符跨度、推进 cursor 后同标点一起跳过 surface.isspace()，不改原 TXT、原文轨、词字符跨度或从别处补文本。三条真实源文本回归修复前 **3 failed**；代码替换、原文件 SHA256 和测试已暂存于 `staged-whitespace-repair/plan.json`，生产文件尚未修改。当前健康第三批已加载旧 Python 模块；立刻改文件会使缓存源码指纹与已加载实现不一致，所以须等 align 子进程退出、父任务正在发布且当前 hybrid-report 已存在的批次间隙应用，再运行相关/全套回归和真实 TD 检查，标记三条 retry_required。不得中断健康批次或启动重复 MFA。

### JA-035：孤立小假名分词及无效声调输出的拒绝证据（2026-09-30）

`0verflow_Shiny_Days/wav/01-i0-b01-0780__0verflow_Shiny_Days.wav` 对应原 TXT「うん、ぎゅー。」被 Sudachi 锁为 ウン/ギ/ュ/ー，孤立 ュ 无法按既定莫拉契约切分，报 unexpected_exception。原文、前端和 traceback 已保存在 `batch-evidence/496a305523794dfd8ee64a29f4a37c0c/prepared/u5192f1531c11dd1b49ac35d1/`，当前维持筛除，没有猜读音、合并词或发布结果。另 `02-00-a00-0570` 的真实 tdmelodic 重跑返回「ア]ナ]タ」，第二次下降时已经低调，严格解析继续报 malformed_output（boundary=2）；属于 accent 输出，不能误标成 G2P 字典格式错误。原始输出保存在同批 `accent-failure-recheck.json`。无可靠声调候选时不能放宽解析或编造声调。

对首个 500 条中的旧 5 条 malformed_output，先前只检查了独立 G2P 返回及音素/莫拉映射，其原失败产物已清理，故仍不能确定失败阶段或声调解析是否恢复；这里更正此前“G2P格式异常”的阶段归因。这 5 条继续包含在 96 条真实重试清单中，须完整管线重试后按真实结果登记。

**2026-10-09 同类准备失败复发：** 批次 `2b56532d337049d390653f03183b959d` 的 2000 条 WAV/TXT/CTC 已通过输入预检，准备成功 1870、失败 130。完整报告保留在 `.runtime/jobs/galgame-mfa-all/reports/2b56532d337049d390653f03183b959d.json`；与改动前同一组源文件的 `.runtime/jobs/galgame-mfa-all/work/207db8355e0649eca363309a3d006cb9/run/prepared-bundle.pkl` 比较，130 个失败 stem 和原因逐项相同，故此次删除重复 WAV 存在性检查不是这些失败的成因。99 条 `malformed_output` 属于声调标记与当前解析规则冲突（97 条已低调时再次下降，2 条连续上升）；例如原源 `Alice_Soft_Evenicle_2/15831__Alice_Soft_Evenicle_2`，旧准备产物 `.runtime/jobs/galgame-mfa-all/work/207db8355e0649eca363309a3d006cb9/run/prepared/u0298ffdd432e7e76f838466c/frontend.json`，失败信息为 `a fall occurs while pitch is already low`。27 条 `unsupported_japanese_text` 是前端明确拒绝（12 条 ASCII 拉丁字母、15 条无稳定片假名读音）；例如 `Alice_Soft_Evenicle_2/14622__Alice_Soft_Evenicle_2`。4 条 `empty_output` 是原生 accent 请求返回空值；例如 `Alice_Soft_Evenicle_2/15833__Alice_Soft_Evenicle_2`。这批失败发生在 MFA 声学对齐前，尚无可信音素时间坐标；没有放宽解析、猜读音或将失败改写为通过。自动报告与旧准备包的逐项一致性检查是机器验证，不是人工语音金标。剩余范围是这 130 条的独立发音诊断；同批最终 1974 条筛除还包含后续对齐/审核原因，不能归入本项准备失败。

**2026-10-09 隔离修复验证（尚未应用生产）：** 只在 tdmelodic 单词标记违反当前声调过渡规则、同一表层/假名具有唯一 UniDic 重音值且受单词约束的模型最高分候选与该值相同的情况下替换标记；原始输出、替换值和依据保留在私有 resident 请求回执。无一致证据的专名和复杂词仍失败，不删除冲突标记后猜测音调。对原 18 个异常词的原生模型回放，仅「あなた」由 `ア]ナ]タ` 修复为 `ア[ナ]タ`；54 条原失败包含该词。使用同一 2000 条源三联和当前生产 phone map 在独立目录完整准备，结果 1870→1920 准备成功、130→80 准备失败，其中 `malformed_output` 99→45，4 条转为后续 `no_mappable_pronunciation`；其余 27 条 `unsupported_japanese_text` 和 4 条 `empty_output` 保持原失败。原 1870 条成功样本的 frontend/mora/MFA 字典共 5610 份逐字节一致。证据见 `.runtime/jobs/galgame-mfa-all/accent-recovery-probe-20261009.json`、`.runtime/jobs/galgame-mfa-all/accent-fix-replay-20261009/matched-replay-summary.json`、同目录 `run-matched/` 与私有服务请求回执。失败均发生于声学对齐前，暂无可信音素时间坐标；未发布任何修正 TextGrid/WAV。自动检查不是人工语音金标，剩余 45 条声调异常与 4 条新暴露的音素映射失败须分别诊断。

**2026-10-09 修复证据与缓存部署补充（仍未应用生产）：** 私有 native 请求回执及批处理 `outputs.json` 均可保留修复词的原始标记、修正标记和判据；未修复的原输出原样进入现有拒绝规则。针对真实固定镜像的测试 1/1 通过，隔离分支完整测试 842 passed / 5 skipped。生产词缓存只读查询确认旧重音身份 `ec5043f7305ce10c4412f846398faddf93cb04f9c34476052b01fed7a55f8db0` 有 145391 条、旧 G2P 身份 `9de5e4bed180fa4365b72c72caa115cca53629efd52bc31864ffc496649f762e` 有 111968 条；隔离部署配置 `.runtime/jobs/galgame-mfa-all/staged-accent-recovery-20261009/cache-compat.env` 指向这两者，复用时仍校验词值 SHA。生产启动器尚未引用该文件，也未重启 resident 或写入正式输出。

**2026-10-09 同批后续失败修复与拒绝复核（隔离，未应用生产）：** 原 80 条准备失败中的 4 条 `empty_output` 均为 Sudachi 把「ゃ／ゅ／ょ」与前一假名拆成独立词；仅当原文相邻且前一假名可组成拗音时合并，紧随其后的长音符号也一并归词。私有四源回放中 3 条完成准备：`uceff47cebd42f1476ee73c60` 的「きょ」（自动 CTC 定位 0.48–0.56 秒）、`udd65d94dbfb96451da646de0` 的「ひしょち」（4.72–5.28 秒）及 `uf957c0dba9ff5f3f0b496cce` 的「ぎゅー」（0.48–0.64 秒）；`ub3eab28af998671c7a85d334` 的「きゃ」（0.48–1.12 秒）已越过空输出，但同句「おっぱい」（4.88–5.04 秒）暴露出 G2P 省略促音长度的映射失败。曾试加五条精确音素映射，在同一 2000 源回放得到 1926/74，却让 5 份原成功字典增加备选发音，并触发 10 项既有“缺失促音/长音须拒绝”回归失败；候选补丁与回放保留于 `.runtime/jobs/galgame-mfa-all/accent-fix-round2-20261009/rejected-map-candidate.patch`、`final-replay-summary.json`，已从隔离分支撤回，不能用于发布。仅保留切词修复并使用生产 phone map SHA `a07189cb24a762248ed43445b50a63823c198c989910c238c544c5caf6322ad9` 回放同一 2000 源三联，原 1920 准备成功/80 失败变为 **1923 成功/77 失败**；原成功的 frontend、mora、MFA 字典共 5760 份逐字节一致，三联输入 SHA 一致，详见 `final-safe-replay-summary.json`。剩余 45 条无足够词典/模型证据的重音冲突、27 条前端读音不明（12 ASCII、15 Sudachi 汉字原样读音）、5 条音素映射缺失/歧义，在 `remaining-77-review-queue.json` 逐条保留 WAV/TXT/CTC 路径、哈希、原模型输出或 G2P 候选；57 条带精确匹配的自动 CTC 词时间，仅供定位，不是人工音素或重音真值。失败仍在声学对齐前；本轮未发布修正 TextGrid/WAV，也没有把未经证实的读音、声调或缩短促音的音素序列写成通过。

隔离分支 `b41d6482daccf46dab0a5809fbff403eccc2c176` 的最终完整测试为 847 passed / 5 skipped，固定 tdmelodic 镜像真实调用另 1 passed；代码审查提出的「デュ／フュ」拆词边界已增加负/正向测试与实际 Sudachi 分词核对。上述测试和自动 CTC 定位均不构成人工发音或重音金标。

**同一根因的词表细分核对：** 固定 tdmelodic 镜像对剩余 45 条涉及的 14 种表层/读音直接调用原生 `get_n_best`，逐词返回与镜像哈希留于 `.runtime/jobs/galgame-mfa-all/accent-fix-round2-20261009/malformed-45-native-lexicon-inventory.json`。按失败源数计，40 条虽匹配读音，却被 UniDic 切成多个词条，无法从各词条重音直接得到整词唯一重音（`イシュタム` 24 条分成「イシュ＋タム」，`一度` 8 条分成「一＋度」）；2 条虽返回单条但 `acc=*` 无值，1 条 `パレード` 为 `acc=1,2` 多值；1 条 `三十三` 的指定读音匹配距离为 1；另 1 条 `パンパンパン` 有单一数值 `acc=5`，但模型约束后的最高分合法候选为 3 型（次高才是 5 型），不满足一致性门禁。故“缺少重音依据”不是说 45 条都在词表中完全不存在，而是现行严格修复所需的全词精确读音、唯一重音及模型一致性未同时成立。原始异常标记仍保持失败，未据分词条或多值条目臆造整词重音。

**输出契约澄清：** `segment_morae`、G2P、MFA 及 `_match_morae_to_phones` 的发音/音素匹配只依赖假名与音素，不依赖整词重音；但当前 `project_annotations` 要求每个非静音音素映射到已有 H/L 的 mora，`write_five_tier_textgrid` 强制非静音 `phone_tone` 为 HH/LL/HL/LH。故这 45 条的重音失败阻断的是现有完整带声调 TextGrid 的发布路径，并非证明其音素无法对齐。后续可在隔离流程先验证音素对齐，再决定如何显式处理未知声调；不能把未知声调伪装成 HH/LL，或称仅完成音素对齐已满足当前成品契约。

**2026-10-09 隔离解耦修复（未应用生产）：** 对原生 tdmelodic 仅 `malformed_output` 且去掉 `[`/`]` 后与锁定假名逐字一致的词，保留原始标记与逐词 `malformed_output_exact_reading` 回执，允许无 H/L 的 mora 继续通过原 G2P、375 条生产音素映射及 MFA；全未知 mora 组在私有六轨 TextGrid 的 `phone_tone` 明确标 `??`，已知/未知混组拒绝，错读音、空输出及模型命令失败仍拒绝。私有固定 2,000 源八进程回放在 `.runtime/jobs/galgame-mfa-all/accent-phone-decoupling-20261009/final-replay/private-replay-summary.json`：同一 WAV/TXT/CTC 哈希不变，准备成功 **1923→1958**、失败 **77→42**，35 条新增准备均明确记录未知声调；原 1923 条成功的 frontend/mora/MFA 字典共 **5769 份逐字节不变**，无成功源丢失。剩余 42 条为 27 不支持读音、15 不可映射音素（其中 10 条原重音异常在绕过声调后暴露映射问题），逐条保留于 `remaining-42-review-queue.json`。固定完整测试 **857 passed / 5 skipped**，真实 tdmelodic 镜像测试 **1 passed**。

35 条新增准备在私有目录完成真实声学和原门禁：**15 条私有通过、20 条失败**（15 `alignment_acoustic_coverage`、5 `timestamp_mfa_disagreement`），报告 `full-run-final/hybrid-report.json`；私有 TextGrid/WAV 独立 `tools/audit_textgrid_pauses.py` **15 files / 0 failed**，报告 `private-published-final-audit.json`，缺失的 20 份成品未算通过。例如 `u27ad9a388d3d7f2725fb087b` 的原 WAV/TXT/CTC 位于 `accent-fix-replay-20261009/source-full/{wav,txt,ctc}/` 同 stem，WAV SHA-256 `2fa06de6c59d95b78168f58adce4875d3df94f59e414d1d9bba3c2bc393884cd`；原「イシュタム」重音输出 `イ]シュ]タム`，自动 CTC 词定位 2.48–2.96 秒，私有成品首次 `??` 音素区间 2.48–2.62 秒；私有 TextGrid SHA-256 `ab84e87cc74c6ba80cad2199c70616fd9243d21d205115cf9004e9d1d71d6f50`。15 份私有 WAV 与源 SHA 逐一一致，`alignment.json` 和 `postprocess.json` 均注明 `tdmelodic_predicted_with_explicit_unknown` 及未知音素数。证据总览 `final-validation.json`。这证明音素可对齐且缺重音可显式表示，不证明 `??` 有人工重音真值；本轮不改正式账本、生产管线或 NAS 成品，现有消费者若只接受 HH/LL/HL/LH 需在应用前适配 `??`。

随后补齐输出契约：仅含 `??` 的新输出在 `alignment.json` 声明 `tone_encoding=HH_LL_HL_LH_??`，原已知声调输出继续声明 `HH_LL_HL_LH`；README 与输入输出、重音映射、局限文档均明确全未知 mora 条件及混合已知/未知拒绝。该元数据修正后完整回归 **857 passed / 5 skipped**；前述 15 份私有成品在元数据修正前生成，因此其 TextGrid/WAV 与声学审核有效，但不能当作最终 `tone_encoding` 字段的实物验证；该字段由隔离管线集成测试验证。

**2026-10-09 用户批准后应用主线及正式首批核对：** 在旧 `ce3889a6659542fd9e4aecb55add1682` 批次完整落账后暂停扫描器，保存旧正式账本一致快照 SHA-256 `cdb252b8f0c2a86f4d58bc9f092e6c8d9d0ab00239d2251ae125ba9761b93a5b`、原代码和启动脚本哈希及未提交工作目录，回执位于 `.runtime/jobs/galgame-mfa-all/accent-phone-decoupling-20261009/production-switch-20261009/`。旧扫描器/常驻服务全部退出后，仅将隔离分支 `9fe93b3` 的 29 个目标文件按原/候选哈希安装至主工作树，保留其余已有本地修改；启动脚本加载已验证的旧重音/G2P 缓存兼容身份，保留 8 个准备进程、8 个审核进程、固定镜像和原 NAS/账本路径。主目录完整回归 **999 passed / 5 skipped**、固定 tdmelodic 镜像集成测试 **1 passed**。新监督器、扫描器与两个 resident 实际运行，准备 resident 对「イシュタム,イシュタム」返回原异常 `イ]シュ]タム`，对「あなた,アナタ」返回有词典及模型依据的 `ア[ナ]タ`；没有以错误重音冒充已知 H/L。

新主线首批正式报告 `.runtime/jobs/galgame-mfa-all/reports/4fdeea2041c44d1f858b70a96a97624f.json`：2,000 条在切换前账本均不存在，准备成功 1,922、失败 78；最终正式账本 **650 passed / 1,350 filtered**，总耗时 234.30 秒，其中准备 27.29 秒、MFA 对齐 149.84 秒、审核 46.33 秒、发布 10.85 秒。8 条以未知重音完成准备，**4 条正式发布、4 条因 `alignment_acoustic_coverage` 继续筛除**，未将缺失 TextGrid 算通过。4 份新正式 NAS TextGrid 的 `??` 共 27 个音素区间，逐项与原 WAV、报告和账本 SHA 相同，独立 `tools/audit_textgrid_pauses.py` 对 NAS 配对 **4 files / 0 failed**；首次空目录审计为 0 files、不算验证，已以实际 4 对重审覆盖。完整逐源回执 `production-validation.json`、`first-batch-unknown-formal.json`、`first-batch-unknown-formal-audit.json`。例如原三联 `/mnt/Raw/JapGalgame/GIGA_Sucre_Sweet_and_Charming_Time_for_You/{wav,txt,ctc}/09010151__GIGA_Sucre_Sweet_and_Charming_Time_for_You` 对应正式 `/mnt/Raw/GalgameMFA/GIGA_Sucre_Sweet_and_Charming_Time_for_You/09010151__GIGA_Sucre_Sweet_and_Charming_Time_for_You.TextGrid`，首个 `??` 区间 0.90–0.98 秒，TextGrid SHA-256 `6ebb5b449ce83ede2fe43fd7301377273b170cc8c49003771db5f98c2571776a`、原 WAV SHA-256 `ed9abdfbb04e092b5abee3f3f5b29428cabd906519ac62c2297a8fbfc2e7216d`。这证明主线正式运行和自动质量门禁可接受显式未知声调；声学审核及 `??` 都不是人工重音/音素真值。原始音频扫描继续运行，后续批次以正式报告和账本统计，不把首批比例外推至全库。

持续运行的下一批 `7dc736252e2140d790798cbb8bc8f4d0` 也完整落账：2,000 源、1,938 准备成功、**407 passed / 1,593 filtered**，251.44 秒，其中准备 30.49 秒、MFA 对齐 162.42 秒、审核 44.23 秒、发布 14.30 秒；详见同名正式报告与账本。前两批的准备时间占各批约 12%，当前观察到的主要耗时在 MFA 对齐及审核，不能据此推断全库所有输入均无拥挤；原监督器仍每 30 秒更新运行状态。

JA-034/JA-035 发布审核证据：`published-audit-batch1000.json` 中新增 280 份已全部用原 NAS WAV 完整审核 280/0；原 221 份本轮重新读回哈希均不变、沿用前次完整审核，累计 501/0，账本/目录 501 一致、其他文件 0。自动审核不是人工音素金标。51 条本批 no_mappable_pronunciation 已依据保留前端和精确真实缓存重新核查，当前均仍拒绝，具体断点在 `mapping-recheck.json`，其中仍含合法映射缺项，后续须继续区分，不能笼统视作所有读音都异常。

### JA-034 verification update 2026-09-30T14:51:00Z
Applied only after third-batch aligning child exited and hybrid report completed, while parent publishing; retained staged-whitespace-repair/japanese.before.py and original SHA. Frontend skips whitespace after validating source cursor/span; original text, spoken tokens and offsets retained. Full non-real-model regression 628 passed /15 deselected, regression.log. Production frontend plus real tdmelodic 3/3 returned and all tokens parsed, production-accent-recheck.json. Three previous command_failed items now retry_required with repair-whitespace.jsonl, original failure JSON preserved in rejected-before. This fixes frontend/accent entry only; no new acoustic success claimed.

## JA-036 full pipeline acceptance review 2026-09-30T14:59:04Z
User requested review of low acceptance rate. Review evidence .runtime/jobs/galgame-mfa-all/pipeline-audit/review.json. Whole -> native full-WAV CTC speaker-window fallback -> final acoustic/punctuation/five-tier/source-hash gates verified in code and complete reports; first/second/third500 actual published204/280/261. Current762passed696filtered99retry; early data all0verflow_Shiny_Days, not random full-corpus quality estimate. SQLite reason stores whole_reason before anchored_reason, so diagnostic label can hide final fallback reason; effective current filtered reasons445acoustic/85timestamp/131mapping/35other. No standards relaxed. Independent original WAV recomputation for12deterministic failed cases:10with suspect pauses all values/classifications match;2have other unowned-coverage causes, pause check alone does not validate those cases. Not manual phonetic truth.
Two second-batch batch_input_mismatch cases02-00-b16-0090 and02-00-b12-0030 were initially no_mappable preparation failures, then whole review regenerated inputs after map changed and found no prepared batch entry. run_hybrid reviews all stage inputs rather than only successfully prepared subset; this plus mid-batch mapping version change produced misleading later stage reason. Current isolated real full retries4case in pipeline-audit/transport-recheck, independent MFA root mapping-diagnostics-batch500/mfa-root and cache, complete source immutable; these two now reach MFA and fail acoustic checks, no accepted publication. No global retry-completion claim; current job historical outcomes retained. Restrict future code/map edits to batch boundary; original prep evidence preserved. Pending possible surgical review-subset/reporting correction must retain initial stage failures and tests; no fix claimed for that orchestration behavior.
Alias case01-i0-c00-0060 reproduces MFA anchored raw output omission of jmfa_000011/12/13 (8 of11words). Raw artifact batch-dual/combined/aligned retained and alias-mismatch-diagnosis.json. Guards correctly reject incomplete content; do not fabricate missing owners. Second aliascase01-i0-b01-0370 current isolated rerun has full word coverage but fails acoustic review, suggesting original MFA output variability; original raw output lost in prior cleanup, cannot prove original cause. Missing-output/alias rejects remain model failures, not valid data-quality conclusions. Third500 failed preparation/review JSON preserved batch-evidence/<batch>. Third new261 published full sourceWAV acoustic/structure audit0fail, old501 hashes unchanged; cumulative762/0, TGonly.

JA-036 orchestration correction staged: staged-preparation-review-repair/plan.json contains exact9line subset change; test_preparation_review_repair.py reproduces current original processing blocked preparation input (red1fail), proposed module tested only in-memory with all project tests plus new regression629passed/15deselected. Production code has not changed; current fourth batch remains healthy. Planned correction only copies prepared-success source WAV/TXT into whole review subset when preparation failures exist, preserves initial failure outcome, and leaves all fallback/acoustic/publication gates unchanged. Must apply at safe batch boundary with original SHA check, preserve before file, copy new test into tests/unit, verify relevant/full and real pipeline. Proposed in-memory tests are not production or acoustic completion.

JA-036 verified production repair 2026-09-30T15:37:01Z
User requested automation stopped until repairs complete. Native heartbeat paused; MFA own process group3369901 terminated only after verified identity; state locks released; interrupted-work/be8fc52fe090405dac6ff8bd0036f635-user-pause retained intact and no fourth-batch publication counted. CTC16 healthy workers untouched. Applied staged subset change with original SHA guard and retained galgame_mfa_hybrid.before.py; new test installed tests/unit/test_galgame_preparation_review.py. Full production non-real regression629passed/15deselected. Isolated root real-validation ran immutable sources01-00-a00-0060(normal) and01-00-d10-0230(ガッコウmissinggeminate); normalaligned and fullpause/energy/structure auditpassed, badpreparationexcluded from whole-input preservingno_mappable. Onlylocaldiagnosticcandidate created; NAS762hashes/output not replaced. Automation remains paused;99queuedcompletepipeline retries and remaining mapping investigations not claimedcomplete.

JA036 whole-versus-anchor acceptance evidence 2026-09-30T15:51:20Z
User asked whether whole-file MFA causes energy mismatch. Whole-vs-anchor observational report pipeline-audit/whole-vs-anchor-review.json:689acceptedwhole+73acceptedanchors,615fallbacks;387whole acoustic rejects include28recovered+327still acoustic failed after anchors.445finalacousticrejects are already fallback results;430have energy-bearing pause overlapping actual raw MFA explicit silence. Of282second/third preserved failures,184use2–12windows and191have active ranges overlapping inside CTC windows rather than only outside windows. Native anchor corpus retains original complete WAV with TextGrid speaker-window utterances, not physical per-word WAV crops; modewhole consumes rehydrated native segmented output on original axis. Therefore whole-first alone is not established as cause, and switching to physical cuts is not yet tested. Energy presence alone does not identify speech versus BGM/breathing or correct mora ownership. User pause remains respected; no automatic job resumed and no standard relaxed.

JA-034 recurrence: stale shared frontend cache after source fix (2026-09-30T18:00Z)
Current resumed500 batch56a6598b082b4101875ca591b5077b5e prepared frontend snapshots for02-00-a00-0770/0800/1160 still contain3 whitespaceキゴウ tokens each. Exact cache result SHA and paths retained in stale-frontend-cache-diagnosis/cached-evidence.json; production JapaneseFrontend fresh recomputation3/3 removes all whitespace tokens and historical before source recreates cached kana exactly. _adapter_id(old)==_adapter_id(current): frontend identity ignores tokenizer and has no implementation version, so the existing fingerprint hits pre-fix cache. This confirms cache bypass of JA034, not rollback of source fix. No current loaded code/cache changed. Surgical operation staged in stale-frontend-cache-diagnosis/plan.json: archive only three exact stale frontend cache entries with SHA guard at safe own batch publication boundary, then mark these same sources retry_required after current outcomes are recorded and verify fresh shared-cache/fullpipeline retries. All quality gates stay strict; fresh frontend proof is not acoustic acceptance. Current99 preparation snapshot91withMFA/8without, five oldmalformed plus these3; remaining5 root cause not yet asserted pending final report. All raw realMFA TextGrids and JSON snapshots copied tobatch-evidence to prevent historical cleanup loss.

JA034 stale-cache targeted recovery verified after batch completion: original500 report archived and affected3 outcomes recorded command_failed; next activebatch aliases verified disjoint. Three SHA-guarded private frontend entries archived to stale-frontend-cache-diagnosis/archived-cache; actual fresh productionfrontend payload3/3 restored and production StageCache hit readback0whitespace3/3. Receipt old/newhashes retained. No source/code/maps/gates changed;3 keys requeued in sameSQLite after current final report. Counts1039passed916filtered3retry; this cache repair is not acoustic acceptance.

JA035/JA021 malformed scope clarified by fresh real accent replay after resumed500: all five former malformed retries completed initial preparation with frontend/asr evidence but failed accent beforemora/MFA; original old stage remains unknown because artifacts lost. Current real original full-token tdmelodic replay5/5 returns commands0 with full outputlinecoverage, yet parser strictly rejects あなた->ア]ナ]タ(two sources),オレンジエド->オ[レンジ]エ]ド(two),一度->イ]チ]ド(one), fall occurs whilepitchalreadylow. Exact request/stdout/stderr/tokenpositions and receipt retained malformed-accent-recheck-resumed500/<alias>/, summary.json. This is a current real accent-model malformed output, not G2P failure/data-quality proof; no fabricated accent or relaxed parser. Remains filtered, not repaired. Resumed500 published277/filtered223; original99 actual result{"filtered": 45, "passed": 54}, finalrejectreasons{"command_failed": 3, "timestamp_mfa_disagreement": 10, "alignment_acoustic_coverage": 27, "malformed_output": 5}.JA034 stalecache3requeued aftertargetedcachefix;allothers have actual terminal reports.

### JA-021 resumed1000 new exact mapping gaps (staged only)

Batch d8fb724facfd4c4cb158f0b2ab28cc80 has 49 real locked-reading G2P mapping rejects. Current production map recheck retains all49. Exact cached request evidence and source token/mora JSON retained in batch-evidence/d8fb724facfd4c4cb158f0b2ab28cc80/mapping-recheck.json. Proposed12 literal rules cover observed long vowels, palatalized ギャ/リャ/リョ, dz+ɨ in ズ/ヅ, コウ/ゾウ long vowel and ッ+ク kː. Current production red12/positive3negative; independent proposed full regression644 passed/15 deselected after moving two older legal mapping-only unresolved candidates ジツリョク and チェック to positive. Missing/wrong sokuon remain rejected. Proposal exact whole-request recheck recovers 24 of49 preparation conditions, 25 still rejected; this is not acoustic acceptance. Plan and proposed files in staged-mapping-repair-resumed1000. Production code/map/tests/ledger statuses unchanged. Apply only own final report complete, aligning child exited and parent publishing, originalSHA verified; preserve before; actual full regression and all historic currently-filtered mapping recheck needed before queuing retries.

JA-021 staged proposal follow-up: exact current SQLite219 filtered mapping cases checked against retained prepared token/mora+unique full-reading G2P cache;68 preparation-ready under proposal,123 still reject,28 lack retained full preparation evidence. Production mapping not applied and SQLite statuses unchanged. These counts are preparation diagnostics only. published-audit-resumed1000.json confirms new328 source-WAV full automated checks and old1039 unchanged, cumulative1367/0.

JA-021 生产应用与真实补查（2026-10-01，resumed1500）：旧批4a295121cc8a4cb99d172f3d27e72a5c完整报告归档、500条账本落地、对齐子进程已退出后，在本作业父扫描器批次间隙短暂停留13秒并finally恢复；CTC未动。原map及旧test SHA完全匹配plan，before文件保留，12条精确规则已真正应用。当前map SHA256 3125c635b075237c548470f537c77b44f29e293e4c2505d2bbe28fe4ed2a14a6；实际生产完整非真实模型回归644 passed/15 deselected，日志和实际回执在staged-mapping-repair-resumed1000/production-regression.log、apply-receipt.json。缺失/错配促音仍拒。
生产全账本254条原映射筛除按完整保留的token+mora+唯一全读音真实G2P请求复核：72恢复准备条件、146仍拒、36缺完整准备证据（历史28及本批8）。36又用独立MFA root和fresh cache逐条运行原WAV/TXT/CTC真实frontend/tdmelodic/G2P准备：5恢复、31严格no_mappable；原请求/模型输出/所有阶段JSON在missing-evidence-real-preparation/，receipt.json。77条仅加入全声学重试，不计通过；两新清单repair-mapping-resumed1500.jsonl(72)、repair-mapping-missing-evidence.jsonl(5)与旧repair-whitespace.jsonl(3)合并80条唯一，完全对应SQLite，80源三联完整。账本1597passed/1281filtered/80retry_required，所有80需真实完整回执，最终补扫不得漏。历史旧失败具体根因不因新准备返回而自动确认。

resumed1500发布与JA-033复发证据范围：4a批230新增/270筛除；新230用NAS成品读回及原WAV完成停顿、声能、标点、轨道、SHA和完整源配对审核0失败；旧1367哈希不变，累计1597/0且成品目录仅TG，见published-audit-resumed1500.json。最终筛除原因见batch-evidence/4a295121cc8a4cb99d172f3d27e72a5c/transport-failure-summary.json，18missing_output、4batch_alias_mismatch均正确保持失败且0发布，不能将模型输出失败算数据差或放宽完整性。示例源及全部逐条报告已留final-report.json和transport-failure-summary.json。本批原后MFA raw在两次heartbeat之间被work清理，现只有2062准备阶段JSON快照、无旧rawTG，具体原模型输出根因尚未知，时间坐标无法据缺失raw核实。新本作业专用preserve-work-evidence.py(pid2300134)每20秒仅保留本地work阶段JSON、TG与日志，JSON解析校验及size/mtime确认后原子复制到batch-evidence；不触碰源NAS/成品/代码/map/审核标准、不运行MFA，并在本作业supervisor退出后结束。实际首轮快照及状态见evidence-watcher-status.json，后续复发必须按新保留raw定位。下一健康批ef534eb8739e449492805c21f33d6072继续，不中断或重复启动。以上自动审核不等于人工音素真值。


JA-033 复发内部证据定位（2026-10-01，resumed2000，ef534eb8739e449492805c21f33d6072）：完整500批已落账240新增/260筛除，当前1837passed/1541filtered/80retry_required。完整最终报告与各阶段JSON/rawTG/日志在batch-evidence/ef534...，原MFA corpus.db亦只读备份留存。898个whole+anchor预期文件实际输出880，缺18（14whole/4anchor），另外8份anchor遗漏锁定wordalias；不能把所有未使用anchor异常都算成最终失败。实际最终拒绝16missing_output、1batch_alias_mismatch，全部0发布。真实MFA日志Done1462/errors28，SQLite28 utterance的alignment_log_likelihood为null且0word_interval（whole14/anchor14），所有18缺失文件/8漏词文件均对应内部失败utterance。这定位到MFA内部对齐/导出失败，而非NAS丢文件或解析器丢词；具体声学/解码触发原因尚未知。
例 0verflow_Shiny_Days/02-23-a19-0760__0verflow_Shiny_Days 的原whole wb0012全缺，CTC anchor ab0012的1.44–2.45秒utterance失败，2.88–3.91秒段返回后四词，前四锁定词069–072遗漏。原输入三联、同完整字典SHA和原模型固定，独立MFA root只用该whole/anchor原两输入真实重跑15.55秒，2/2返回全部8锁定词（jmfa_000069..076），见transport-real-replay/{input-provenance,receipt}.json及raw。原批whole449条/anchor1041段分别共享speaker，独立重跑1/2段；批上下文或归一化差异仅是假设，旧CMVN统计未保留，不能据一次小批成功宣称根因已修复或源音频差。此为raw完整性证据，不是全声学通过，未新增发布/更改源、生产代码/map/门禁/账本重试。历史4a批18缺失/4alias原raw仍缺，不追认其根因。
JA-021 新增精确缺项暂存：本批49条映射失败在当前生产map完整原token/mora+唯一有complete标记真实G2P请求复查仍全拒；细节mapping-recheck.json。staged-mapping-repair-resumed2000/plan.json暂存20条真实长音/促音/ヅ规则，所有49完整请求与真实输出副本保留observed-requests。原生产红灯20failed/6负例passed，提案仅在独立进程重定向目标map加载，完整670passed/15deselected；完整请求38恢复准备、11仍严格拒绝。生产map/code和账本未改，当前验证仍644项，未增加retry_required或声学通过。仅下一本作业安全发布间隙原SHA匹配后保留before应用、生产相关/全回归，再核对全账本终态映射失败，只把完整请求确认恢复者唯一加入声学重试；异常缺音、插音、错配促音拒绝不放松。

resumed2000最终发布审核：published-audit-resumed2000.json累计1837/0，新240全部NAS读回+原WAV完整停顿/声能/标点/轨道/SHA/源配对审核；旧1597重新读回哈希不变并保留前次全审计，成品目录仅TextGrid，目录键集合=passed账本1837。retry-manifest-verification-resumed2000.json确认80唯一待重试=3旧缓存+72映射+5补查，三联全部存在，仍需完整真实声学终态。下一健康500批26d02387bd3841d09adee8ecc83d2f65已启动，未改其已加载生产map或源代码。20规则提案最终670passed/15deselected、38恢复准备/11仍拒，当前生产仍644验证版；映射未应用、36旧提案统计被38覆盖，未增加声学通过或retry_required。自动审核不等于人工音素金标。

JA-021 resumed2000暂存提案全账本复查：global-proposal-recheck.json对当前226终态no_mappable逐项完整原请求核验，当前生产226仍拒；20-rule独立提案64准备恢复/162仍拒，证据缺失0。195采用原保留完整frontend/mora与唯一complete真实G2P请求，31采用此前独立fresh准备的完整证据；fresh不能追认历史原根因。所有结果仅暂存映射准备条件，生产未应用、账本仍1837passed/1541filtered/80retry_required、未声学通过。下一安全批次边界应用前后需重新核对当前终态集合和生产真实结果，再唯一排声学重试；不得把64加到pending或通过。当前健康26d批准备阶段持续推进，继续保留全部门禁与现场。


resumed2500实际回执（2026-10-01，26d02387bd3841d09adee8ecc83d2f65）：500批259新增/241筛除，当前2096passed/1782filtered/80retry_required。published-audit-resumed2500.json累计2096/0，新259逐份NAS读回+原WAV停顿/声能/标点/轨道/SHA/源三联审核，旧1837哈希不变且先前全审计链保留，目录仅TG且键=passed账本。最终筛除143声能/33时间戳/48no_mappable/2malformed/12missing_output/2alias/1unsupported。retry-manifest-verification-resumed2500.json再次确认80唯一完全等于SQLite且源三联完整；尚未完整声学重试。自动审计不等于人工音素真值。
JA-033复发：本批898预期raw实际879，19缺（whole8/anchor11）、3原始alias序列不完整；最终仅12missing+2alias拒绝，其他未使用anchor不可重复当最终失败。完整报告、raw-transport-coverage.json、transport-failure-summary.json及全部raw/阶段JSON/日志在batch-evidence/26d023...；例0verflow_Shiny_Days/02-24-b34-0050__0verflow_Shiny_Days：whole声能拒绝，anchor完全缺失，因此无raw时间轴可核实。真实MFA align.1.log Done1493/errors25；原corpus.db/特征因旧helper白名单排除而在work清理前未保留，当前不能把具体25内部失败逐条关联到19缺失/3alias，不能追认原根因已证明或修复。
JA-033诊断证据保留补强：仅本地preserve-work-evidence.py按原SHA保护，before和独立红绿回归在staged-evidence-preservation-repair/。增加.db只读SQLite backup（含已提交WAL变化，5秒期限）和.ark/.scp稳定快照；解析JSON、排除WAV/符号链接、size/mtime确认后原子发布，仍每20秒、仅本作业work至本地batch-evidence。原版真实fixture红灯database snapshot absent；提案两轮WAL提交均读回、integrity_check=ok、ark/scp一致、WAV/链接/半JSON排除。仅旧helper2300134退出并锁释放后换新helper3367583，singleton锁核验；主supervisor1120472/scanner1121103/align3352226启动时间不变，CTC未动。实际sourceSHA793cad793ebcb6edeb3041eb3006788135b19c773c396e14519a25eb548eccf5，apply-receipt.json。当前批仍准备阶段未生成模型DB，真实批次捕获效果待后续核查；快变阶段快照非保证，不能宣称MFA遗漏已修复。
JA-021 20规则仍暂存：两次应用前安全守卫未通过，第二次已明确发现新批adac6d6e034743f4a378765712d74af9子进程3352226；均未执行任何生产map/test替换。map仍3125c635...且47项生产代码散列无漂移、生产验证仍644/15，提案670/15不是生产验证。旧提案全账本226诊断64恢复准备/162拒不覆盖新增48，本批mapping-evidence-index.json保留48项原证据索引（只索引未复查）；下一真实安全边界应用及全账本复核必须包含新终态，历史缺证须真实fresh准备，确认恢复后唯一排全声学重试。新健康批不打断/改其加载版本；20提案尚未应用，未新增pending或声学通过。


JA-021 resumed3000生产应用（2026-10-01）：adac6d6e034743f4a378765712d74af9对齐子进程3352226退出、完整报告归档、500项账本已完整落地后，原SHA3125c635...匹配；仅本作业扫描器1121103在批次间隙短停约16秒并finally恢复，CTC未动。before map保留于staged-mapping-repair-resumed2000/japanese_mfa_v3_phone_map.yaml.before，新tests/unit/test_galgame_mapping_resumed2000.py已安装。生产map实际SHA84cb903ed33f834425d91f07ca7ba7e2ad2767a0c4f710c330d0d32c0455ca19，相关26passed0.96s、完整非真实模型670passed/15deselected14.79s，production-regression.log和apply-receipt.json。与原47项生产散列仅目标map变化，加新test现48项；startup-provenance保持原始。
全账本306终态no_mappable用完整原token+mora+唯一complete真实G2P复核：93恢复准备条件/213仍拒/缺证0，275原生产证据+31旧独立fresh证据。production-global-recheck-resumed3000.json保留逐项原reason/signature/batch/证据，不能用fresh追认历史根因。93仅唯一写入repair-mapping-resumed3000.jsonl和原sqlite的retry_required，不计声学通过；连旧80合计173唯一且完全对应SQLite、原WAV/TXT/CTC全在，retry-manifest-verification-resumed3000.json。当前2360passed/1925filtered/173retry_required，全部需真实全声学终态，最终补扫不能漏。新aef28cc13f1e472485a42e25a9ec3b87子进程3880031加载新map并健康，输入未包含这173条，不干扰或重复启动。
JA-033补强helper真实捕获验证：本批模型运行完成后，本地batch-evidence/adac...保留7060JSON/2797TG/11log/1DB/7ark/10scp。corpus.db只读quick_check=ok，1652内部utterance中18项无likelihood且0word_interval，原raw936预期922实际，14缺失文件与4漏alias文件全部对应内部失败utterance，model-transport-diagnosis.json。这定位本批MFA内部对齐/导出，具体decoder/CMVN触发仍未证明；现归一化/最终特征等已保留供定向诊断，不宣称根因或修复。例ab0240的0.48–2.16秒utterance缺锁定1766–1769，内部失败0词。实际最终报告10missing_output/2batch_alias_mismatch全部拒绝且0发布，不能把其余未使用anchor失败算终态。完整报告及最终原因在final-report.json/transport-failure-summary.json。
resumed3000批500实际264新增/236筛除：166声能/32no_mappable/26时间戳/10missing/2alias。NAS已发布且账本500落地，新增264和旧2096读回全审核正在执行；必须等待published-audit-resumed3000.json成功才宣称2360/0，非模型回归/准备恢复不能替代声学完成。

resumed3000最终成品核查完成：published-audit-resumed3000.json累计2360/0，新264逐份NAS读回原WAV完整停顿/声能/标点/轨道/SHA/源三联审核，旧2096重新读回SHA不变及旧全审计链保留，目录仅TG且集合=passed账本2360。当前2360passed/1925filtered/173retry_required，173仍待完整声学重试；生产670非真实模型不替代声学审核，自动成品审核不等于人工音素真值。aef批3880031初期NAS/source/audio I/O增长已核实，prepared暂0不单独判死，主/CTC健康。监控维持ACTIVE，最新代码/实际回执/限制已写heartbeat-latest。


resumed3500实际回执（2026-10-01，aef28cc13f1e472485a42e25a9ec3b87）：500项154新增/346筛除，当前2514passed/2271filtered/173retry_required。published-audit-resumed3500.json累计2514/0，新154逐份NAS读回原WAV停顿/声能/标点/轨道/SHA/源三联审核，旧2360哈希不变且全审计链保留，目录仅TG且集合=passed账本。最终261声能/30no_mappable/18时间戳/25missing_output/7alias/3malformed/1unsupported/1phone_in_silence，自动审核不等于人工音素金标。173清单唯一=SQLite且源三联全部存在，仍待完整声学重试，最终CTC完整补扫不可漏。
JA-033复发原证据：本批932预期raw实际904，28缺失文件与20漏alias文件全部对应原模型DB50内部失败utterance（1457总项），likelihood为空、word_interval=0、quick_check=ok，真实MFA日志Done1407/errors50。model-transport-diagnosis.json与全部JSON/rawTG/DB/ark/scp在batch-evidence/aef...保留，实际最终仅25missing+7alias严格失败0发布，未使用anchor不能重复计终态。例ab0310的1.20–2.16秒缺锁定jmfa_002021–002025；定位内部对齐/导出，具体decoder/CMVN触发未证明，不宣称修复或源数据差。
JA-021新增10条精确合法ポ/ミャ/ピ及长音/促音规则仅暂存staged-mapping-repair-resumed3500/plan.json，生产map84cb903e...保持且48项散列无漂移、生产验证仍670/15。原生产新回归10failed/6异常负例passed；仅独立map重定向并将旧合法スポット/ポイステ两项由未解决负例移为正例，完整686passed/15deselected10.26s。全243当前终态映射失败完整原请求复查：生产243拒、提案33准备恢复/210拒、缺证0；新批30中13准备恢复/17拒。完整原token/mora/G2P缓存证据副本及global-proposal-recheck.json保留。提案未应用、33未排retry_required且不计声学通过；下一自己子进程退出/完整报告归档/账本落地/安全批次间隙且原SHA匹配时保留before应用map及新test、旧test两合法项移动，再生产相关/完整回归、全终态原请求复核和唯一排完整声学重试。新健康04e4681648ac477d99f0adfbae356a78子进程[213328]已启动，不打断或改其加载版本。


resumed4000实际回执（2026-10-01，04e4681648ac477d99f0adfbae356a78）：500项210新增/290筛除。published-audit-resumed4000.json累计2724/0，新210逐份NAS读回原WAV完整停顿/声能/标点/轨道/SHA/三联审核，旧2514哈希不变且保留前全审计链，目录仅TG且键=passed账本。最终201声能/31时间戳/30no_mappable/12missing/8malformed/3alias/2phone_in_silence/1reading_mismatch/1bgm/1最终候选审核拒绝。自动审核不是人工音素真值。
JA-021暂存10规则已真正应用：本批对齐子进程213328退出、完整报告归档、500条账本完整落地、安全间隙、原map与旧test SHA匹配后，仅本作业scanner1121103短停16.87秒并finally恢复，CTC未动。before map/old test及真实回执在staged-mapping-repair-resumed3500/；新test已安装，旧完整合法スポット/ポイステ移为正例，所有异常缺音/插音/错配促音负例保持拒。生产map SHA d12f4ef378f508a127579c323ac5a87674dd9e9506ba5907332350b91624c83e；实际相关125passed0.74s、全非真实模型686passed/15deselected15.37s，当前49项代码散列，startup原516证据不改写。当前全273终态映射失败完整原tokens/mora+complete真实G2P复查36恢复准备/237仍拒/缺证0；新30使用完整tokens/model/TerminalSokuonG2p生产adapter指纹精确定位缓存，避免同读音但不同表面词/offset出现多个缓存时误选。production-global-recheck-resumed4000.json记录完整原账本/证据。仅36唯一加入repair-mapping-resumed4000.jsonl并同sqlite由filtered转retry_required，未计声学通过。连旧173合计209唯一完全等于SQLite，原WAV/TXT/CTC全在，retry-manifest-verification-resumed4000.json。当前2724passed/2525filtered/209retry_required，全部209必须实际完整声学重试及最终补扫。
JA-033复发：本批922预期raw实际908，14缺文件/6漏alias文件全部对应原模型DB21内部失败utterance（1741总项），likelihood null且word_interval0、quick_check=ok，MFA真实Done1720/errors21；模型DB、特征、所有阶段JSON/rawTG/日志已保留batch-evidence/04e...。实际最终仅12missing+3alias严格失败0发布，未使用anchor不重复计终态。内部对齐/导出关联已证明，具体decoder/CMVN触发仍未证明，不宣称修复或源数据差。
JA-023/JA-026最终门禁拒绝补充：0verflow_Shiny_Days/02-28-a22-0080__0verflow_Shiny_Days在whole阶段aligned但最终发布拒绝，候选仅保留本地final-candidate-diagnostics-resumed4000/ub5dfbf88bac894b61198ffd1/，0 NAS发布。源WAV SHA与pipeline audio receipt一致f45dcda4...；最终五轨结构/标点/相邻停顿均正常，但0–2.25秒停顿的0.54–0.78秒声能超过最终阈值0.0211593433，active0.21s/longest0.11s、suspect1。前段原postprocess阈值0.0224019912，active0.18s/longest0.07s故前段通过；最终导出phone几何/静音可视合并后的审计参考不同，精确变换贡献仍待诊断。原postprocess、TG、两阶段声能范围/阈值及WAV SHA均保存receipt.json；保持严格最终拒绝，不补造音素、不放宽标准，也不把自动声能当人工音素真值。


resumed4500实际回执（2026-10-01，178f4a97b365430ea2062ded3d7a24c1）：500项281新增/219筛除，当前3005passed/2744filtered/209retry_required。published-audit-resumed4500.json累计3005/0，新281逐份NAS读回原WAV完整停顿/声能/标点/轨道/SHA/源三联审核，旧2724哈希不变且全审计链保留，目录仅TG且集合=passed账本。最终145声能/34时间戳/28no_mappable/6missing_output/3unsupported/1malformed/1bgm/1alias。retry-manifest-verification-resumed4500.json再次确认209唯一=SQLite且原源三联完整，仍需全部真实全声学终态和最终完整补扫。自动审核不等于人工音素金标。
JA-033复发：本批936预期raw实际930，6缺文件/4漏alias文件对应原模型DB10内部失败utterance（1847总项），likelihood NULL/word interval0、quick_check=ok，原MFA日志Done1837/errors10；全部模型DB/特征/rawTG/JSON/日志保留batch-evidence/178...。例whole wb0067源0verflow_Shiny_Days/02-i1-c04-0290__0verflow_Shiny_Days，0–6.1826875秒，内部utterance1109/1-1109，19锁定alias527–545全缺。实际最终6missing+1alias严格拒绝0发布，未使用anchor异常不重复计终态。internal-aligner-path-diagnosis.json保留现安装kalpy/gmm/align.py源码SHA副本与原日志：全部10项出现精确Processing，无零长度feature/missing graph跳过或Python异常日志。当前安装实现底层successful=false返回None，错误计数并回调，alignment/word写出跳过；这支持内部不成功对齐路径，不是NAS/解析器丢词。Retried只在成功后记录，其缺失不能证明没重试/beam耗尽；底层decoder/CMVN具体触发仍未证明，不修改生产或放宽门禁。
JA-021新10条精确合法ジェ/ジュ及ワー/ノウ/ゲー/ペー/ネー/ジャー/ッケー/ッピ映射仅暂存staged-mapping-repair-resumed4500/plan.json，status staged_verified_not_applied。生产map仍d12f4ef...、49项代码散列无漂移、实际生产仍686/15。新生产红灯10failed/6异常负例passed0.75s；初始独立全回归701passed/1failed/15deselected，失败来自旧完整合法コーディネーター仍为未解决负例。其原真实G2P完整[k,oː,dʲ,i,n,eː,t,aː]按新增ネー精确覆盖所有7mora，无缺音/插音/错配促音；仅暂存旧test此项由negative移positive，原SHA、diff及owners在old-test-expectation-diagnosis.json，其他异常负例保留。纠正提案预期后独立完整702passed/15deselected11.00s，proposal-corrected-full-regression.log，生产test/map未修改。全265当前终态映射失败完整原tokens/mora+唯一complete真实G2P请求复查：生产265仍拒，提案37恢复准备/228仍拒/缺证0；本批28中14恢复准备/14仍拒，global-proposal-recheck.json及observed-requests保存。37未排retry_required、不计声学通过；旧31fresh证据不能追认历史根因。下一自己aligning child退出、完整报告归档、500账本落地、安全批次间隙、map和旧test原SHA仍匹配时才保留before精确应用10规则、新test与旧test单合法项移动，再生产相关/全非真实模型回归、全当前终态原请求复核和唯一排实际全声学重试。当前新批3ad3f9da1da1432089f89a44b9f5a8dd child1202332已加载旧生产map，准备/IO持续增长，不打断或改其版本；CTC16健康。


resumed5000实际回执（2026-10-01，3ad3f9da1da1432089f89a44b9f5a8dd）：500项282新增/218筛除；应用映射后38恢复准备项仅转retry，现3287passed/2924filtered/247retry_required。published-audit-resumed5000.json累计3287/0，新282逐份NAS读回原WAV完整停顿/声能/标点/五轨/SHA/源三联审核，旧3005哈希不变且全审计链保留，成品仅TG且集合=passed账本。最终157声能/27no_mappable/26时间戳/6missing_output/1alias/1bgm。自动审核不等于人工音素真值。
JA-021上次暂存10规则已实际应用：3ad子进程1202332退出、全500报告归档和账本落地、原map d12f4ef...与旧test SHA吻合，在安全间隙仅本作业scanner1121103短停18.30秒，finally恢复，CTC未动。before map/旧test保留staged-mapping-repair-resumed4500/；新test_galgame_mapping_resumed4500.py安装，旧完整合法コーディネーター移为正例，其余缺音/插音/错配促音继续拒。生产map SHA979880914571c62e1853de6d89df35d0700d12a9a4230445768a031862db6cc4；实际生产相关141passed1.41s、完整非真实模型702passed/15deselected16.35s，51项现代码散列无漂移，startup原516未改写。全292终态映射筛除按完整原tokens/mora+唯一complete实际G2P请求复核38恢复准备/254仍拒/缺证0，production-global-recheck-resumed5000.json；仅38唯一加入repair-mapping-resumed5000.jsonl和同SQLite retry_required，不计声学通过。连旧209共247唯一=SQLite，原WAV/TXT/CTC全在，retry-manifest-verification-resumed5000.json；均须完整声学重试和最终补扫，历史31fresh证据不能追认历史根因。
JA-033复发：946预期raw实际937，9缺文件/2漏alias文件全部关联原模型DB11内部失败utterance（1777总项），likelihood NULL/word interval0、quick_check=ok，真实MFA日志Done1766/errors11。DB/特征/全rawTG/JSON/log保留batch-evidence/3ad...；例whole wb0061源0verflow_Shiny_Days/02-i3-a00-0240__0verflow_Shiny_Days，0–3.338625秒，内部utterance1300，6锁定alias jmfa_000576–jmfa_000581全缺，原WAV SHAeaa8bb56b98740046ed3fbac83b7f1f936ab4f257fc3e0245347710bf65f5216。最终仅6missing+1alias严格拒绝0发布，未用anchor不重复计终态；model-transport-diagnosis.json和transport-failure-summary.json保存全源对应。内部对齐/导出关联已证明，具体decoder/CMVN触发仍未证明，不宣称修复或笼统源数据差，旧raw/DB丢失批仍不追认。
JA-021新增6条精确合法ヒャ/ミョ/キャー/グー/クー/シイ规则仅暂存staged-mapping-repair-resumed5000/plan.json，status staged_verified_not_applied；生产map979...及旧test SHA cfdbc07...未改写，新test未安装。生产红灯6failed/6异常负例passed0.59s，独立提案714passed/15deselected11.76s；只将原完整合法ラシイ长iː和ミョウ完整mʲ/o/ɯ从旧未解决负例暂移正例，短ラシイ缺イ、缺促音、插音、错配促音等负例继续拒。全254当前终态映射原请求复查：生产254拒；提案35恢复准备/219拒/缺证0，本批余26中8恢复/18拒。global-proposal-recheck.json和observed-requests保存，35未排retry_required，不当声学通过。后续自己child退出、完整报告归档、500账本落地、父安全间隙、原map/旧test SHA匹配后才保留before精确应用、新test安装和旧test两合法项移动，再实际生产相关/全回归及全当前终态原请求复核、唯一排完整声学重试。新批6793dacca3fa43a28dcc9972c4be4762 child1749354已加载当前生产979...、准备和IO增长；保持健康版本。CTC16、父scanner/helper锁正常，原源和其他作业未动。


resumed5500实际回执（2026-10-01，6793dacca3fa43a28dcc9972c4be4762）：
最新实际resumed5500覆盖旧3287计数及6规则暂存提示：500批6793dacca3fa43a28dcc9972c4be4762完成283新增/217筛除；40映射准备恢复转retry后当前3570passed/3101filtered/287retry_required。published-audit-resumed5500.json累计3570/0，新283 NAS读回原WAV完整停顿/声能/标点/五轨/SHA/源三联审核，旧3287哈希不变且全审计链保留，目录仅TG、键=passed账本。最终142声能/25no_mappable/23时间戳/19missing_output/4malformed/2unsupported/1alias/1bgm。全报告、源键和JSON/rawTG/log/DB/ark/scp保留batch-evidence/6793...；数量必须重新读取。新健康500批3010b5a935de4a06b13cb5123e3242a0 child2282665已加载生产map768d8234...，源三联完整，输入与287重试交集和prepared/IO必须实时核验；中途JSON不当终态。父1120472/scanner1121103/helper3367583、CTC16健康，最近CTCsuccess约519.8万/remaining122.4万/failed1334，根447G/NAS83T可用，必须重新读取。不打断或改健康子进程已加载版本，不重复启动。
JA021上次暂存6精确合法ヒャ/ミョ/キャー/グー/クー/シイ规则已真正应用：staged-mapping-repair-resumed5000/plan.json现verified_applied。6793子进程1749354退出、全500报告归档及账本落地、原map979...与旧test SHA匹配，安全间隙仅自己scanner1121103短停20.7544秒、finally恢复，CTC未动；before map/旧test和apply-receipt保留，新tests/unit/test_galgame_mapping_resumed5000.py安装，旧完整合法ラシイ长iː及ミョウ移正例，短ラシイ缺イ、缺音/插音/错配促音负例继续拒。现生产map SHA768d8234cae4eae78b5bc95c90f0f49ebeea0a35e51410de635b4c5c9b666193，实际相关179passed3.15s、完整非真实模型714passed/15deselected16.93s，production-regression.log和apply-receipt.json；52项当前代码散列无漂移，startup原516未改写。历史独立提案714与当前生产714分开保留，生产回归不等于完整声学通过。
最新生产全279终态映射筛除按完整原tokens/mora+complete实际G2P请求复核40恢复准备/239仍拒/缺证0，staged-mapping-repair-resumed5000/production-global-recheck-resumed5500.json保留原signature/batch/reason及原请求。生产cache用完整tokens/model/实际TerminalSokuonG2p adapter fingerprint，不仅按读音挑结果；31历史独立fresh依据原receipt/source/完整frontend+mora及唯一complete完整G2P输入核验，其历史adapter fingerprint不能标作当前生产adapter，fresh不能追认历史失败根因。40唯一新增repair-mapping-resumed5500.jsonl，仅同SQLite filtered转retry_required，不计声学通过。连旧247共287唯一：repair-whitespace3、repair-mapping-resumed1500的72、repair-mapping-missing-evidence5、repair-mapping-resumed3000的93、repair-mapping-resumed4000的36、repair-mapping-resumed5000的38、repair-mapping-resumed5500的40；retry-manifest-verification-resumed5500.json确认287=SQLite且原WAV/TXT/CTC全在。所有287还需完整实际声学终态，扫描已越过者最后CTC完成补扫必须收齐。旧99实际54通过45筛除、3缓存在287内；旧96/99/80/173/209/247不可重复pending。新批25映射中5转retry，当前该批SQLite283passed212filtered5retry，原报告283/217保持。准备/G2P/714单测不计声学通过。
JA033最新6793原证据：938预期raw实际918，20缺文件/9漏alias文件全部对应原模型DB33内部失败utterance（1964总项），likelihood NULL且word_interval0、quick_check=ok，真实MFA日志Done1931/errors33、特征Done1964/errors0；model-transport-diagnosis.json、final-report.json、final-source-items.json、transport-failure-summary.json及DB/CMVN/features/raw保留。例whole wb0014源0verflow_Shiny_Days/02-i3-g01-0490__0verflow_Shiny_Days，0–7.36625秒，内部872/1-872，15锁定alias jmfa_000127–jmfa_000141全缺，原WAV SHA0eee109d856c2b25e9edf593add8eea430f567f546009083c34b09d3a86cd507。实际最终仅19missing+1alias严格拒绝、账本filtered且0NAS成品；未用anchor不重复终态。published-audit-resumed5500累计3570/0已保存postpublication_verification，原中途限制保留为历史。内部对齐/导出关联已证明，具体decoder/CMVN触发仍未证明，不称修复或笼统源数据差。
JA021最新2精确合法ギョ→ɟ/o、プー→p/ɯː（长元音跨两mora）仅暂存staged-mapping-repair-resumed5500/plan.json，status staged_verified_not_applied，无旧test预期移动。生产map768...不变，新test未安装。完整原真实请求エイギョウ（02-i3-g01-0640）、イギョウ（02-i4-a00-0670）、プール（02-i4-a00-0980）留observed-requests.json；生产红灯2failed/6异常负例passed0.43s，独立完整提案722passed/15deselected12.15s。全239当前terminal完整原请求复核生产239拒、提案13恢复准备/226拒/缺证0，本批20中3恢复/17拒；global-proposal-recheck.json明确31历史fresh完整请求身份及历史adapter fingerprint限制，不追认历史根因。13未排retry，不计声学通过。ギョ额外i、プー缺长mora、缺促音/错配促音/チュウチョ额外促音继续拒；ッチャッ合法变体未证明，维持拒绝不猜。独立验证初始暂存YAML缩进和测试缺ffmpeg PATH失败原件/日志保留，仅修正暂存提案/测试环境后得到722绿灯，生产未受影响。下一自己child退出、完整hybrid报告归档、500账本落地、父安全批次间隙、plan原SHA匹配才保留before精确应用2规则和新test，再实际生产相关/全非真实模型回归、全当前terminal原请求复核后只将恢复者唯一排完整声学重试/同SQLite并核验源三联；后续新增失败必须包含，历史缺证须真实fresh准备。当前2282665已加载生产768...，不能改其代码/map；他人SHA变化先比较不能覆盖。独立722/准备返回不是生产或声学通过。
实际MFA_ROOT_DIR独立.runtime/mfa-root-galgame-all；模型temporary_directory为自己批次run/batch-dual/combined/work，不能口述为字面同一目录；不移动健康已加载版本。

### 2026-10-01 resumed6000: 3010 batch, exact two-rule application and retained decoder replay

- Full batch3010b5a935de4a06b13cb5123e3242a0 finished266 passed/234 filtered. Original final reasons:170 acoustic coverage,24 timestamp disagreement,18 no_mappable,12 missing_output,5 alias mismatch,3 unsupported text,1 malformed output,1 BGM. Complete report/source map and model DB/graphs/features/raw remain under .runtime/jobs/galgame-mfa-all/batch-evidence/3010b5a935de4a06b13cb5123e3242a0. After two mapping recoveries in this batch, current ledger266 passed/232 filtered/2 retry; original266/234 report retained.
- JA021: own child2282665 exited, full500 archive and ledger committed, scanner1121103 start identity and all original code hashes checked. Scanner alone stopped22.128139s and resumed in finally; CTC unchanged. staged-mapping-repair-resumed5500/phone-map.before.yaml retained. Exactly ギョ→ɟ/o and [プ,ー]→p/ɯː with [[0,1],[0,2]] installed; no old-test moves. Actual production187 related passed3.51s and722 passed/15 deselected17.68s. MapSHA822b60eb0707677ffa8046264109bc0a3074a2018f8bb80270c48f6e48bc0362; test/full-request/before/apply receipts retained. All257 terminal original requests rechecked15 preparation restored/242 rejected/missing0; production-request-identity-verification-resumed6000.json verifies237 exact current full-token/model/adapter fingerprints and20 historical independent fresh receipt requests. Historical fresh cannot prove historical failure root.15 uniquely queued in repair-mapping-resumed6000.jsonl, total302=SQLite with complete WAV/TXT/CTC. Preparation/unit tests are not acoustic success.
- NAS published-audit-resumed6000.json:3836 cumulative/0 failed; new266 complete original-WAV pause/energy/punctuation/five-tier/SHA/source-triplet audit; old3570 hashes unchanged and full prior audit chain kept. Directory TG only, exact passed ledger keys. Automatic audits and five listened samples are not manual phonetic ground truth.
- JA033 recurrence:956 expected raw/938 actual;18 missing and8 partial-alias files all linked to26 internal failed utterances among1823, NULL likelihood and0 word intervals, quick_check ok. Actual logs feature generation1823/errors0, graph compilation1823/errors0, alignment1797/errors26. Final only12 missing+5 alias terminal failures, allfiltered and0 NAS output; unused anchor anomalies not counted twice. Whole source0verflow_Shiny_Days/02-i7-d00-0110__0verflow_Shiny_Days, wb0048/internal28/1-28,0–3.823375s,11 aliases415–425 all missing; WAVSHAffc60ba1e3bb94479c59f320ee98ccf9841986f4aebd8f468f5020bab3382382. Full diagnosis and final-source rows retained.
- Further JA033 diagnosis: decoder-frame-feasibility/receipt.json retained original graphs/features shows26 failed and26 controls have reachable final graph and nonzero frames; all exceed non-epsilon input-arc lower bound. This is only a lower-bound feasibility check, not proof of full duration adequacy. Initial sorted-reader ordering error retained and corrected by globally sorting kaldi keys; no production changes.
- decoder-retained-artifact-replay: original logged beam10/retry40, scales1/.083333/.1, carefulFalse, splice3+LDA and current own-root model/LDA copied privately with SHA. Same retained graph/features replay failed26/26 with retried=True, successful26 controls; controls' normalized likelihood, full alignment vectors and word vectors exactly match original saved outputs. Controlled replay changing ONLY retry_beam40→160 recovers26/26 with complete original alias order; no production search parameter, quality gate, status or NAS output changed. This proves search-width sensitivity for these retained inputs/current copied model. Original ephemeral final.alimdl/lda.mat were excluded by old evidence suffix list and lack original SHA, so do not declare full original-model identity, all historical beam exhaustion, CMVN cause, acoustic success, or repaired pipeline. Historical unknown roots remain unknown. Future repair requires original actual model/LDA capture and complete pipeline real validation through all unchanged gates.
- Evidence capture repair: old helper793cad... excluded .mdl/.alimdl/.mat, demonstrated red model snapshot absent. Only these suffixes and scope string added in staged-evidence-model-preservation-repair; before retained,2 committed-WAL sweeps/integrity/ark-scp/model exact/exclusion fixture passes. Separate real current own-root final.mdl/final.alimdl/lda.mat bytes snapshot SHA readback passed, root unchanged; not historical identity evidence. Own helper3367583 replaced by2884005 under singleton lock; SHAa97f91499b172c0d8fedfe243bed8de98284ab913cb33f1753e1b8a142625406. Main supervisor/scanner/child identities and all pipeline/map hashes unchanged. Future original batch model capture still pending actual stage verification; stable snapshots do not guarantee every rapid phase.
- Current next500 725e15df9d6b4b479fe3e6ad68820899, child2824128 start595302346, own root/map822b... loaded;500 source triples verified, no302 pending retry overlap. Prepared105, healthy IO; CTC16 still active. Startup provenance SHA unchanged. All repaired retries must receive full acoustic terminal results in final CTC-complete rescan; no CTC interruption or duplicate MFA.

### 2026-10-01 resumed6500: original model identity and controlled retry-search replay

- Batch725e15df9d6b4b479fe3e6ad68820899 full500 final223 passed/277 filtered. Final reasons190 acoustic coverage,32 timestamp disagreement,38 no_mappable,9 missing_output,2 alias mismatch,4 malformed,2 BGM. Complete report/source map/raw/models/DB/features/graphs retained under .runtime/jobs/galgame-mfa-all/batch-evidence/725e15df9d6b4b479fe3e6ad68820899. NAS published-audit-resumed6500.json4059/0, new223 full original-WAV silence/energy/punctuation/five-tier/SHA/source-triplet audit, old3836 SHA unchanged and previous full audit chain preserved; output directoryTG only, keys equal passed ledger. Automatic checks and five listened samples are not manual phonetic truth.
- JA033 recurrence:916 expected raw/906 actual,10 missing files and4 partial alias files all associated with14 internal failed utterances among1676, likelihoodNULL/word_interval0, DBquick_checkok. Final only9missing+2alias=11terminal filtered and0 NAS; unused anchor defects not counted again. Whole wb0067/internal826/1-826 source0verflow_Shiny_Days/03-00-b00-0701__0verflow_Shiny_Days0–2.5114375s, original jmfa_000574–576 all absent, WAVSHA3335d62f6a18bd5478a3ac73a485a136c799fa7b6ac6d7f02219d8ee272e4ed7.
- New helper actual production evidence verified: while original working files existed, final.mdl/final.alimdl/lda.mat stable source size/mtime and exact SHA matched helper-retained bytes; original-model-capture-verification.json retains original/retained paths, hashes and times. This now establishes original actual model/LDA identity for this batch; prior ephemeral models excluded by old helper remain unproven. Helpera97f... still singleton2884005; no production root or model change.
- Controlled decoder-retained-artifact-replay used captured ORIGINAL model/LDA, retained original graphs/features and original logged beam10/retry40/scales1/.083333/.1/carefulFalse/splice3, CMVNNone/deltasFalse/fMLLRNone.14/14 original failures reproduced with retriedTrue. Changing ONLY retry40→160, initialbeam10 unchanged,14/14 successful with original full alias sequence;14 success controls normalizedlikelihood/fullalignment/fullwordvectors exactly equal original saved output. receipts retain all vectors and model/graph/feature SHA. This proves search-width sensitivity of these exact retained inputs/models, not all historical batch root or CMVN cause, and decoder success is not final pipeline/acoustic truth.
- Independent full500 real pipeline experiment retry-search-full-pipeline uses original WAV/TXT/CTC SHA-verified pairing, copied private StageCache/root/models and all unchanged pipeline/final gates; outputs local only, no NAS/ledger publication or production code/map/search change. Initial experiment omitted JAPANMFA_TDMELODIC_COMMAND and defaulttdmelodic was absent; initial-environment-diagnosis/receipt.json exact command_start_failed red retained. Initial PATH hypothesis disproven; production actually configures docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb. One symlink diagnostic fixture rejected by source gate and preserved; copied fixture reproduces actual missing command. Corrected experiment uses exact production accent command and PATH, separate run-corrected-command preserving failed originalrun. Full result still pending at this note; status.json and diagnostic scripts identify own instance, no duplicate production MFA. Any wider production search repair still requires completed private full pipeline validation, relevant/full regression and own safe child-exited boundary with SHA checks; local decoder outputs not credited passed or queuedretry.
- JA021 full current280 terminal mapping original requests rechecked, all280 still rejected, missing0; current38 complete original production fingerprints in mapping-evidence-index.json, complete tokens/mora/G2P requests and unmapped details in mapping-unmapped-original-requests.json; no guessed/deleted/inserted phones or new rules installed. Production map822b60eb... and53 code hashes unchanged, actual production722/15 regression history retained. Current retry-manifest-verification-resumed6500.json302 unique=SQLite, source triples all present, no new retry this batch. These302 still need actual complete acoustic terminal reports and finalCTC-complete full rescan.
- Next own production500 b0d12a82a8a34f0191b2c6396e5856d6 child3342367/start595695729, independent productionroot and822bmap, full500 source triples and no302retryoverlap verified. Parent1120472/scanner1121103/helper2884005 preserved, startup SHA unchanged. CTC16 remains healthy; live counts require refresh.

#### resumed6500 private full-pipeline result and remaining control limit

- Corrected independent full500 run-corrected-command completed, actual MFA log beam10/retry160,1676 internal successes/errors0;916/916 raw grids, no missing or alias defects. All500 actual original source triplets SHA-verified; all unchanged final gates and local original-WAV pair audits completed. Private accepted223, filtered277:204 acoustic coverage,29 timestamp disagreement,38 no_mappable,4 malformed,2 BGM. All11 original final missing/alias failures still fail final acoustic coverage, zero accepted/NAS/ledger credit.
- Full-pipeline-comparison.json proves manifest/dictionary/final.mdl/final.alimdl/lda.mat exact original hashes. Regenerated FST archive and final feature archive hashes differ; this remains a full regenerated experiment, not an exact original graph/features single-variable full-pipeline replay. Equal accepted count223 masks3 original accepted becoming rejected,3 new local-only accepted and100 common accepted TG SHA changes. Lost original sources: ['0verflow_Shiny_Days/02-i7-d10-0040__0verflow_Shiny_Days', '0verflow_Shiny_Days/03-00-b08-0060__0verflow_Shiny_Days', '0verflow_Shiny_Days/03-00-a00-0210__0verflow_Shiny_Days']. New local-only sources: ['0verflow_Shiny_Days/03-00-a00-0300__0verflow_Shiny_Days', '0verflow_Shiny_Days/03-00-a00-0230__0verflow_Shiny_Days', '0verflow_Shiny_Days/02-i7-d03-0090__0verflow_Shiny_Days']. No inference that all boundary differences are caused by retry width, graph order, dither or CMVN without per-source evidence. Preserve all raw/grid/model/DB/feature/archive/reports/local candidates and initial failed environment run.
- Precise retained original-model/graph/feature decoder14fail/14control single-variable proof remains valid and separate from regenerated full500. No production search/config/map/code/gate/source/NAS/state changes, no retry queued or passed credited. Do not apply a wider production search based only on equal counts or internal success. Next diagnosis: compare per-source graph/feature semantics, isolate regenerated differences, and use controlled original-input decoding/export plus all final reviews for minimal retry policy validation. Historical missing model/DB/raw roots still unproven.

#### resumed6500 exact per-source inputs, failure-only retry, and native export (2026-10-01)

- Per-source graph/feature comparison joined all1676 segments by file.name, begin/end and full normalized alias sequence. All1676 original/regenerated graph FST contents are byte-identical after reading the keyed archive; all normalized state/arc signatures are also equal.1675 internal Kaldi keys changed (only1 unchanged), so the prior FST archive SHA difference does not indicate changed graph content. All1676 actual final13-dimensional MFCC matrices differ numerically, with identical frames/dimensions; maximum absolute delta37.126033782958984. Evidence: retry-search-full-pipeline/per-source-input-comparison/receipt.json and its saved diagnostic script. Feature differences are proven; no attribution to dither/CMVN/order without separate evidence. Preserve the preceding full regenerated experiment and its control limits as historical evidence.
- Original-input-retry-policy/receipt.json replays all1676 exact original model/graph/features at beam10/retry40 and beam10/retry160.1662 original successful utterances exactly reproduce all saved alignment/word vectors and normalized likelihood at10/40;14 original failures reproduce failure and recover complete aliases at10/160. Global160 changes alignment and likelihood for one already-successful whole source0verflow_Shiny_Days/02-i7-d04-0120__0verflow_Shiny_Days, wb0393/internal1625/1-1625,0–8.2009375s (word sequence unchanged). Keeping the original10/40 result whenever successful and adding10/160 only after failure preserves all1662 original successes exactly while recovering14; total1676 diagnostic decoder successes. This is a diagnostic minimal policy, not a production repair or acoustic pass.
- Original-input-native-export/receipt.json uses actual installed Kalpy Alignment CTM/phones_to_pronunciations and native MFA construct_textgrid_output on a PRIVATE original DB copy. Original successful intervals retained exactly; word/phone/pronunciation identity matches the independently generated identical lexicon. Baseline exports reproduce all906 original raw TextGrid SHA values exactly. Inserting only14 recovered original failed utterances yields916 real native exports;902 unaffected existing raw SHA values remain exact,14 files affected (10 formerly missing+4 partially missing). Original model DB SHAac78ecbdf4934387c3647774c7b431c7b481831978e99005d8a5af7d50bc7c44 unchanged. Recovered phone_goodness is explicitly0 because per-frame confidence was not preserved in this direct receipt; it is not treated as quality evidence.
- A private all500 original-input-final-gate-replay is in progress using these native exports and unchanged final original-WAV gates; it does not launch another MFA alignment or regenerate acoustic features/graphs. Saved script/status identifies own PID3705784; retain lock and work, do not duplicate. Final acoustic acceptance is pending this experiment's real terminal report. No production code/map/search parameter/quality gate/ledger/NAS/source modification, no new retry or pass credit. Historical missing artifacts still prevent retrospective root-cause claims; automatic checks are not manual phonetic truth.

- MFCC repeatability control: original and regenerated make_mfcc.1.log record identical parameters with dither1.0. On three exact SHA-verified private original waveforms (wb0067/0–2.5114375s, wb0393/0–8.2009375s, wb0000/0–6.2214375s), the installed MfccComputer called twice on the identical loaded waveform gives unequal features with logged dither1.0 (maximum deltas27.9732608795/25.3776035309/29.2305145264); changing only dither to0.0 gives byte-equal numerical arrays for each pair. Both original parameter dictionaries, six pairs of actual.npy outputs and sample identities retained in retry-search-full-pipeline/mfcc-repeatability-probe/receipt.json. This proves a mechanism for fresh feature non-repeatability in these three samples, not exact reproduction of all original feature bytes or exclusive attribution of all downstream differences. No production dither/config/model/gate changes.

- Original-input-final-gate-replay is now COMPLETE (receipt.json/status.json/run/hybrid-report.json), PID3705784 exited; do not repeat. Full500 real preparation, BatchGridRunner hydration, whole/anchored postprocessing, strict final pause/energy/punctuation/five-tier/source-SHA/pair audits completed on exact original native exports with no new MFA or feature/graph generation. The generated full manifest and dictionary exactly match original; all500 original WAV/TXT/CTC SHA rechecked. Local accepted223/filtered277, final reasons201 acoustic coverage/32 timestamp disagreement/38 no_mappable/4 malformed/2BGM. Accepted source set equals original223 and all223 accepted TextGrid SHA values exactly match original and local readback;0 old pass lost,0 newly accepted. All11 original final missing/alias failures now fail final acoustic coverage; zero production/NAS/state/retry credit. All916 raw exports have exact complete expected alias sequences,0 alias defects.
- This completes a controlled exact original-input decoder/native-export/full500 final-gate experiment for the failure-only additional160 policy, not production implementation or repair completion. Original1662 successful alignments remain identical;14 recovery internals and11 transport-to-energy rejections do not count as new acoustic passes. There is currently no staged/applied production search fix: implementing fallback only after original10/40 failure still requires surgical project integration, meaningful negative/unchanged-success regression and actual production-code/private-root validation, then safe own child-exited/report-archived/ledger-committed/SHA-matched boundary. Global retry160 has a demonstrated changed-success counterexample and must not substitute for failure-only retry. Recovered private confidence0 is not manual phone truth. Existing audited NAS outputs stay unchanged.

### JA033 / resumed7000: failure-only retry implementation staged and real validation (2026-10-01)

Production b0d12a82a8a34f0191b2c6396e5856d6 finished all500:177 newly passed/323 filtered. Final reasons are225 acoustic coverage,45 timestamp disagreement,23 unmappable,20 missing output,5 alias mismatch,2 malformed,3 BGM. Original950 expected raw/925 retained actual:25 absent and15 partial-alias files associate with41 NULL-likelihood/zero-word internal failures among1769 utterances; SQLite quick_check=ok. Sample wb0051/internal1688/1-1688, source0verflow_Shiny_Days/03-1m-a01-0180__0verflow_Shiny_Days,0–5.33125s, aliases419–425 all absent, WAV SHA7b9f55fcfeaffc09184cec31b75f202723ae6ab7c82822148a4ad0a1181cee4e. Only final20 missing+5 alias are terminal transport refusals, all filtered and0 NAS outputs; unused-anchor defects are not additional terminal failures. Full report/source identities/DB/raw/graphs/features/model snapshots and diagnosis retained under batch-evidence/b0d12a82a8a34f0191b2c6396e5856d6. Independent live original-working model SHA comparison was missed before work removal for this batch, so retained model snapshots do not retrospectively prove that specific live comparison; no exact decoder cause claimed here. Earlier725e original-model identity proof remains separate.

published-audit-resumed7000.json reads all4236 NAS TG hashes against passed ledger, full original-WAV final pause/energy/punctuation/five-tier/source-triple/SHA audit for177 new products, old4059 unchanged, directory TG-only and exact passed keys,0 audit failures. Initial audit context assertion stopped before177 audits because preflight records private work paths, not literal NAS paths; corrected only path resolution via original source key and kept SHA/gates unchanged, original failure note retained. Full303 current terminal mapping original tokens/mora/COMPLETE actual G2P inputs rechecked:303 still rejected,0 missing evidence; historical fresh identity/root-cause limits retained. All23 new mapping requests saved.302 unique retry manifests still equal SQLite with complete original triples; no new retries or acoustic credit.

staged-failed-retry-search-repair/plan.json is staged_verified_not_applied. Proposed module wraps this controlled one-job hybrid MFA process only, preserves original10/40 successful native tuple, adds10/160 only after native10/40 unsuccessful using pristine pre-call graph and identical features/models, carries all native per-frame likelihoods; ordinary MFA/G2P entry, installed Kalpy files, dither and gates unchanged. Native exceptions propagate and failed extra search stays failed. Stage red4failed/5passed, related31passed0.30s, full731passed/15deselected12.39s. Initial private full regression729passed/2failed/15deselected12.64s was missing README and upstream applicability reference in private checkout; copied original reference files only and retained failed log, no changed test expectations or production files.731 is proposal regression, not production regression.

Actual staged wrapper through installed GmmAligner using exact retained725e model/LDA/graph/features:1662 original successes preserve alignment/words/normalized likelihood AND per-frame likelihoods exactly;14 original failures recover with true native per-frame arrays retained. Actual native916 exports all SHA-identical to the earlier controlled original-input native exports, original DB unchanged; private DB confidence now actual native values, previous diagnostic0-confidence history retained and not elevated to quality proof. actual-proposal-exact-final-gates/receipt.json executes complete500 actual staged preparation/whole-anchor hydration/postprocessing/all unchanged final original-WAV gates without new MFA/feature/graph generation:223 passed/277 filtered, all223 accepted source identities AND TG hashes exactly original,0 old passes lost/0 new passes. Original11 final transport failures all remain strict acoustic coverage refusals.916 alias sequences complete; final201 acoustic/32 timestamp/38 mapping/4 malformed/2 BGM.0 NAS/SQLite/retry credit.

Separate actual proposed hybrid CLI full-private-validation/receipt.json uses own root/cache and verified original500 triple SHA, original manifest/dictionary/model/LDA exact. Native1676/errors0, actual failed-only extra attempts14 all successful, raw916 and0 alias defects. Complete final local222 passed/278 filtered,204 acoustic/30 timestamp/38 mapping/4 malformed/2 BGM,0 NAS/ledger credit. Fresh features contain dither variation, so this fresh local outcome is not an exact-original boundary comparison or manual phonetic truth. Exact original-input223-SHA preservation and fresh actual command/process propagation validation are separate proofs. Both experiments completed, do not restart.

Production code/map/search parameters have not been changed;53 current production SHA remain original, startup provenance unchanged. Current own child3859613/start596089054 in batchac19a9e6315d4f9ea32fad47173af792 remains healthy and has loaded old production. Application requires its exit, all500 report archived and ledger committed, safe own parent batch gap, all original/candidate SHA matching, before preservation, short stop only own scanner with finally-resume, exact3-file application, ACTUAL production related/full regressions and new hash/receipt recording. Do not globally substitute retry160 or change healthy loaded child; future retries require complete real final gates, not decoder/preparation credit. Historical missing original evidence and five listened samples' limited scope remain explicit.

### Preparation throughput diagnosis / resumed7000 (2026-10-01)

Human reported slow full-corpus progress. Production remains one sequential 500-source batch; this is full-corpus scope, not full hardware parallelism. Last b0d12a82a8a34f0191b2c6396e5856d6 report total 3118.3107s, preparation 2922.1347s, acoustic MFA 34.1782s. Six recent batches total 3114.7–3296.4s; preparation dominates. This is an engineering throughput limitation, not evidence of a stalled job or unavailable CTC.

Evidence: .runtime/jobs/galgame-mfa-all/preparation-performance-profile-20261001/{receipt.json,input,cold,warm,cache,mfa-root}; script/log preserved beside directory. Three original SHA-verified WAV/TXT/CTC source requests from retained 725e source-pairing were prepared with current production code, private model root and initially empty private cache. Local profile observes existing _run_utterance duration records and subprocess.run wall time without editing production. All 3 prepared successfully: cold 22.2748496s, warm 0.5778360s. Cold subprocesses: 3 MFA G2P calls 17.4154193s total; 3 tdmelodic Docker calls 3.7959454s. Warm cache: zero external subprocesses. Cold per-source G2P 6.8793/5.0578/5.5365s, accent 1.2453/1.3094/1.2560s. Audio/front-end durations small in this sample.

Confirmed mechanism: preparation runs serially per source; cache misses invoke separate G2P and tdmelodic processes for each source. Measured call time includes process startup, model loading and inference; their individual shares have not yet been isolated. Warm-cache speed is not a forecast for unseen source requests. Three samples are not a corpus-wide benchmark. Safe next performance proposal should target batched G2P/resident processing and bounded preparation concurrency while preserving complete request identities, ordering, strict mapping and final gates. No performance implementation applied, no production parameter/code/map/dither change, no acoustic alignment or NAS publication, no ledger/retry/pass credit; 53 production SHA values unchanged. Search-failure-only staged repair remains separate and awaits its already specified safe batch window.

### JA033 / resumed7500: failure-only retry applied at safe batch gap (2026-10-01)

Original production ac19a9e6315d4f9ea32fad47173af792 completed 500:160 accepted/340 filtered; cumulative ledger4396 passed/4260 filtered/302 retry_required. This entire batch used the old implementation, so none of its passes is credited to the new search repair. Final reasons:278 alignment_acoustic_coverage,32 timestamp_mfa_disagreement,12 no_mappable_pronunciation,13 missing_output,4 batch_alias_mismatch,1 malformed_output. Full parent/hybrid report and source identities archived in batch-evidence/ac19... . Full NAS readback audit runs separately as published-audit-resumed7500; its successful receipt is required before reporting postpublication audit complete.

Original raw evidence:974 expected/960 actual;14 absent files and9 partial-alias files all associate with23 original model utterances whose likelihood is NULL and word_interval count0, out of1748; original DB quick_check=ok. Only final13 missing+4 alias failures count as17 terminal transport rejections, all filtered and zero NAS publication. Example wb0009/internal1545/1-1545,0verflow_Shiny_Days/03-22-g23-0190__0verflow_Shiny_Days,0–6.4461875s,11 locked aliases jmfa_000073–000083 absent; WAVSHA b1da081e3900f09cf4d903febc998ce18ac3e226b10c17c1985e8eb4eeb2f4b0. model-transport-diagnosis.json and transport-failure-summary.json preserve full relations. This batch original live final.mdl/final.alimdl/lda.mat stable size/mtime and SHA were independently matched to retained copies before removal; original-model-capture-verification.json preserves identity. Association is confirmed; specific search behavior for these23 has not yet been replayed and prior725e proof cannot silently establish their cause.

Applied exactly3 previously staged files from staged-failed-retry-search-repair/plan.json, with all53 original production SHA,3 candidate SHA and5 validation receipt/log SHA matching. Original child3859613/start596089054 exited; parent complete500 report was archived and all500 source keys terminal in the same SQLite before SIGSTOP. No scanner child existed after STOP/race check. Only scanner1121103/start590522039 stopped18.368011s; finally SIGCONT restored it. CTC and other jobs received no signals. Before content/absence manifest preserved at before-production-apply/. New module SHA df8f3f9185d5f8f163ca8b84e1856b95274b826ecb739b7f911ee5b118dc90b6, hybrid847a492f3fe8fba4fec50b414e580ac8c32e6c350457d4f94a6975ee69a214ee, test34d8eb57a645400bc96c1281d9af39c5fb1853f12fb58a3e12e681c6a393b015. ACTUAL production related31passed0.25s and full731passed/15deselected17.64s, logs and apply-receipt.json retained; plan verified_applied. Actual current code hash dictionary55 entries, startup original516 provenance SHA unchanged.

Policy remains original10/40 success tuple unchanged; extra10/160 only on native unsuccessful10/40 using pristine graph copy/same features/model, preserving all real native fields. No global160, installed Kalpy, dither, map or quality gate change. Earlier actual proposal exact original500 final gates223/277 with all223 originalTG SHA unchanged and fresh real CLI222/278 are separate evidence, not new production acoustic outcomes. No NAS product changed by installation and no decoder/preparation credit or new retry queued. Next production batch must demonstrate actual driver use and all final gates; historical terminal transport retry selection must preserve complete final reasons, source triples, original request evidence and unique ledger state without assigning unproved historical root causes.

Current mapping recheck:315 terminal full original requests all still rejected,0 missing evidence,12 new original requests retained; no mapping relaxation. retry-manifest-verification-resumed7500.json confirms302 unique pending keys exactly SQLite, all original WAV/TXT/CTC present; all need complete actual acoustic terminal outcomes. This repair addresses missing/partial transport outputs, not the separately measured serial preparation throughput bottleneck. Automatic acoustic gates are not manual phonetic truth; listened5 samples remain limited evidence.

Performance measurement scope clarification (2026-10-01): the previously quoted52–55min/500 and b0 total3118.3107s are hybrid-report.total_seconds, not scanner end-to-end elapsed time. tools/galgame_mfa_from_ctc.py performs source preflight and copies before run_hybrid starts its timer; tools/galgame_mfa_all.py then audits/publishes/records after the child exits. These outer phases and source scan/NAS waits are excluded. Do not infer end-to-end550–580/hour or completion ETA from the inner phase timer alone. Preparation still dominates the measured inner pipeline; new batch191269 currently reads original NAS CTC/source preflight with rising rchar before preparation starts. No stalled-job claim or unmeasured startup-only attribution.

## 2026-10-01 — JapGalgame controlled hybrid preparation throughput

Human request: deploy the fast script and complete production verification. The automatic message heartbeat remains paused. The existing supervisor/scanner and SQLite continue; no per-source assistant approval is added.

Root cause measured in the existing b0/ac19 reports: preparation 2922.1347/2837.5136 seconds per 500 versus acoustic MFA 34.1782/33.8707 seconds. Serial per-source G2P and tdmelodic startup/model loading dominated. PhoneMap YAML was also parsed per source. The first batch proposal retained duplicate G2P inputs (4254 positions, only 900 distinct readings); native MFA processed all 4254 in 226.145 seconds with 3 workers. This initial full500 preparation took 348.6258 seconds; all original frontend/mora/dictionary/alias outputs and preparation failure reasons matched. Its full local pipeline passed224/filtered276; fresh acoustic features are not an exact-original-boundary control.

Final proposal in `.runtime/jobs/galgame-mfa-all/staged-bulk-preparation-repair`: controlled hybrid only batches isolated accent requests, deduplicates exact (surface, reading) pairs and exact G2P readings, restores every original token index/duplicate position/ordered pronunciation variant, invokes native G2P with 16 workers, and reuses the unchanged PhoneMap per pipeline. Cold source preflight and immutable WAV/TXT/CTC snapshots use 8 readers, exact preflight SHA validation, and local CTC/TXT during preparation. Original source triples are never written. Regular non-hybrid behavior and default G2P invocation remain unchanged; all automatic final gates and the applied failure-only acoustic retry remain.

`optimized-full500-cli-validation/receipt.json`: actual final proposal CLI, 500 original triples, empty cache, private root, real native models; 500 frontend,496 mora,458 dictionary,458 alias artifacts match the original exactly; all42 preparation failures retain their reasons. Native accent 8.2884 seconds; G2P16workers900readings 16.7784 seconds including command startup (native log11.907 seconds). Preparation57.8531; MFA32.0508; whole review31.6789; anchored16.0416; local publication42.5105 seconds. Source preflight17.2933 and snapshot29.9131 seconds. Complete experiment239.6776 seconds, including setup and verification; this is not yet production end-to-end throughput. Full local final result224 passed/276 filtered (201 acoustic coverage,31 timestamp,38 mapping,4 malformed,2 BGM), all500 receive final outcomes. Local accepted candidates are not NAS/SQLite passed credit. Fresh dither can change acoustic boundaries/results; do not attribute the old223/new224 difference to batching.

Red/green tests cover cache/result identity, duplicates/ordered variants, malformed accent and missing G2P isolation, exact native worker flag, source snapshot order/SHA and mutation rejection. Proposal related47 passed; full740 passed/15 real-model tests deselected. These tests are separate from real full500 validation. All initial failures and first proposal evidence are retained. Actual production installation requires the original own child exit, full500 report and same SQLite committed, original55/candidate hashes unchanged, own scanner safe gap with finally-resume, production regressions and before rollback copies. Production application and throughput are recorded separately in apply-receipt and production-throughput receipts. Automatic checks are not manual phonetic truth; only5 historical listening samples exist.

Production application follow-up: original batch9100 complete500 (140 passed/360 filtered) and same SQLite committed. Own scanner stopped20.415917 seconds and resumed; existing CTC and loaded old child were not interrupted. Production related47 passed1.43s and full740 passed/15deselected18.52s; actual current code hash dictionary59 entries, original startup SHA unchanged. Exact before copies and apply receipt retained; no prior accepted product was overwritten by this application. First new real production batch c04db66064a846c6b8844d4e6482e290 uses the final batch implementation; its complete automatic outcomes and throughput remain under observation.

Real production completion: c04db66064a846c6b8844d4e6482e290, all500 terminal in original SQLite,170 passed/330 filtered through unchanged automatic final checks and NAS publication. Preparation64.4213s; native MFA36.8480s; hybrid231.0083s. Source preflight17.1554s and snapshot28.0758s. Child startup to all500 committed422.7454s (7m02.745s), including the parent final source verification/NAS publication/ledger; this excludes the preceding scanner selection gap. Application-start to this completion590.3335s also includes the20.4159s deployment pause and initial scanner selection, not a steady-state throughput or ETA. Cumulative4706 passed/4950 filtered/302 retry_required at completion; pending retries are not acoustic successes. No cumulative fullNAS audit was repeated. Current59 hashes and original startup SHA match, parent/scanner/helper identities unchanged and CTC16 continues. Production observer exited; automatic notification heartbeat remains paused. Receipt/source-key report and native evidence remain in the job directories.


## 2026-10-02 — filter analysis, isolated mora failure, resident timed route

Full terminal report statistics (not SQLite whole-reason shortcut):45094 filtered,36029 acoustic coverage,3525 timestamp disagreement,4059 no mapping,664 malformed,260 unsupported,251 missing output,51 alias mismatch,166 BGM,56 phone-in-silence,5 final publication audit,22 unexpected,2 input mismatch,3 reading mismatch,1 token span. Large differences by game are observed, not evidence that every source is poor or every filter is correct. Original per-source report identities retained in filter-analysis-20261002 and staged-resident-timed-repair.

Production halted12403d86... on original kuw_0001 Hakata source tokenメェェェェェ:segment_morae ValueError escaped bulk accent publishing. Before/source/raw failure retained; three expected-value failures reproduced before fix; catch only StageFailure/ValueError around per-source segmentation/parse, no successful cache for rejected input, serial reason preserved; neighboring sources continue.

Git e9ced98 contains native CTC time-crop/offset restoration. User explicitly selected that strategy. Resident timed path batches exact existing prepared crops and occurrence aliases, restores each using original align_timed_segments through BatchGridRunner, then runs full unchanged final original-WAV checks. Private native service owns only this job's paths; content SHA keyed acoustic models stay in memory, G2P rewriter and tdmelodic Converter stay resident; no installed package edits, map/dither/gates unchanged, original successful decoder10/40 unchanged and failed-only10/160 retained. Native request receipts log actual commands/results/load counters. Native model metadata set serialization initial prototype failure and initial symlink source-selection failure are retained; corrected tests and real runs replace neither history nor missing evidence.

Production regressions747 passed/15 real_models deselected19.15s. Two private full21 runs22.11s/20.01s,7accepted/14rejected;36native crops, model loads remain2, G2P loads1, unchanged server/accent PID.2previous filtered recover locally and3old accepted fail new route, so no blanket superiority claim and existing accepted NAS immutable. No private run credited to NAS/SQLite.40083 routing-dependent old filtered queued uniquely as retry_required (plus302 existing);5011 unchanged preparation/mapping failures remain. Original SQLite backups/manifests/source identities retained. Full production resumes after CTC16all terminal/remaining0 on same SQLite, independent original root, no duplicate scanner. Initial first production batch still pending; audit truth remains automatic rather than manually verified phonetic labels.


### 2026-10-02 常驻分时间戳正式作业验证

正式首两批 ed00c47c78a34ace83328b35bf2e1f94 / f2c4a07bc4314864bbb24ff9e3b6b0ad 各500源，完整报告归档、同SQLite终态落地：42/458 与62/438，通过合计104；104份NAS TG逐项SHA读回与账本一致。管线内部耗时102.8224 /107.9086秒，准备47.4682 /48.2648秒，MFA21.0919 /21.0835秒，复审33.6156 /37.4433秒；外层源目录选择、预检/复制、最终源SHA和NAS发布/账本另计，不能把21秒或管线内部时间当端到端。原1368 /1559时间戳裁剪仍按原样本边界恢复全局offset。两批实际native PID1687660，声学model_loads2→2/hits1→4，G2P loads1→1/hits0→1，声调Docker PID1689278保持；同模型按内容SHA复用，未全局更改beam或dither。

这些输入是历史筛除重试，不代表新语料整体通过率。首两批仍756声能覆盖、126时间戳差异、6静音内音素、3BGM、3映射拒绝；分时间戳路线并未证明全部历史筛除为误判。现有通过成品未重对齐，自动审核不是人工音素真值。代码65项SHA无漂移，startup原SHA保持；完整回执 staged-resident-timed-repair/production-verification.json。生产自主继续，消息自动化保持PAUSED。


### 2026-10-03 全部旧未通过项使用常驻分时间戳管线重试

人工指令要求新管线重试当前未通过并继续后续数据。在新管线已完成19批9500历史项、475恢复通过/9025再次筛除后，补入此前排除的5011旧准备/映射/文本失败（4059映射、664malformed、260unsupported、22异常、2输入、3reading、1token）；保留原report/reason/signature，SQLite只将这些尚未被新管线复验的filtered唯一转retry_required，0通过信用。已经新管线复验仍拒的9025保持终态，避免同管线无限循环。

完整报告与账本落地后，自己的scanner在无子进程、无新work的安全批次间隙短停；SQLite backup与manifest保留retry-all-unreviewed-20261003。重启自己的主/扫描/常驻/取证进程，从完整源目录起点继续同SQLite，确保新入队而已越过扫描位置的项不遗漏，之后连续处理尚未处理数据；没有并行重复生产。生产代码65项散列无漂移、门禁/模型参数不改，源和既有通过TG未改。新PID详见queue-receipt/heartbeat current_runtime。恢复时18537passed/9025filtered/35896retry_required；这里只是排队与自动作业恢复，5011仍需完整真实声学终态，准备/G2P成功不计passed。消息自动化保持PAUSED。


### 2026-10-03 取证helper目录清理竞争复发

自己的helper1709576在89986d48065748d090097a2b735d8baa/run/pipeline-timed/ue9391da9961d7fcc93aae9c0遍历时发生FileNotFoundError退出；主1709383/scanner1709384/native1709244持续健康。根因是批次完成清理目录可发生在exists检查和rglob迭代之间，原catch只覆盖逐文件复制，没有覆盖枚举。仅对这一rglob捕获FileNotFoundError、跳过本次已删除目录，下轮继续；原SQLite/WAL和稳定指纹复制逻辑未改。私有before实际helper注入清理竞争红灯退出、after两轮真实helper绿灯及文件捕获通过，py_compile通过，原helper备份/日志/receipt在staged-evidence-directory-race-20261003。只恢复自己的helper、没有重启主MFA。helper死亡到恢复的瞬态原始证据缺口保留，不能追认补证或人工音素真值。


### Preparation throughput optimization20261003 applied
Success-only exact word cache with immutable Docker image/G2P archive/implementation identity; partial native accent failure retained per source; deterministic8-process preparation; SHA-verified prepared state carried to every final gate; two windows overlap using separate preparation root and service. Preparation window2000, acoustic groups500. Original failed preparation manifest coverage repaired; unknown source type explicit. No quality threshold/map/dither change, no old passed rewrite.
Evidence: /home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-preparation-optimization-20261003/final-benchmark-receipts.json; exact-replay-final-verified/receipt.json (500 final outcomes exact/84 accepted TG SHA exact); prefetch-validation-corrected/receipt.json (1000 true scheduler entries/170.24s/overlap and owner-thread SQLite); independent-review-receipt.json; actual production-regression.log763 passed/15 deselected; apply-receipt.json. Initial private runner parent-path/integer-vs-float identity mismatch and too-long socket paths retained as failed harness logs, corrected without loosening state check. First prototype code identity drift retained; final benchmark identities all match. Cold final8 prep50026.66s,2000 73.46s, disjoint next50018.67s/1603 hits. These preparation timings exclude outer preflight/copy, acoustic/review/publication and are not global ETA. Automation staysPAUSED. Automatic checks not manual phonetic truth; previous5 listened samples/unknown historical roots and dither limits retained.

Production observation: /home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-preparation-optimization-20261003/production-verification.json; two2000 windows terminal635passed/1365filtered and664passed/1336filtered; report cadence346.1082s/2000=86.5271s/500 (includes previous commit, excludes next final commit). First preparation97.8229s/2000=24.4557s/500; second73.9452s; third48.3485s. Source corpus and NAS load differ from private benchmarks. Initial restart rescanned approximately170062 prior rows before first new window, observed about34min startup, not model reload/preparation and not claimed optimized. Cached acoustic models2loads/G2P1load across8groups; actual pinned Docker image/root identities and77production SHA checked; source/map/startup unchanged, required three locks held, no human item/batch approval. All4000 terminal. Automatic acceptance not manual phonetic truth; prior unknown root causes/5listen scope retained.
Completion observation at30s sampling: full terminal-ledger cadence approximately90.24s/500; report-archive cadence86.53s/500. Both meet the measured steady110s/500 acceptance. Previous six500 report archive intervals averaged189.19s; different source/NAS load, no universal2x guarantee. Current job continues independently, automation remainsPAUSED.


### 2026-10-03 timed resident window e4c192e: low acceptance explanation (read-only production analysis)

Existing complete 2000-source hybrid report: 344 published, 1656 rejected. Final timed reasons: 1259 alignment_acoustic_coverage, 250 no_mappable_pronunciation, 112 timestamp_mfa_disagreement, 15 unsupported_japanese_text, 10 malformed_output, 6 bgm_suspect, 3 phone_in_silence, 1 missing_output. Compared with preceding 358169 window (499 passed), mapping rejects increased 121 -> 250 and coverage rejects 1229 -> 1259; these are terminal-reason distribution changes, not proof of input quality or an optimization regression.

All 1259 retained local postprocess reports read: 1257 have suspect pauses; 904 have a suspect pause with >=0.2 s active energy; 73 contain only active-edge suspects with <=0.04 s active/longest energy. Unowned-region 111 and synthetic-silence-region 513 overlap these diagnostics and must not be added as terminal failures. Example u00af33e044b53c6d3cb41c9a: 3.12-3.21 s pause has 3.12-3.16 s energy, and 3.76-4.00 s pause has 3.76-3.78 s energy. Example u00e3ff775f481c30087e4b64: CTC/MFA lexical span starts 5.92 s; completed leading pause 0-5.89 s includes 1.86 s active energy. These locate the rejection; energy alone does not establish whether it is speech, breath, BGM, source/text mismatch, timestamp error, or excessive rejection. No root-cause repair claimed.

Evidence: .runtime/jobs/galgame-mfa-all/batch-evidence/e4c192e450754ac89d3b0c14baf89363/pass-rate-explanation-20261003.json, run/hybrid-report.json and run/pipeline-timed/<stem>/{asr,mfa,postprocess}.json. No new MFA experiment, source/NAS modification, code/model/threshold change, job restart or ledger credit. Healthy script continues. Historical manual listening remains limited to five samples; automatic checks are not manual phonetic truth.

**2026-10-08 同批次原生空白重叠复核（只读）：** 对上述完整 2,000 条中的全部 1,259 条终态 `alignment_acoustic_coverage`，逐一读取保存的 `run/pipeline-timed/<stem>/postprocess.json`，无缺文件。以每条 `suspect_pauses[].active_ranges` 与同条 `explicit_source_overlaps`（原生 MFA 空白）和 `synthetic_source_overlaps`（补齐空档）的正时长交集分类：**610 条仅与原生空白相交、513 条两种来源均相交、134 条仅与补齐空档相交、2 条无可分类活动交集**；合计 1,259。即 1,123/1,259 条有活动帧与原生 MFA 空白重叠，另有 647/1,259 条与补齐空档重叠，后两数因 513 条交叉而不可相加。778 条在原生空白内累计至少 0.2 秒活动，433 条在补齐空档内累计至少 0.2 秒活动。这是同一批筛除项的来源几何统计，不是 1,123 条均为台词、均由同一种解码原因触发，亦不能外推成全库「タクマ」式音素压缩频率。此前记录的 904 条“某个疑似停顿有至少 0.2 秒活动”使用的是整段停顿口径，不能与来源子区间的 778/433 直接相加。源 WAV/TXT/CTC、生产流程与发布结果未修改；自动 RMS 分类仍非人工语音学真值。


### 2026-10-03 ten listening samples: sp provenance traced before punctuation

User reports these ten listening examples contain obvious speech. Replay buttons include 0.3 s before/after the active-energy interval; hearing speech in that context is not a frame-exact phonetic judgment for the three 30 ms edge samples. All ten primary suspect spans traced through retained asr.json/mfa.json/postprocess.json: 4 native-MFA explicit-silence only, 5 native-silence plus uncovered geometry, 1 uncovered geometry only. These are primary playback-span classifications, not all intervals or corpus-wide proportions.

Sample 4 ASa_Project_Karigurashi_Ren_ai/vo1_1846__ASa_Project_Karigurashi_Ren_ai. Actual native grid run/batch-timed/0/aligned/b0189_000.TextGrid: phone tier blank0.28-2.09 s local with source crop offset0.48 -> original0.76-2.57 s. Final sp begins0.88 s after energy refinement; it was already native silence, not punctuation substitution. Sample 9 (vo2_0986): CTC/segment end4.32 and next start4.40; raw MFA silence absent there, partition completion fills4.32-4.40 as sp0. Sample1 (vo2_0821) has raw explicit0.77-1.16 and1.68-1.76, with unaligned crop gap1.16-1.68; full suspect pause0.77-1.76 has0.56 s active energy.

Source implementation: timed.py plan_timed_segments/expand_timed_segments_with_audio/align_timed_segments; hybrid_batch.py remaps occurrence aliases only, leaves interval geometry; output/textgrid.py complete_phone_partition fills uncovered time and build_word_intervals attaches source punctuation to pre-existing gaps; postprocess.py duration-buckets sp labels and audits them. Audio bytes are not muted. Speech existence and acoustic correctness of sp labels are distinct from having a complete alias sequence. Native decoder root cause and whole-corpus scope remain unknown; do not label all rejects bad source data or fix by removing gates/inventing phones. Evidence: listening-samples-e4c192e-20261003/sp-origin-analysis.json plus retained native/per-source reports. No new acoustic experiment, source/product write, code/threshold change or restart.


## 2026-10-03 — timed sp repair analysis and execution handoff

Human request: complete problem analysis and possible repair design, documented for execution in a new chat. Saved docs/superpowers/plans/2026-10-03-japgalgame-timed-sp-repair-handoff.md (SHA256 f2f20ee90a6d9ca9e19fbda7819d2a68dbdc68a9cdd87e044f84fe5431cc2d75) and 2026-10-03-japgalgame-timed-sp-repair-evidence.json (SHA256 1cd986465f2abd8bb168198e779d124ce764422fb37223346ee0ccc32a77aca7). This turn is analysis/documentation only: no new acoustic alignment or feature/graph generation, production code/parameters/gates/ledger/NAS source or product mutation, pause/restart, or automation resume.

Additional original evidence for listening sample4 ASa_Project_Karigurashi_Ren_ai/vo1_1846__ASa_Project_Karigurashi_Ren_ai, stem u5f63ebb03626529f122c5775, exact group0 b0189_000: prepared/local dictionary jmfa_000000 and native global jmfa_001865 both contain t a k ɯ m a; raw local phone span0.03–0.28 in crop0.48–2.57 restores0.51–0.76, followed by raw native silence0.76–2.57. Original corpus.db file/utterance580 (Kaldi1-580) has209 frames and non-NULL likelihood-63.38858309659091; logs Processing/Retried1-580 and group Done1446/errors0. Thus the existing unsuccessful-only10/160 wrapper does not address this demonstrated complete-output timing defect. Speaker1 named corpus and shared CMVN are observed, but their causal role is unproved; model SNR based on its own incorrect partition is not independent source-quality evidence. Specific decoder/search/feature/context trigger remains unknown.

Handoff separates native internal silence, uncovered crop gaps, short frame-edge diagnostics and independent no_mappable preparation failures. It proposes proof-first bounded failed-source recovery, all final gates and normal controls unchanged, private exact-input and fresh-resident validation, safe own-job integration and unique terminal retries only after real acceptance. Current77 production file hashes reverified unchanged; automation remains paused. User listening reports and +/-0.3s context do not establish frame-specific phone truth for30ms examples or corpus-wide correctness. No new repair is claimed applied.


### 2026-10-03 — timed SP context recovery, private validation and historical audit in progress

User authorized diagnosis, repair, real/regression tests, and checking previous rejected AND accepted data. Automation remains PAUSED. No source WAV/TXT/CTC modification, guessed text/readings, silence relabeling, or quality-threshold change is authorized by this repair.

**Confirmed mechanism and boundaries.** In the ten listening cases all fresh full frontend/mora/dictionary/alias requests match the retained originals (40 aliases). The fourth source `ASa_Project_Karigurashi_Ren_ai/vo1_1846__ASa_Project_Karigurashi_Ren_ai`, original text `タクマ。`, has all six dictionary phones `t a k ɯ m a`. Exact retained native features/graph/model reproduce the wrong local .03–.28 s word (source .51–.76 s), leaving speech-energy region in blank/native silence. Original crop .48–2.57 s PCM SHA cdd389f6bf7403bb2355953d8d4917a0270b6f07b5895ef4eb3351581ca815bf matches a fresh source cut. Original WAV SHA ce921c1e820172813ede1976ffcd81bb36dc7e2146162be364c0fa1e731320a6. Wider 10/160,40/160,160/640 beams leave that exact bad alignment unchanged; per-utterance recentering and unadapted final.mdl did not fix it. A speech-frame mask stretched a vowel to 1.4 s and was rejected as an invalid forced solution. Whole-wave context also did not solve this case. The presence of actual speech has user support, but exact spoken wording/reference correctness is pending user confirmation. This case remains rejected and UNRESOLVED, not fixed by the context candidate.

**Minimal candidate (private checkout only at this entry).** Short adjacent timed crops can lack useful acoustic context. Retain the original first pass and its successful outputs; retry only eligible timing/acoustic failures once using min_segment_duration=2.4 with the existing long-gap separation and original source/CTC/words/dictionary. Crucially retain original segments as `review_segments`, so the final original CTC constraints and .2 s review still apply. No forced phone filling or energy exception. Single-segment cases (including source4), noneligible mapping failures and long separated islands are not blindly retried. Candidate code in `staged-timed-sp-repair-20261003/checkout`: context_retry.py, pipeline.py, galgame_mfa_hybrid.py, galgame_mfa_all.py and two regression test files. Candidate SHAs in candidate-files.json, not production-applied yet.

**Evidence.** Ten exact native replay reproduces all original rejections. Enlarged acoustic-context real native retry plus ORIGINAL segment final review recovers listening samples 3,8,10; others remain rejected. `validation-500/receipt.json`: 500 sources,437 prepared/63 preparation failures; frontend/mora/dict/aliases exact; original native first-pass outputs reused with crop SHA validation; all 104 original accepted source/TG SHA unchanged and excluded from retry;231 eligible retries,26 recovered,370 still rejected. Retry native acoustics really executed through a private resident/root. 102.369 s is the local validation harness time, not production end-to-end ETA. No NAS or ledger credit. Separate full fresh native initial+retry500 validation is running, not yet a success claim.

**Regression/review.** New context tests initial stub:2 failed/2 passed, then11 related passed. First full765/2 failed/15 deselected had absent ffmpeg PATH in the harness, not relaxed expectations; original log retained. Correct environment767 passed. Independent review found context postprocess not synchronously archived by the outer batch committer and audit success classified before final source-race check. Added real commit/cleanup regression (red1 failed), retained context postprocess synchronously, moved final audit classification after all stat checks, distinguished snapshot supersession. Final private regression768 passed/15 real_models deselected17.03 s. Reviewer recheck found no further material blocker; deployment must load the new scanner module, not just update on-disk files.

**Historical scope and limitations.** `historical-baseline.sqlite3` frozen at1791018362.2673538 includes288062 sources:75472 passed,212590 filtered. `historical-audit/results.sqlite3` is resumable read-only verification of original source triples/signature/SHA, retained preflight/final report if available, CTC lexical coverage, actual published TG SHA/full structural-punctuation-five-tier/original WAV energy audit and lexical-text consistency. Original provenance missing => review_required, not invented historical certainty. Filtered identity check alone is NOT proof of correct rejection; actual affected real reprocessing remains needed. Automatic checks do not prove manual phone truth. Audit of this frozen scope is currently incomplete, later production rows outside it must be separately counted. No automatic passed=accurate claim for unfinished or uncertain rows. Current production continues on old code while audit and private validation run.

Receipts/raw/logs/native DB/models/graphs/features and failed diagnostic attempts retained under `/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/`. Initial diagnostic MFCC native-owner-lifetime harness error corrected by retaining archive/matrix objects; not a production root-cause claim. Historical root-cause unknowns, dither limits, and prior human listening limitations remain.


### 2026-10-03 — bounded context retry applied to ongoing production
Actual apply-receipt.json confirms installation at 1791022547.3824518; prior batch c7d3e3cc5c5a455baefbbafe93bccaa6 all2000 report rows archived and same SQLite committed. Scanner2013963/start611661801 held 23.107s, including installation/full actual production768 passed15 deselected22.21s. All healthy preparation/alignment children completed before mutation; all task child lists rechecked after holding parent. Resident2013695/2013696 unchanged, no reloading; original supervisor2013962/ledger continues. 80 actual code hashes verified without drift; startup SHA 7b0f3a3de32cc45d98526e553f063c388b4a60c60508b34d4ec294f7a89182fe unchanged. No source/old accepted TG changes, map/dither/final gates unchanged. Old loaded outer scanner synchronously archives full report embedding context postprocess JSON/SHA; separate context-postprocess copy in newly installed outer module activates only at its future restart. Therefore durable diagnosis does not depend on watcher timing or restarting healthy production. First new-production batch receipt still pending, not claimed complete here.
Historical audit temporarily yielded NAS IO during deployment and resumed in finally. Scope remains288062 frozen rows75472passed/212590filtered, currently incomplete. Complete final-report classification coversall212590filtered/missing0/report-ledger mismatch0:170143 acoustic coverage,21243 unmappable pronunciation,13996 timestamp disagreement,4426 malformed,1319 unsupported,755 bgm,376 phone_in_silence,133 missing,80 unexpected,59 empty,41 reading mismatch,17 final audit/hash,1 token span,1 punctuation source. See historical-final-reasons.json. These are final rejection reasons, not proof of incorrect source data or correct rejections. Main audio-in-SP case4 remains unresolved.


### First production pipeline complete; final publication/audit pending (1791023994.5200472)
Batch 5d56d7710f0c494eb7b51a1ce9cd7af4: complete2000 report,1210 accepted/790 rejected; failed-only context retry533 sources/1160 crops restores154. Preparation26.700s, nativeinitial+retry131.684s, timedreview196.938s, localcandidatepublication406.791s, reporttotal762.113s; this is not outer NAS end-to-end. Archive is durable, ledger currently{'filtered': 50, 'passed': 191}; do not credit full batch until observer first-production-receipt.json verifies all2000. Scanner had NAS wait_for_response with static read/write counters;45s audit-only IO yield did not itself resolve wait, then report archive/ledger progressed. Cause is not established as audit contention or deadlock. Old12403... traceback has mtime1790893908 (before this repair), not a new production failure. Historical26 actual candidate correction remains pending safe boundary and receipt. Frozen audit status56320/288062, completefalse, issues{}; unknown provenance is not a confirmed wrong grid. No source/oldpassed rewrites.


### Historical WAV/TG provenance supplement (1791024298.3441365)
Some historical batches have no retained batch-evidence directory/preflight triple SHA, but their original synchronous full reports retain per-source WAV and final TG SHA. Added read-only audit-report-provenance.py (match, mismatched WAV/TG, wrong source key and missing evidence assertions passed) to compare these ORIGINAL values against the already collected historical audit hashes, with no extra NAS traversal or source/output writes. Current39040 old passed rows all WAV/TG hashes match; issues{}. Original TXT/CTC SHA gaps remain unknown and main historical classifications are not rewritten into unsupported certainty. Incremental evidence: historical-audit/report-provenance.sqlite3 and report-provenance-status.json. Main frozen audit incomplete; a correct hash does not prove human phonetic boundaries.


### First new production and historical correction verified (1791024826.968086)
First-production-receipt.json confirms all2000 unique batch5d56d7710f0c494eb7b51a1ce9cd7af4 rows committed:1210passed790filtered,533 context retries/154 restored,532 embedded postprocess diagnostics; one extra context missing_output retained as failure (no invented success). Three extra NAS SHA spotchecks match; standard production gates cover allpublished, not a separate fullbatch human review. No historical-baseline passed source in this batch.
Historical-correction-receipt.json confirms context-repair-66b8fc70382048ac9f026e4ec8ff9262 exact26 oldfiltered restored, all26 sourceSHA/standardfinalaudit/NASreadback/ledger verified, previouspassed unchanged. Original failed diagnostics moved by standard committer and before-ledger/prepublication proof retained. Scanner held48.7835s for safe-boundary publication and resumed in finally; resident models not restarted. Counts now{'filtered': 222556, 'passed': 85506}. Frozen historical audit remains incomplete: 67072/288062, {'filtered/rejected_requires_acoustic_or_mapping_retest': 21504, 'passed/review_required': 11267, 'passed/automatic_pass': 34301}, issues{}. Original report provenance supplement checked45312 oldpassed WAV/TG hashes, issues{}. Source4 remains unresolved; no automatic-to-manual truth claim.


### 2026-10-03：原生 SQLite 导入短锁失败与有限等待恢复

## 后续生产停机及恢复

记录时间：2026-10-03T12:35:15.563834+00:00。生产在批次 57ce145ac63a4595bdc1fc87d7544d39 的第 3 组原生对齐完成后，SQLite 导入 word_intervals.csv 时遭遇 database is locked，导致完整批次未落账。原 work、模型、日志、数据库和故障状态已保留。锁的持有者未知，未将证据快照读者追认为原因。

最小修复仅在本作业串行 resident 的 align 调用内，给自己 temporary_directory 下 sqlite3 .import 增加 .timeout 5000；不重新执行部分导入、不吞异常，持续锁仍失败；其他数据库、普通 SQL 和 G2P 不受影响。这个设置是 SQLite 锁等待策略，不是整个导入/批次 5 秒总时限。

实际测试：短暂真实读锁红灯复现；修复后短锁导入正确、持续锁仍报错、跨目录数据库不改变、异常后原调用恢复。原失败组 1488 个音频在私有真实 MFA 下完成 1488 个 TG 导出，注入 0.3 秒读锁的真实 word 导入耗时约 0.352 秒并成功。这个实验不计生产通过数，不替代完整最终审核。

独立审查通过后安装仅 2 文件：src/japanmfa/mfa/native_resident.py 和 tests/unit/test_sqlite_import_wait.py。实际生产相关 7 passed，全回归 772 passed/15 deselected（27.58 秒）；81 项生产代码哈希记录，startup 原 SHA 不变。原生模型、dither、音素/映射、质量门禁未改。回执：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-sqlite-import-wait-20261003/apply-receipt.json`。

沿用原 progress.sqlite3 和原启动脚本恢复 after-ctc-complete 阶段；CTC 已结束，6421468 成功、1640 失败、remaining=0。故障时生产账本 86887 passed / 229175 filtered；恢复后的新进度以 live-status 为准。旧常驻进程已经随故障退出，本次恢复需重新启动常驻进程；正常后续批次仍复用常驻模型。自动发送消息仍暂停。

历史 288062 全核查完成，75472 原 WAV/TG SHA 全一致；19940 TXT/CTC 原 SHA 缺证保留。26 个冻结后状态差异与已验证修复集合完全一致。用户确认第 4 句确实只说タクマ，具体音素定位仍未修复，不以文本确认替代边界真值。


### 2026-10-04：CTC 重生成与两个变化候选完整验证

# CTC 重生成验证：语音落入 SP 样本

记录时间：2026-10-03T16:08:52.244909+00:00。

结论：已经用原 WAV/TXT 和现有本地 Qwen3 ForcedAligner 重新生成 10 条试听样本的时间戳，9 条新旧 TextGrid 字节完全相同，1 条有局部变化。第 4 句批量结果仍为 0.48–2.40 秒；单条结果为 0.48–2.48 秒。第 7 条新增两个零时长词，原 3 个变为 5 个，不能将重算直接当正确修复。

原 source4 CTC 覆盖了主要冲突有声区 0.98–2.22 秒，裁剪为 0.48–2.57 秒；原生 MFA 却在该裁剪内部给出长静音。此前精确原输入重放、搜索范围/特征诊断和整句上下文均未消除此问题。用户已确认文本为タクマ。上述证据支持该样本主要表现为 MFA 内部定位失败，尚未证明所有 CTC 边界正确，也不排除其他样本的系统性词时间误差。

## 实际执行

使用生产同一加载函数、同一本地模型、bfloat16 CUDA，原三联 SHA 在前后全部一致；模型权重与配置 SHA 在 receipt.json 留存。模型加载 9.017 秒，10 条批量重算 1.325 秒，第 4 条单独重算 0.143 秒。这是 10 条诊断计时，不推算全量吞吐。

10 份候选全部通过现有 CTC 文本完整性、时间轴、词序和零时长点读取验证；这只确认格式与身份，不是人工词边界真值。

再将有变化的两个候选送入隔离真实 MFA 管线：第 4 条使用单独重算的 2.48 秒结束，第 7 条使用新批量结果。两条均完整准备成功；初轮真实 MFA、适用的上下文重试和最终原 WAV 审核全部执行。结果 0 条通过、2 条 alignment_acoustic_coverage 拒绝；第 7 条上下文重试仍拒绝。耗时 32.033 秒。重新生成的特征及两条批上下文不能用来声称精确原音素边界等价，但已经证明这些重算候选没有在本次完整测试中解决失败。

未替换生产 CTC、未改原 WAV/TXT、未写 NAS TG、未改账本、未给候选计通过信用。生产常驻作业保持运行，自动消息仍暂停。由于新候选未能改善并通过完整审核，当前没有依据全量覆盖重生成 CTC。

## 可复查证据

- 重算前 CTC/TXT：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/before/。
- 新 10 条时间戳和原始响应：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/generated/。
- 第 4 条独立候选：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/source4-single.TextGrid。
- 原输入身份、模型 SHA、新旧逐词比较：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/receipt.json。
- 完整私有管线报告：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/changed-ctc-full-validation-final/run/hybrid-report.json。
- 完整测试回执：/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-ctc-verification-20261004/changed-ctc-full-validation-final/receipt.json。

初始测试环境失败（ASR 环境无 praatio；首次私有 socket 路径过长；诊断脚本准备并发值 2 不受支持）原日志留存。只修正诊断脚本环境和调用配置，未改生产；最终验证回执与这些初始失败分开保存。

后续修复应验证 CTC 裁剪/约束与原生 MFA 定位的具体关系；不能用词时间框直接填充音素或把自动声能当人工音素真值。当前第 4 句仍未修复。



### 2026-10-05 — ENOSPC interruption and server-local evidence relocation (storage only)

- The system filesystem reached 100% and the prior supervisor/scanner/resident services exited. `live-status.json` was stale because the exception snapshot also failed. Original interrupted batch `1d3c2f33ae42457793084104fad7f2ad` has zero committed ledger rows. Its 76,730,368-byte truncated report is retained unchanged (SHA256 `1d53210c1beadbcb60d102e56413f055cbb9d4a6d9d0b52ad8f065ac3441738d`); no partial output is credited as a pass.
- At the user's latest instruction, evidence was relocated to server-local `/mnt/nvme4/JapanMFA/galgame-mfa-all-evidence`, not NAS. All 57 archive/evidence directories retain original-path symlinks. Each of 719 migration units was copied, fully MD5/tree/symlink checked by rsync dry run, then only its verified original duplicate was removed. These units contain 15,712,815 regular files / 406,862,605,365 logical bytes. Five stopped work directories were separately copied and checked into `migration-20261005/interrupted-work-disk-full`. The prior tiny NAS attempt and its ENOSPC linking failure are preserved on NVMe; only that exact newly created NAS destination was removed after its complete content verification.
- Final checks: same ledger `192424 passed / 625638 filtered`, `quick_check=ok`; original startup SHA unchanged; four actual write/readback probes through the original `batch-evidence`, `filtered`, `pipeline-audit`, and `reports` paths landed on the NVMe device. Available system-disk space at verification was 470,255,255,552 bytes. Active ledger/cache/new work/model roots remain on their existing local paths. Future archive writes follow the NVMe links. Source WAV/TXT/CTC and published NAS TextGrids were untouched.
- Of the 81 recorded files, 80 remain byte-identical. The sole intended change is one NVMe mount preflight line in `resume-timed-resident.sh`, with original SHA/backup and exact-line verification in `launcher-storage-guard-receipt.json`. It refuses startup if the local evidence disk is unmounted. No alignment code, model, dither, mapping, search strategy, or final gate changed. The initial all-81-identical verification assertion correctly detected this intentional launcher difference; the final verification explicitly checks it against the retained original, rather than accepting arbitrary drift.
- Existing `japgalgame_mfa_all` flow was restored with the same SQLite: supervisor 2967011, scanner 2967012, evidence watcher 2967076; startup receipt is `migration-20261005/recovery-start.json`. Recovery of uncommitted input must still run the complete pipeline. CTC remains `complete_with_failures`: 6,421,468 success / 1,640 failed / 0 remaining, not all-success. Storage verification is not acoustic validation; all existing alignment uncertainties and automatic-review limits remain.
- Full storage verification: `/mnt/nvme4/JapanMFA/galgame-mfa-all-evidence/migration-20261005/migration-verification.json`. Routine monitoring/automated notifications remain unchanged; no new acoustic experiment or NAS corpus audit was started.

### 2026-10-06: filtered-source crop tails and native misplacement, bounded repair

- Read-only seven completed 2,000-source batches: 8,831/14,000 final reasons were acoustic coverage, 1,320 phone/mora mapping, 654 timestamp disagreement; 2,669 passed. These are unique final-result categories, not proof that all acoustic regions are human speech. BGM, pronunciation/frontend failures and model/transport failures remain distinct; an earlier veto may be hidden by the final pause reason, so inspect the full postprocess diagnostic.
- Proven boundary mechanism: a CTC-gap midpoint caps both native crop and weak acoustic support. A connected fading vowel can continue beyond that artificial midpoint; native cannot observe the missing tail, the existing synthetic-tail 120ms refinement cannot repair longer exclusions, and stale support can reject an acoustically supported boundary. CRYSTALiA_Kizuna_Kirameku_Koi_Iroha_Tsubaki_Renka/VO09_00220__CRYSTALiA_Kizuna_Kirameku_Koi_Iroha_Tsubaki_Renka: first CTC end 1.12, native crop end 1.36, prior support 1.24; original WAV has connected decay to 1.44 then quiet before next crop 1.60. Another native crop ends 7.84 while its connected tail ends 8.04. Final proposal retries crops to 1.47/8.07, with support limited to 1.44/8.04, never silence padding. Original CTC anchors/token geometry and the originally unsupported review are retained.
- Minimal proposal: only failed acoustic-coverage sources whose real native last-token vowel touches the original crop edge; require continuous decay, log fit>=0.8, end/start<=0.1, adjacent rise<=1.5, <=200ms exposed tail and three quiet 10ms frames before the next actual crop. Support for timestamp review additionally requires continuous original-anchor-to-quiet activity and <=350ms total displacement, matching the existing weak-tail evidence window. This adds an evidence-constrained support condition; it is not merely crop enlargement. No 0.2s drift constant, source CTC, pronunciation, dither, model, silence/energy gate or success result is changed. Do not assign extra phones from RMS. Re-run native alignment for changed crops; unchanged crops retain original native TG after source/occurrence-alias/crop-SHA identity checks. New crop retry and the existing 2.4s merge retry are mutually exclusive. Any original BGM, low-energy-phone, unowned speech or material structure veto excludes the new path. Preserve first postprocess path/SHA and old support limits in the retry receipt.
- Old project `/mnt/local_E/MFA_Pause/repo/scripts` was compared read-only. Quiet/decay checks inform the repair, but Chinese full-word shifts and lexical snap rules were not ported blindly. Current native silence ownership and final audits remain authoritative.
- Final isolated validation: `exclusive-broader-private/receipt.json`: 111 immutable source triples, 73 edge candidates / 32 accepted controls / 6 negatives. All 32 accepted source sets/TG hashes remain exact; all six negatives rejected. Only uc71cef13bc276b56be595a50 is an attributable new-rule full recovery. u7c54c30826578bfb021e926e recovered through existing merge without new-tail evidence and is not credited. 34 local final exports pass `tools/audit_textgrid_pauses.py`, including structure, adjacent pauses, punctuation and original WAV coverage. `exclusive-full-regression.log`: 793 passed/15 real-model tests deselected; `exclusive-veto-red.log` five expected failures and `exclusive-veto-green.log` 25 passed. Actual private native runs separately cover acoustic execution; unit success is not acoustic or manual phonetic truth. No local validation was written to production NAS or ledger.
- Negative/local-only results: VO09_00195 tail 1.44->1.62 corrected locally, but another original internal SP at 4.52–4.63 still fails; u251270989ef13318f0bc92e0 tail 2.72->2.86 corrected locally but its 2.48 anchor is >350ms away, so full timestamp review still refuses. Neither is a pass. Original and earlier failed variants are retained.
- Rejected diagnostics: continuous-gap bridge and per-source normalization grouping did not recover tested failures; silence-prior change did not move the exact native early-collapse example. ASa_Project_Karigurashi_Ren_ai/vo1_1846__ASa_Project_Karigurashi_Ren_ai (タクマ) still has all six dictionary phones, native assigns them near .51–.76 and labels later signal silence. This begins in native decoding, not punctuation or missing phones. Specific decoder/model trigger remains unproved. An inward crop .98–2.25 would discard substantial original signal both before .98 and after 2.25; RMS cannot prove those islands irrelevant, so this forced-fit trial is rejected and no blanket CTC regeneration is justified.
- All evidence and current proposal hashes: `/mnt/nvme4/JapanMFA/galgame-mfa-all-evidence/staged-boundary-repair-20261006/plan.json`. Proposal is staged and verified, **not production-applied yet**; safe application receipt must prove original hashes, complete prior batch/ledger, no loaded child, original startup unchanged, production tests and scanner finally resumed. Automated notifications remain paused. Most acoustic rejections remain unresolved; do not extrapolate this one recovered source to total yield or retrospectively label unknown failures fixed.

- Production follow-through, 2026-10-06: proposal now **verified_applied**. Natural own batch `120238dcf95943e8a27f448f19320b1b` fully archived/committed with 2,000 terminal items; no loaded child during installation. Only scanner 2967012 stopped for 28.582335712388158 seconds and finally resumed. Actual production unit 25 passed and full 793 passed/15 deselected; 81 current code hashes verified, only the three planned files changed; original startup SHA unchanged. Residents/supervisor/watcher retained, no CTC signals or new automated messages. `apply-receipt.json` records all hashes and tests.
- One fully validated source uc71 promoted using the standard `_commit_batch` publication/audit/ledger path, after identical implementation deployment and confirming it was filtered and absent from healthy production work. The retained actual native decode scope was the 111-source private full pipeline, not a fabricated one-source run; report publication provenance names that complete source report/SHA. No additional MFA process/feature generation, no control/chance-recovery credit. Old filtered diagnostic moved through the standard resolved-evidence path; prior reports/hashes remain. Production batch `a4605759a42340b6986af3e20f4f0cee`: 1 passed/0 filtered. NAS TG SHA 2d93c23aa5bca0a0d8d06eaa514eaa01d56e1fdc3b46911a67437eb9f4932449 read back exactly, original WAV/TXT/CTC unchanged, original-WAV final five-tier/adjacent-pause/punctuation/acoustic audit passed. `production-recovery-receipt.json` and `post-application-health.json` retain the full receipt and active restored processes. All other existing accepted NAS TG remain untouched; 32-control preservation is a sample, not a global phonetic audit. Most filtered acoustic sources and the native early-collapse case are still unresolved, and this limited repair must not be described as fixing all alignment bias.

### JA-032/JA-021 追加：2026-10-08 全量 G2P 音素与莫拉规则缺项

本轮针对当前仍在运行的 GalgameMFA 中 `no_mappable_pronunciation` 筛除项更新同一根因。真实生产 G2P 缓存 132,629 条读音；原规则 223 条。缺项分为长音 `ー` 与相邻音素合并（如 `ソー → s oː`）、外来语及拗音辅音变体（`ティ → tʲ i`、`ファ → ɸ a`）、有实际长辅音的促音组合（`ッシ → ɕː i`、`ッド → dː o`）。准备阶段被拒的样本没有 MFA 音素时间边界，时间坐标不适用；示例原始三联为 `/mnt/Raw/JapGalgame/0verflow_Shiny_Days/{wav,txt,ctc}/03-i5-e08-0080__0verflow_Shiny_Days`、`/mnt/Raw/JapGalgame/AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/{wav,txt,ctc}/air_2003__AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu`。

原自动推导给出 116 条 support≥10 候选，但其中 `ウ → oː`、`ロ → ɾ oː`、`フ → ɸ a`、单独 `ッ → pː` 等会接受错元音、无长音记号或与后续辅音不一致的发音；官方词典子串命中不能证明音素归属。只装入 87 条有完整音素且归属明确的精确规则：49 条 `ー` 长音、13 条 `ッ+后续莫拉`、25 条单莫拉变体。双莫拉规则均显式写出每个原音素的 `mora_spans`；一个长元音或长辅音可以归属两个莫拉，但只保留**一个原音素区间**。原 G2P 若漏掉促音，如 `オッパイ → o p a i`、`セッカク → s e k a k ɯ`，继续拒绝，不借用后一个莫拉的辅音制造促音。

证据保存在 `.runtime/jobs/galgame-mfa-all/mapping-diagnostics-full-20261008/`：`report.json`、`curated-selection.json`、`curated-map.yaml`、`curated-validation.json`、`curated-recheck-2000.json`、`phone-map.before-live-apply.yaml`、`apply-receipt.json`。生产相同匹配器对 135,348 个真实莫拉/音素键逐条对照：原 105,928 可映射，新增 7,818 个键可映射，旧映射回归 0、新歧义 0；87 条规则直接验证每个输入音素恰对应一个输出归属。固定种子抽取的 2,000 个历史筛除项，750 个通过新的**准备阶段映射**，1,250 个仍拒绝；后者包括促音类 828、其它未映射 371、缓存未命中 29、长音残余 22。逐条回放因当前源码指纹与运行缓存身份不再一致，使用仍在追加的最新生产 G2P 身份 `9de5e4bed180…`，未伪称精确重建旧身份。这个抽样不是声学通过率或全库人工音素真值。

切换时仅暂停扫描进程 2967012，待原子批次子进程 945455 完整退出且无活动后代后替换规则文件，再于 `finally` 恢复；旧规则 SHA-256 `822b60eb0707677ffa8046264109bc0a3074a2018f8bb80270c48f6e48bc0362`，新规则 `2fff45cf99f405bae4af99881584069c9e2b0c0065574943cdba742ee427abfe`，原件留存。切换时台账 `563411 passed / 1762651 filtered` 不变；之后扫描状态为 running，下一原生子进程已启动。没有由本轮诊断直接发布 TextGrid/WAV 或把历史筛除项记作通过。定向测试 67 passed；完整回归 813 passed、4 skipped、1 failed，失败为独立 `test_sqlite_import_wait.py` 对 SQLite `.import` 新建表 `id` 列期待整数而实际为文本的环境行为，单测独立重现，与 phone map 无关。历史筛除仍需按原始 WAV/TXT/CTC 真实重跑并经发布前停顿、标点、声能和配对审计；缺音及其它不可信发音继续保持拒绝。

**切换时发现并修复的运行态复发（同一规则版本根因）：** 上述“无活动子进程”条件不足以保证没有**已完成但排队等待对齐的预处理包**。切换后旧规则预处理的批次 `89b8260a69284074850ad38413839a5a` 用新规则计算 `_preparation_identity`，2000 条中 1730 条被正确报 `prepared_source_changed`，其余 211 `no_mappable_pronunciation`、49 `malformed_output`、10 `unsupported_japanese_text`；该批 0 发布，不是音频质量结论。原 2000 条报告 SHA-256 `440a9216b1b4b3e38cfe85d11f9f92f4b11cbd0f5c3b2bf1eac8b53db92d2249` 与逐条失败诊断保留。全 2000 条原源三联和账本签名复核一致、正式目标文件均不存在；仅将这批改为 `retry_required`，并保存改前逐行状态/原因、可重放 manifest 与哈希于 `mapping-diagnostics-full-20261008/mixed-window-*`。没有把失败改写为通过。之后新规则完成的 `dbc1f9b7e52e4c77a3070561e58af44f`、`4ea8a85552aa403e85319701a8d9feb6` 两个 2000 条批次分别 729/1271、905/1095（通过/筛除），无 `prepared_source_changed`，说明新预处理与新对齐规则的交接正常。该次切换暴露的必要安全条件是**所有已预处理排队窗口也须排空**，不能仅看进程树。

**实际恢复终态：** 保存本批原 2000 条失败 JSON 与逐条 SHA、核对全部原始三联/签名及正式目标不存在后，暂停扫描器并等其当前子进程完成，用同一常驻模型、同一原始输入和现行规则走完整生产 `_run_batch` / `_commit_batch`。新批次 `68defd1088aa4124bc03beed2a54a682` 逐条完整报告 SHA-256 `deb5b972b9725b0e8c8dc283a53b4304b70ebfabb6ebe090153abcff386356a6`：**752 发布、1248 筛除、0 prepared_source_changed**。保留筛除原因：933 声能覆盖、146 不可映射、108 时间戳不合、49 格式异常、10 不支持文本、1 缺 MFA 输出、1 BGM 疑点；这些都不能改记为通过。原误筛除 2000 条现全部由新批次终态替代，原报告/失败副本仍在证据目录。正式 752 份 TextGrid 台账 SHA 与 NAS 读回逐项相同、原 WAV 配对 752/752；用 `tools/audit_textgrid_pauses.py` 独立审计 **752 files / 0 failed**，检查结构、相邻停顿、跨轨标点与声能覆盖，报告 SHA-256 `6a9806a67139cad636556e1d852aed65931ab51a5e95e5b12f016de724b134f9`。扫描器在 `finally` 恢复并继续运行。上述自动门禁不能证明人工音素边界真值；其它历史映射筛除项仍需另行精确重跑。

**2026-10-08 历史映射筛除项的独立真实重测：** 从固定种子 2,000 条回放中取最先列出的 30 条原 `no_mappable_pronunciation` 样本，开跑前 30/30 仍为生产 `filtered`。原始 WAV/TXT/CTC 和旧失败 JSON 的逐条 SHA-256、私有 30 条 manifest 与完整结果在 `.runtime/jobs/galgame-mfa-all/mapping-diagnostics-full-20261008/real-recheck-30/`。隔离状态与输出目录调用实际 `tools/galgame_mfa_all.py`、现行音素规则、常驻原生 MFA、上下文重试及标准最终门禁，**30/30 不再因音素/莫拉映射失败**；最终 **4 条私有通过、26 条仍筛除**（24 `alignment_acoustic_coverage`、2 `timestamp_mfa_disagreement`）。四条实际通过的源键为 `0verflow_Shiny_Days/03-i5-e08-0080__0verflow_Shiny_Days`、`AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu/yum_1167__AKABEiSOFT3_Dekinai_Watashi_ga_Kurikaesu`、`AKABEiSOFT3_Maho_x_Roba_Witches_Spiritual_Home/mik_0371__AKABEiSOFT3_Maho_x_Roba_Witches_Spiritual_Home`、`ALcot_Yomegami_My_Sweet_Goddess/6010134__ALcot_Yomegami_My_Sweet_Goddess`；同名原三联分别在 `/mnt/Raw/JapGalgame/<game>/{wav,txt,ctc}/`，这些准备阶段旧失败没有 MFA 时间坐标。报告 SHA-256 `951df8687c20b6f8619bd0846ca3e714188eb8b09059bcea4ff687b1b3f45f63`，逐条结果 SHA-256 `61b1f52dc64f1737560e8e6f791cddc8900d86caf1ce7ad4903be659aa6849cf`。4 份私有 TextGrid 与原 WAV 完整配对，`tools/audit_textgrid_pauses.py` **4 files / 0 failed**。首次独立审计的 4 个“无法读取”是诊断目录把相对 TextGrid 目标写成错误符号链接，原失败报告留存为 `audit-initial-broken-symlink.json`；修正为同一文件的绝对链接后重审为 4/0，没有把缺失文件算成通过。私有输出标记 `NOT_FOR_PUBLICATION`，NAS 成品和生产台账对这 30 条仍保持原筛除状态；4/30 是这组非随机首列样本的最终通过数，不外推到全部历史筛除项，也不是人工音素边界真值。

**2026-10-08 更多场景的独立真实重测：** 从当前生产仍标记 `no_mappable_pronunciation` 的 3,500 条历史项，以固定种子 20261009、优先覆盖不同游戏且排除上述 30 条，选取额外 120 条：含长音 `ー` 的旧失败读音 30、无长音/促音的变体读音 30、含促音 `ッ` 的旧失败读音 30、缺促音音素对照 15、其它缺音对照 15。前 3 类按旧失败读音分组，**不声称每条都由该类的某个单独规则修复**。旧/新规则对当前 G2P 缓存的逐项回放预测前 90 条可映射、后 30 条应拒绝；随后用原始 `/mnt/Raw/JapGalgame/<game>/{wav,txt,ctc}/<stem>`、现行规则和同一常驻原生 MFA 运行完整私有管线。实际准备阶段 **90/90 可映射、30/30 对照仍为 `no_mappable_pronunciation`**；前 90 条最终分别为：长音组 9 通过/19 声能覆盖失败/1 时间戳失败/1 MFA 缺输出，变体组 9/20/1/0，促音组 9/19/2/0。合计 **27 私有通过、93 仍筛除**，其中 58 声能覆盖、4 时间戳、1 缺输出、30 映射拒绝；缺输出 `Azarashi_Soft_Amaemi_longing_for_you/fem_ski_12565__Azarashi_Soft_Amaemi_longing_for_you` 记作失败，不能归功于映射或算通过。例子：长音组 `AUGUST_Aiyoku_no_Eustia/aiy310209390__AUGUST_Aiyoku_no_Eustia`（旧读音 `ジーク`）、变体组 `Frontwing_Hatsuru_Koto_Naki_Mirai_Yori/myl_air_001_022__Frontwing_Hatsuru_Koto_Naki_Mirai_Yori`（`ファル`）、促音组 `Azarashi_Soft_Amakano_2_Perfect_Edition/CC_03_rei_01_001__Azarashi_Soft_Amakano_2_Perfect_Edition`（`ハムエッグ`）均私有通过；缺音对照 `CIRCUS_D_C_5_Da_Capo_5_Plus_Happiness/dc5_mzh19601112d_mna019__CIRCUS_D_C_5_Da_Capo_5_Plus_Happiness`（`マッタク`）仍拒绝。旧失败发生在准备阶段，无 MFA 时间坐标可记录。证据目录 `mapping-diagnostics-full-20261008/real-recheck-120/` 保留 120 条 manifest、每条原三联及旧失败 JSON SHA、完整原生批次报告、逐条私有结果和审计；120/120 原输入哈希不变，批次报告 SHA-256 `606be28f4c4ad0149d983b1636e1da1665c2feba71739342f78b2c5cadd8b93b`，逐条结果 SHA-256 `676b5fe59baad5487ec5be52546f09f09818b2ee9b7bebbbe8790fd097aa4550`。27 份私有 TextGrid 与原 WAV 逐项配对且与私有台账 SHA 相符，`tools/audit_textgrid_pauses.py` **27 files / 0 failed**，审计 SHA-256 `2c6d50d0ea645dbd170b5b55cfd46bacbd6b8b95afbf5101b4dd6950c62c60f7`。120 条生产台账仍为原 `filtered/no_mappable_pronunciation`，本测试没有正式发布；自动门禁及音素不拆分的单测不能替代人工语音学真值，也不能将 27/90 外推为全库通过率。

### JA-032/JA-021 追加：2026-10-08 扩大 500 条、失败重试及跨 mora 误分类纠正

- 额外固定种子 20261010 选取 500 条历史 `no_mappable_pronunciation`，来自 198 部游戏，与先前 30+120 条不重复。按旧失败读音粗分长音/变体/促音各 120、仍失败的两组各 70；此分组只用于抽样，不能证明缺音根因。原始三联路径 `/mnt/Raw/JapGalgame/<game>/{wav,txt,ctc}/<stem>`、旧失败 JSON 哈希、manifest、逐条结果和五批报告哈希保存在 `.runtime/jobs/galgame-mfa-all/mapping-diagnostics-full-20261008/real-recheck-500/`。首轮 360/360 预期可映射项通过准备，140/140 对照仍不可映射；最终 98 私有通过、402 筛除（240 声能覆盖、20 时间戳、2 BGM 疑点、140 映射）。长音组 28 通过、变体组 37、促音组 33。500/500 原三联哈希未变。98 份 TextGrid/原 WAV 完整配对并核对私有账本哈希，独立停顿、标点、声能审计 98 files / 0 failed，审计 SHA-256 `6280332356b25c889b2e80a1d38477631827e9f88a1ee45dd6c02fbb21aacc5c`；逐条结果 SHA-256 `b330e21532a38261828b5c36be752bde9497f261cf302d312bf074bdf89810db`。
- 用户要求重试后，对其中已过映射而终态失败的 262 条另起完整私有 MFA，保留首轮诊断哈希于 `retry-262/`。重试 2 通过、260 失败（237 声能覆盖、21 时间戳、2 BGM），262/262 原三联未变。两条新增私有通过为 `GIGA_Ai_Kiss_2/03030574__GIGA_Ai_Kiss_2`、`AUGUST_Sen_no_Hatou_Tsukisome_no_Kouki_Hana_Akari/sfd220200800__AUGUST_Sen_no_Hatou_Tsukisome_no_Kouki_Hana_Akari`，首轮均为声能覆盖失败；仅重复解码没有修改规则，不能将这两条恢复归功于新增规则。另有 2 条时间戳失败转为声能失败、3 条声能失败转为时间戳失败；重复运行并不保证完全相同终态。两份配对独立审计 2 files / 0 failed，审计 SHA-256 `b7c31e5063d2910cff54126e7f8ee6bac79835de51b338441b1d963d46ccdc9f`，结果 SHA-256 `f79afd525c1d1df214a6c58e40fd300482c54b54fa831056a2afc4f370739647`。

**纠正此前“缺音对照”的过宽表述：** `no_mappable_pronunciation` 仅说明当前规则无法覆盖整句某个锁定读音，不等同于 G2P 确实漏音，更不能说明 WAV 没有发出该音。旧失败读音可能在新规则下已经可映射，而同句另一个读音仍失败；必须重新分析全部 token，不能只看旧的第一个失败读音。对本轮 140 条重新运行真实 frontend、使用本轮实际 G2P 缓存逐 token 检查，发现以下明确规则缺项：

| 根因 | 完整音素与 mora 归属例子 | 新规则使整句可映射 | 最终私有通过 |
|---|---|---:|---:|
| 假名 `ウ` 表示长音的组合未列全 | `リョ＋ウ → ɾʲ oː`，`oː` 同时归属两个 mora；`シュ＋ウ → ɕ ɨː` 同理 | 22 | 9 |
| 促音和长音在中间 mora 重叠，现有局部规则不能直接串接 | `ッ＋キ＋ー → cː iː`，`cː` 归属 `ッ＋キ`，`iː` 归属 `キ＋ー`；需要三 mora 整体规则 | 8 | 1 |
| 鼻音与后续辅音合并 | `ン＋モ → mː o`，`mː` 归属 `ン＋モ`；含长音的 `ン＋マ＋ー → mː aː` 也保留两个原音素 | 5 | 0 |

候选扩展为 12 条：`リョウ/シュウ` 两条、`ッキー/ッホー/ッセー/ッピー/ッサー` 五条、`ンミ/ンモ/ンマ/ンネ/ンマー` 五条。每个输入音素只生成一个归属条目，不拆成两个音素区间；12 个正例显式验证 `mora_spans`，5 个负例验证漏促音、错辅音、缺长音及多余长音仍拒绝。例如 `マッタク → m a t a k ɯ` 的 G2P 没表达促音长度，`スッゴイ → s ɨ pː ɡ o i` 长辅音部位不符，不能因一个音素可覆盖多个 mora 就强制匹配。这是 G2P/规则层证据，不是人工听辨真值。

候选表 `span-candidate.yaml` SHA-256 `8d0a683b4508ce73268126ab75d153bea543040fdb383317dd41083d053e458d`；全缓存 136,995 个真实 mora/phone 键：新增可映射 839、原映射回归 0、新歧义 0，快速匹配器与生产匹配器抽样一致，报告 `span-candidate-validation.json`。先行只加两个 `ウ` 长音规则的验证报告也保留，不能把它的 482 个新增键与 12 条候选的 839 相加。旧源代码与工具复制到 `span-recheck-140/snapshot/`，69 份文件逐项校验，只有候选规则表不同；原生产表仍为 `2fff45cf99f405bae4af99881584069c9e2b0c0065574943cdba742ee427abfe`。该隔离快照真实重跑全部 140 条：35 通过准备、105 仍映射失败；35 条中 10 最终私有通过、25 声能覆盖失败。原 140 份 WAV/TXT/CTC 哈希均未变，整句映射预测与实际准备结果逐条一致。完整证据为 `span-recheck-140/reading-analysis.json`、`results.json`、`snapshot-hashes.json` 及原生报告。结果 SHA-256 `979722ed5d15f241b3974bdbb99d1e8626b392ae5fd53a422a9c8e45b2bf7a21`。

原映射失败均在准备阶段，没有 MFA 时间坐标。新声能失败的例子为 `Debo_no_Su_Seisakusho_Kurenai_Kagura/is00479__Debo_no_Su_Seisakusho_Kurenai_Kagura`：`timed-postprocess.json` 自动报告 1.28–1.45 秒合成停顿含活动声能（阈值 0.038214、最大 RMS 0.112179），该源最终仍失败；声能活动不等于人工确认的人声。新增 10 份私有成品与原 WAV 独立审计 10 files / 0 failed，审计 SHA-256 `8752191157e577629953a93491aec74e229f6e4b690803a44208a2facf367f0d`。一次审计在配对准备进程完成前误启动，退出码 1、0 files，其报告保留为 `audit-before-pairs-ready.json`，不算验证成功；等待全部 10 对存在且哈希一致后重审得到 10/0。全部产物均标记 NOT_FOR_PUBLICATION，未修改这 500 条生产账本或 NAS 成品。12 条规则目前为已通过隔离验证的候选，尚未切换运行中的生产规则；剩余 105 条不可映射和后续声学问题仍未解决，不能统称为缺音或已修复。

### JA-032/JA-021 追加：2026-10-08 指定 21 种罕见音素的规则补全与 417 条真实音频对照

用户给出的前 12 种音素在现行 310 条规则中确实没有入口；但“成品没有该音素”不能推出“凡有该音素候选的整句都被过滤”。规则表接受 G2P 音素并确定 mora 归属，不生成音素；其它合法 G2P 候选仍可能使整句通过。最新按读音去重缓存共 109,301 条，其中 1,984 条至少一个候选包含目标音素。`bʲː ɴː wː çː ɸʲː` 在此缓存未观测到，只能以固定模型词典的完整词例验证；`ɾː ɾʲː` 有缓存记录，本次源子集未定位对应音频。不能把这七种写成真实音频已通过。

本轮新增 33 条精确规则，连同此前已隔离验证的 12 条跨 mora 规则，共 310→355 条。覆盖促音长辅音、促音和长元音重叠、鼻音合并、外来语 `ヴェ/ヴォ/ヴァー/ヴィー` 等；21 种目标音素都有完整词例正测。33 条每条均有完整 G2P 或固定模型词典读音的成功匹配证明，保留于 `.runtime/jobs/galgame-mfa-all/phone-inventory-20261008/rule-provenance.json`。例如 `ウェッブ → w e bː ɯ`、`ウッディ → ɯ dʲː i`、`カペッリーニ → k a p e ɾʲː iː ɲ i`、`スタッフ → s ɨ t a ɸː ɯ`。每个输入音素仅产生一个归属条目和原时间区间；`ッ＋フィ＋ー → ɸʲː iː` 的 spans 为 `[[0,2],[1,3]]`，不拆音素。`グッスリ → ɡ ɯ dʲː s ɨ ɾʲ i`、`ギュギュ → ɟ ɨ ɟː ɨ`、`プクッリ → p ɯ k ɯ e ɾʲː i` 等错辅音、无促音标记或额外元音仍拒绝。原准备阶段失败无 MFA 时间坐标，不等于人工确认 WAV 缺音。

从 5,498 个历史原始三联定位 124 部游戏的 417 条目标候选源，涉及 14 种目标音素。原路径仍为 `/mnt/Raw/JapGalgame/<game>/{wav,txt,ctc}/<stem>`，417 条原生产状态为 24 passed、362 `no_mappable_pronunciation`、27 声能覆盖失败、3 时间戳失败、1 格式失败。新旧两轮使用同一模型、完整原生 MFA 及标准门禁；旧轮读 NAS，候选轮为缓解 NAS 拥塞读取逐文件 SHA 校验一致的本地三联副本。`input-evidence.json`、`prior-diagnostics/`、两阶段报告与私有账本保留全部旧失败和输入/输出 SHA。两轮均完整处理 417 条、0 跳过、0 缺失终态；本轮私有成品未发布，417 条原生产记录未改。

| 项目 | 旧规则 | 新规则 |
|---|---:|---:|
| 准备成功 | 310 | 331 |
| 映射失败 | 106 | 85 |
| 格式失败 | 1 | 1 |
| 最终通过 | 99 | 107 |
| 声能覆盖失败 | 192 | 206 |
| 时间戳失败 | 19 | 18 |

新增准备成功 21 条、准备回归 0；其中最终 9 通过、12 声能覆盖失败。另有 1 条原准备成功源从失败变通过、2 条从通过变声能失败，三条新旧词典逐项相同；这些解码终态差异不归功于映射规则，也没有改写原正式成品。97 条两轮均通过，其中 39 份 TextGrid 字节相同。`comparison.json` 和 `unattributed-acoustic-changes.json` 保留完整源键与差异。两条转失败的原源 `GIGA_Haru_Kiss/01000156__GIGA_Haru_Kiss`、`GIGA_Haru_Kiss/01000253__GIGA_Haru_Kiss`：候选上下文复试分别报告 1.93–2.64 秒停顿中 2.61–2.64 秒活动，以及 1.27–1.69 秒停顿中 1.65–1.69 秒活动、1.92–2.05 秒停顿活动；这是自动声能证据，具体原生边界变化根因未进一步定位，保留为失败。不能将 99→107 的净增 8 全部当作规则效果，直接可归因的是上述 21 条映射恢复。

实际通过的旧轮 TextGrid 已包含 `dː dzː ɡː tʲ v vʲ ɸʲ`，因此用户第二组也并非均被过滤。候选新增实际 `ɸː` 的 5 个成品区间，例如 `AKABEiSOFT3_Hataraku_Otona_no_Ren_ai_Jijou/kok_0106__AKABEiSOFT3_Hataraku_Otona_no_Ren_ai_Jijou` 2.99–3.11 秒为单一区间 `ɸː`，`phone_kana=ッ|フ`；`COSMIC_CUTE_Gleam_Garden_no_Shoujo_witch_in_gleamgarden/miz_21043__COSMIC_CUTE_Gleam_Garden_no_Shoujo_witch_in_gleamgarden` 1.79–1.88 秒同理。`mʲː` 新进入 3 条准备词典，但仍没有最终通过音频；`hː tʲː` 同样有合法准备候选、无本组通过成品。源候选数、被接受词典数、最终真正采用的区间数分别统计在 `phone-coverage.json` / `coverage-report.md`，不能混为实际音频覆盖。

全缓存 137,025 个 mora/phone 键对照：115,159→116,044 可映射，新增 885、旧映射回归 0、新歧义 0；此数字已包含前 12 条候选，不能与之前的 839 相加。新增测试 `tests/unit/test_phone_inventory_20261008.py` 在旧表上 21 failed / 19 passed，在候选上正负例全部通过，相关定向合计 50 passed。完整快照回归 861 passed / 4 skipped。最初快照遗漏 README、上游回归适用性文档与子进程 PYTHONPATH，3 failed 日志留存，补齐诊断快照后完整通过；未据此改产品代码。两阶段所有通过结果均核验账本 SHA，与 SHA 相同原 WAV 副本配对，再用 `tools/audit_textgrid_pauses.py` 独立检查结构、相邻停顿、标点共享边界及声能：旧轮 99 files / 0 failed，新轮 107 files / 0 failed。没有缺失 TextGrid 被记为通过，自动验证不代替人工音素真值。

**运行中规则已应用：** 原表 SHA-256 `2fff45cf99f405bae4af99881584069c9e2b0c0065574943cdba742ee427abfe` 保留为 `production-map-before.yaml`，新表 SHA-256 `b6025bda5be2f3cf51c8e6a18e2815ed885a94befdb6152561e28382d0664c6b`。安全切换只暂停扫描器 2967012，共 63.73 秒，等待全部子进程退出，保留完成对齐的旧批 `fa9b956479f444329ef7128c27498852` 原报告（2,000 条，SHA `1acea0e1ac843babce8db460d479d314803e647754d5c625a1035471284a8c7b`），并对尚未对齐的预取批 `dd02cebe80be436e95f6b906e85dd39b` 先完整保留旧 run/日志，再用标准准备流程重建全部 2,000 条；可准备数 1,840→1,852，原准备成功源无丢失。扫描器在 finally 恢复，同一批已启动标准 `--use-prepared` 对齐；未仅依赖“无子进程”就忽略排队旧包。`apply-receipt.json` 保存旧新包 SHA 与恢复回执。第一次应用启动误用缺 praatio 的系统 Python，在导入阶段即退出，未暂停进程或修改表；原失败日志留存，改用生产 orchestrator 环境后成功应用。后续生产整批结果仍需以正式终态报告为准，不把预处理恢复数当最终发布数。

应用后生产目录再次完整回归 **861 passed / 4 skipped**，规则 SHA 与已测试候选完全相同，定向文件及台账 `git diff --check` 无错误。`post-application-health.json` 验证扫描器已恢复、同一生产常驻模型保留、重建包 2,000 源/1,852 准备成功可完整加载，417 条原生产记录/输出 SHA 仍相同。记录时新批仍执行中，尚无最终报告，因此不宣称该生产批最终通过或已完成无版本错误审计。

### JA-032/JA-021 追加：2026-10-08 全部历史筛除项替换当前扫描进程重跑

用户要求用修复后的管线重跑历史筛除项并替换当前 MFA，随后明确指出范围应是接近 200 万条，不能仅限此前抽样。冻结生产账本确认 **1,820,426 条 filtered、587,636 条 passed**；393 条仅是上一轮已核实含目标 G2P 候选的历史失败优先子集，不能当作全部失败数。全量队列为优先 393 条 + 其余 1,820,033 条。原失败原因包括声能覆盖 1,422,836、不可映射 190,932、时间戳不合 129,236、格式失败 49,882、不支持文本 16,479、BGM 5,705 等；此次按用户要求全部纳入，不把规则修复等同于这些原因全部解决。

393 条中目标候选源数为 `bː:1,dʲː:7,mʲː:4,ɟː:3,ɸː:10,dː:52,dzː:9,hː:95,ɡː:18,tʲ:111,tʲː:4,v:15,vʲ:7,ɸʲ:72`，各数可重叠。源键、原三联 SHA、原状态、旧诊断 SHA 和切换时状态见 `filtered-retry-20261008/known-filtered-phone-evidence.json`；这是实际 G2P 候选证据，不是人工听辨，也不是全 182 万条的完整音素频数。

证据位于 `.runtime/jobs/galgame-mfa-all/filtered-retry-20261008/`，指向服务器本地 `/mnt/nvme4/JapanMFA/galgame-mfa-all-evidence/filtered-retry-20261008`。暂停旧扫描、等待其全部后代任务退出后，保存一致的完整账本 `full-ledger-before.sqlite3`（SHA-256 `88a80d7b97c21a1f921f3b30196bce4bd495f903bcc8312da423cd2824745c66`）及固定失败队列 `cohort.sqlite3`（SHA-256 `e902b7b33e5ada85d437650344ed88955802b074ef3f7a4e30cd01358978d594`）。旧未提交工作 `1c7c181ba1f74a7390e4374efc25dead` 的完整对齐报告/预处理包与 `4591de71dd794250b87fb0ee495cb59a` 的排队预处理包留在原 work 路径，重要文件 SHA 在 `retained-work.json`，没有改记为通过。它们不属于冻结时已落账的失败队列；历史重跑结束后普通全库扫描会重新发现尚未落账的源，保留原工作供追溯。

旧扫描器 2967012、监督器 2967011、启动器 2966640 和两个旧常驻模型进程均已退出。停止旧常驻服务时客户端收到 `ConnectionResetError`；切换脚本记录为失败并未伪报新进程已启动。随后逐个确认全部旧 PID 已退出，再启动新服务，原失败日志与 `switch-receipt.json` 保留，恢复记录为 `restart-receipt.json`。新启动器 1193915、监督器 1194037、历史重跑扫描器 1194292，实时阶段 `retry-filtered-priority`。仍使用已全量验证的 355 条音素表 SHA `b6025bda5be2f3cf51c8e6a18e2815ed885a94befdb6152561e28382d0664c6b`、原配置、原始 NAS 三联和标准 MFA/最终审计；旧常驻请求完成后才替换服务，不并行保留两个正式扫描器。

运行脚本 `retry_filtered.py` 只读取冻结队列。每条处理前将旧失败 JSON、旧各模式 postprocess、存在的旧 TextGrid 复制至 `prior/<source-key>/`，写入 SHA/原账本行回执后才执行源预检；正式输出仍由标准 `_commit_batch` 的 `tools.audit_textgrid_pauses.audit` 检查结构、相邻停顿、标点边界和 WAV 声能后发布。源缺失记入单独 missing-sources 记录并保持原失败，不计作通过。重启时仅重跑当前仍为 filtered 且 batch_id 仍等于冻结代次的源，已产生新终态的失败也不会从头反复重跑；已经 passed 的条目跳过。原失败证据不会因再次筛除覆盖丢失。新增队列/证据保护测试及既有发布、预处理、音素回归共 **55 passed**，最终脚本保护测试另 **7 passed**，此前已部署产品完整回归 **861 passed / 4 skipped**。

该次操作启动了长期后台任务，尚未完成 1,820,426 条重跑；当前阶段进度不代表全量终态。优先队列结束后自动重跑剩余历史失败，再恢复普通全库扫描。最终通过、继续失败、缺失输入与尚未处理必须分别统计，不能把进入队列或准备成功当作最终通过。

**启动验证发现的运行态问题及修正：** 第一次替换启动器 1193915 虽建立了重跑扫描器，但两个旧 Unix socket 文件仍存在、内核已无监听者。原启动脚本仅凭 `-S` 判断就绪，使新 resident 因“socket already exists”退出，而扫描器仍进入准备；首批 `e2f60858ada84dc8a1d62b3f90fed4b7` 最终连接失败、无完整报告，标准提交入口正确中止，393 条原状态未改。该次启动不算成功，`startup-verification.json` 保留 attention_required 证据。确认所有旧/首轮新服务已退出，检查 `/proc/net/unix` 不含两入口后，将失效 socket 原样改名留在同一文件系统（跨设备 rename 的初次尝试失败，未删除任何入口）。修正本次启动脚本为先检查两个 resident PID 存活，再检查 socket，并在启动监督器前再次检查 PID。第二次启动器为 1196047，常驻服务 1196183/1196184、监督器 1196449、重跑扫描器 1196451；新 socket 创建时间为 2026-10-08 12:18 UTC。`stale-sockets.json`、`restart-after-stale-sockets.json` 保留修复证据。重跑从同一固定失败代次恢复，已备份的 393 条旧证据复用，未把启动故障记成源音频失败。

**最终运行确认：** `verified-running.json` 已确认第二次新原生进程 1196183 实际完成 align 请求且 code=0，新准备进程 1196184 实际完成 G2P 请求且 code=0；不能只凭 PID/socket 文件存在认定启动成功。新批 `f4fb61c942af47f0b37e1cbfc76eca28` 的 393 条完成准备（307 可进入对齐、86 准备失败），正在继续完整声学及最终审核。393 条旧证据回执全部存在，所有副本 SHA 逐项核验相同；固定队列仍完整为 1,820,426 条。新监督器状态 running，所有旧服务 PID 不存在，音素规则 SHA 保持已测试版本。该回执确认全量重跑已实际启动，不表示全量重跑完成。

### JA-032/JA-021 追加：2026-10-08 完整 83 音素无遗漏核对及清化元音缺项

用户要求保证每个音素涉及、没有遗漏，因此将检查范围从此前 21 种扩大为实际配置 `japanese_mfa` 声学模型元数据的全部 **83 种语音音素**。`japanese_mfa.zip` 与固定 `japanese_mfa-v3.0.0.zip` SHA-256 均为 `85928ffb1024486872a677a92e1fa94d2f997462d0b84c73a58aa9bb0e35179a`，模型内 `final.mdl` SHA 为 `eee0d60657af89c468ec47be97a55bda4513e4d7201d44761d518b31f08a77c9`。另外明确登记 `<eps>`、`sil`、`spn` 三个控制/静音/未知语音符号，不将其当成词汇 mora 音素，也不漏在清单之外。

全表核对新发现 **`i̥`、`ɨ̥` 两个结构性缺项**：旧 355 条表无入口；固定模型词典分别含 1,292、1,291 条相应词例，`ɯ̥` 也有 1,182 条词例且旧表上下文很有限。当前 G2P 缓存三者均未观测到，因此没有对应真实失败音频时间坐标，不能宣称已经定位到清化元音导致的历史筛除。证据及完整词例见 `.runtime/jobs/galgame-mfa-all/all-phone-coverage-20261008/inventory.json`，词典 SHA `4a0c66760576e4b7f3748f3169e7d5217c0135f857f0b5d34637c93a85fd1c91`。只采纳在整个词典读音上能成功匹配、具有明确 mora 归属的 20 条精确清化元音规则：`キ/シ/チ/ティ/ヒ/ピ/フィ` 的 `i̥`，`ス/ツ` 的 `ɨ̥`，`ク/フ/プ` 的 `ɯ̥`，以及有完整词例的 `ッキ/ック/ッシュ/ッス/ッチ/ッツ/ッティ/ップ` 组合。不是去掉 IPA 清化标记，也不借清化接受错元音、漏促音或短音冒充长音。每个原输入音素仍只有一个归属条目及区间。

新增固定元数据/词例证据 `tests/fixtures/japanese_mfa_v3_phone_inventory.json`，为 83/83 音素提供完整词典词例；`tests/unit/test_complete_phone_inventory.py` 验证清单完整、每个词的完整匹配、输入音素数量不变、所有 mora 被覆盖、新规则精确 spans、清化标签保留及错元音/缺长度负例。旧表先得到 **24 failed / 84 passed**，候选完整回归 **969 passed / 4 skipped**，安装后两组音素回归 **148 passed**。全缓存 **137,622** 个 mora/phone 键：可映射数保持 **116,485**、新增 0、回归 0、新歧义 0；因此不把这 20 条新规则归功为当前历史音频的新增恢复。此前所有 83 种规则入口和完整词例正测现已齐全，但“有规则/词例”不等于“所有音素都在现有真实素材出现”。

规则表 **355→375** 已安全应用；旧 SHA `b6025bda5be2f3cf51c8e6a18e2815ed885a94befdb6152561e28382d0664c6b`，新 SHA `a07189cb24a762248ed43445b50a63823c198c989910c238c544c5caf6322ad9`。暂停当前历史重跑扫描器 1200291 并等待全部子任务完成，保留旧表对齐完成批 `576059e622a342de988ecee21899ec7d` 的 2,000 条报告（SHA `d3e9d8831a857f1baf9b47df4c84af4fc20d4fac7e2036321cdbc53a49990952`）；保留旧预处理包后，重建排队批 `df8c47219d68442589da8e0819d16210` 的全部 2,000 源，准备成功保持 891、无成功源丢失。`apply-receipt.json` 保存旧新包 SHA，扫描器已恢复。旧已保留的未提交批和首轮 socket 故障批明确排除在当前活动窗口重建之外。固定全量失败队列保持 **1,820,426** 条，未因某音素难匹配而删减。`filtered-retry-20261008/active-map.json` 登记新验证规则版本，重启校验优先读取此记录，原冻结队列和原版本回执不改写。

真实重跑首组 393 条已完成：**84 正式通过、309 继续失败**。原源键及三联 SHA 仍在原队列证据；正式报告 `reports/f4fb61c942af47f0b37e1cbfc76eca28.json` 保留全部终态。84 份 NAS TextGrid 与原 WAV 独立配对运行 `tools/audit_textgrid_pauses.py`，**84 files / 0 failed**，报告 `all-phone-coverage-20261008/priority-audit.json`；这不是全量 182 万条已经完成。随后已进入 remaining 队列。

新增只读后台覆盖统计进程 1212704，脚本 `all-phone-coverage-20261008/watch_coverage.py`，每批核对正式报告、当前账本 batch_id、发布审计成功标记和 NAS TextGrid SHA，再解析真实 phones 区间。只有完成落账且检查成功的批次才入覆盖统计；缺文件、哈希不符或模型清单外音素进入 `coverage_errors`，不记作成功。83 种音素始终全部列出，包括零观测项；另登记缓存候选记录数、完整词例、已安装规则是否支持和真实成品源数/坐标。模型包 SHA 发生变化时拒绝沿用旧清单。固定源队列没有按音素筛选，因此其中任何音素都不会因不在优先 393 条中而漏跑。

`verification.json` 的当前快照已核验 **4,393 条重跑终态**，实际通过音频出现 **66/83** 种音素，覆盖错误为 0；其余 17 种明确保持“未在通过音频观测到”，持续统计于 `coverage-live.json`，不能伪称真实音频已覆盖全部 83 种。自动规则测试及声学门禁不是人工音素真值。人可读全清单见 `coverage-report.md`；此快照之后的实际进度以持续更新 JSON 为准，全量重跑仍在进行。

### JA-032/JA-021 追加：2026-10-09 缺少 12 音素的真实音频优先复核

用户把每音素至少 500 条测试、100 条正式通过的目标限定为当前零观测的 `bʲː dʲː i̥ wː çː ɟː ɨ̥ ɯ̥ ɴː ɸʲː ɾʲː ɾː`，随后明确要求：语料音频确实缺少的音素跳过，优先处理有音频的音素。固定 375 条规则表已能逐一映射这 12 种；但当前原生 G2P 缓存对 `bʲː i̥ wː çː ɨ̥ ɯ̥ ɴː ɸʲː` 的真实候选数为 0。官方词典有相应完整词例，不能据此声称这 8 种已存在于当前对齐音频。模型字典候选与当前 G2P 输出是不同来源；字典命中只是检索线索，不计入声学测试或通过数。

只读扫描 `.runtime/jobs/galgame-mfa-all/batch-evidence` 与 `preparation-evidence` 全部 1,384 个归档目录、2,362,003 条前端记录，前端读取错误 0、源键解析错误 0。精确候选源数中 `bʲː:0,dʲː:1,wː:0,çː:2,ɟː:3,ɸʲː:0,ɾʲː:0,ɾː:1`；`i̥:566684,ɨ̥:516275,ɯ̥:183225,ɴː:302279` **仅为官方词典读音命中所对应的源键上界，不代表其音频已经包含相应音素**。证据 `missing-phone-priority-20261009/search-complete.json`、`source-candidates.json`、`targets.json`。剩余原始 TXT 的只读检索运行于 `search_raw_text.py`，结果需以完成回执核定；命中文字并非语音学真值。

对其中 7 条稀有真实 WAV/TXT/CTC 三联保留输入 SHA 于 `missing-phone-priority-20261009/private-seven/input-evidence.json`，用相同正式管线及标准质检在隔离输出复跑，完整报告 `private-seven/state/reports/14e6e18d71df4486a8f3d6b55f210755.json`：7 条完整输入、6 条准备成功、1 条 `no_mappable_pronunciation`、0 条最终通过、7 条仍失败；没有缺失 TextGrid 被计为通过，也没有发布私有输出。`GIGA_Ai_Kiss/03040235__GIGA_Ai_Kiss` 的 `dʲː` 位于 1.39–1.40 秒，`Aino_Links_Sousaku_Kanojo_no_Ren_ai_Koushiki/kir_50147__Aino_Links_Sousaku_Kanojo_no_Ren_ai_Koushiki` 的 `ɟː` 位于 6.23–6.24 秒，`CLOCKUP_Ouju_no_Shima/tog_oju_0108__CLOCKUP_Ouju_no_Shima` 的 `ɾː` 位于 10.00–10.01 秒（context 路线为 9.74–9.76 秒）；三条均因 `alignment_acoustic_coverage` 筛除。其余四条只含跨 token 字典词例命中或其它词例，不出现目标对齐区间；`CLOCKUP_Ouju_no_Shima/him_oju_0243__CLOCKUP_Ouju_no_Shima` 还在准备阶段失败。以上区间是自动对齐几何，不是人工确认的长辅音真值；尤其 10–20 毫秒的长辅音标签不能作为可靠的通过覆盖。现有材料不支持虚报每种已测 500/通过 100，且原正式历史筛除重跑仍继续。

**隔离词典候选实验，不改生产 G2P 或已发布成品：** 对精确锁定读音仅附加固定官方词典中可完整 mora 映射的 `i̥ ɨ̥ ɯ̥ ɴː` 候选，保留原生发音为首选，MFA 可按声学选取；没有拆分原音素或强改标签。20 条原筛除音频在 `private-dictionary-pilot/` 复测，20/20 仍筛除，虽失败对齐中 `i̥`、`ɨ̥` 各有 2 条被选中，但零最终通过，不计入成功。另取 40 条原生产已通过且含精确读音的真实音频作为对照，在 `private-dictionary-passed/` 保存原三联 SHA、私有发音变体与完整回执：34/40 私有重跑仍通过、6/40 退化为筛除；通过产物中 `i̥` 为 2/10、`ɨ̥` 为 4/10、`ɯ̥` 为 5/10、`ɴː` 为 0/10，具体音频与秒坐标在 `pilot-summary.json`。因此精确候选能被声学模型选择，但直接全局接入会使一部分原已通过音频退化；不得据 11 个私有通过样本宣称生产配额完成。第一次对私有 TextGrid 独立调用 `audit_textgrid_pauses.py` 因私有输出缺少配对 WAV 得到 34/34 失败，保留 `audit.json`；随后按输入证据 SHA 拷贝 34 份原 WAV 至私有目录，全部哈希核对一致，重审 `audit-paired.json` 得到 34 files / 0 failed。没有把第一次缺配对的样本当成功。所有产物在本地隔离路径，正式历史重跑与 NAS 已发布成品未改；自动通过及官方词典候选都不等同于人工清浊/长音真值。

为区分普通鼻音与词面明确延长的鼻音，再只读扫描同一批 1,384 个归档、2,362,003 条前端记录中的精确锁定读音 `ンー` / `ンン`，错误 0、候选源 0，回执 `missing-phone-priority-20261009/long-nasal-complete.json`。这加上上述 10 条普通 `ン` 的 0 次实际 `ɴː` 选择，只支持暂缓 `ɴː`，不证明未归档原始语料绝无长鼻音。全 642 万原始 TXT 的字面检索曾启动，但 NAS 每文件读取速度不足以在本轮完成；已停止该不完整扫描，不能拿它宣称全语料阴性。优先使用已完整归档且具原始 WAV 的样本继续验证三种确有实际通过标签的清化元音。

**大样本配额实测进行中：** 从正式账本当前已通过且官方词典精确读音可提供清化元音候选的源中，按 WAV SHA-256 去重选出 `i̥` 800、`ɨ̥` 500、`ɯ̥` 500，共 1,800 条互不相同的真实音频，选取回执 `missing-phone-priority-20261009/private-dictionary-scale/selection-complete.json`。初次直接 NAS 顺序预检约 3 分钟只到第 79 条、正式提交 0，记于 `aborted-nas-preflight.json`；改为在隔离路径中按原 WAV SHA 验证并复制 WAV/TXT/CTC，再跑相同 MFA 与正式声能门禁，不更改源文件。首批 500 条 `i̥` 不同 WAV 全部预检，私有重跑 448 整条通过、52 筛除；其中 **118 条通过 TextGrid 的 phones 层实际包含 `i̥`**，120 个区间。例：`Clochette_Haruru_Minamo_ni/e_asumi_a07_010__Clochette_Haruru_Minamo_ni` 4.53–4.58 秒，`Cabbage_Soft_Amairo_Chocolata/mik_b000288__Cabbage_Soft_Amairo_Chocolata` 0.63–0.67 秒。118 份私有 TextGrid 与 SHA 相同原 WAV 组成 `private-dictionary-scale/retained/i_devoiced/`，118 个 WAV 哈希互异，独立 `audit_textgrid_pauses.py` **118 files / 0 failed**；逐源时间坐标、SHA 和原正式账本行在 `retained/i_devoiced-evidence.json`，审计回执 `retained/i_devoiced-audit.json`。因此 `i̥` 达成私有隔离集的至少 500 条真实音频测试和 100 条审计通过配额；这些不是当前生产 NAS 成品，尚不计为生产覆盖，自动通过也不是人工清化真值。其余两种仍在复制/测试，不能预报完成。

**2026-10-09 全量优先队列终态：** 用户要求直接全量加速后，先以 8 路只读复制、逐个 SHA 核验，把全部 1,800 组原 WAV/TXT/CTC 搬到本地隔离快照，1800/1800 完整、0 复制失败，见 `private-dictionary-scale/copy-complete.json`、`copy-evidence.json`。随后用实际 `tools/galgame_mfa_all.py` 及正式最终声学门禁，对 1,800 条互异 WAV 全量运行私有词典变体实验，未拆开单个音素。固定测试数为 `i̥` 800、`ɨ̥` 500、`ɯ̥` 500；终态如下。`passed` 指整句通过私有管线，留存数还要求通过 TextGrid phones 层确实出现目标音素，不能将所有整句通过误记为目标音素通过。

| 目标音素 | 不同真实 WAV 已测 | 整句私有通过 / 筛除 | 实含目标音素的已留存 TextGrid/WAV 配对 | 目标区间 | 独立停顿/标点/声能审计 |
|---|---:|---:|---:|---:|---:|
| `i̥` | 800 | 717 / 83 | 203 | 210 | 203 files / 0 failed |
| `ɨ̥` | 500 | 469 / 31 | 182 | 184 | 182 files / 0 failed |
| `ɯ̥` | 500 | 448 / 52 | 175 | 176 | 175 files / 0 failed |

全部 560 对的原 WAV SHA、私有 TextGrid SHA、phones 层目标标签和秒坐标重新逐项解析验证；560 个 WAV SHA 互异。每对原正式 TextGrid 在 `private-dictionary-scale/prior-production/<game>/` 留存，560/560 原哈希匹配、0 缺失，比较回执 `prior-compare.json`。对比原正式结果，497/560 的非目标音素序列不变；另有 63 条出现区间数或其它音素变化，不能无条件覆盖原成品。为以后审慎采用，`full-run-verified.json` 另外列出每音素 100 条保守子集：非目标音素序列不变且同序号边界最大差值不超过 0.03 秒；候选总数分别为 `i̥` 116、`ɨ̥` 145、`ɯ̥` 104，均足 100。该阈值只是自动几何筛选，不是人工清化真值，也未把私有结果冒充生产正式成品。留存路径分别为 `private-dictionary-scale/retained/i_devoiced/`、`s_devoiced/`、`u_devoiced/`；逐源哈希、坐标、原生产账本状态见各目录旁 `*-evidence.json`，完整核对脚本 `verify_full_run.py`，总回执 `full-run-verified.json`。首轮私有对照曾有 6/40 原通过音频退化，故不能直接把词典候选无差别接入运行中全量生产管线。当前历史 1,820,426 条筛除队列的正式重跑及 375 条规则表继续执行，这 560 份为隔离留存；正式覆盖监控仍按正式已发布 NAS 与生产账本计数。其他指定缺音素没有足量经过证实的真实候选或稀有候选最终通过，依用户指令暂缓，不能写成已测 500/留存 100；后续如果出现可验证音频，应按同一门禁另行处理。所有以上声学、边界和能量检查均为自动证据，不构成人工语音学真值。

### JA-032/JA-021 追加：2026-10-09 暂停历史重跑并把 1,800 条优先队列正式输出至原 NAS 目录

用户明确要求停止历史筛除重跑、记录中断点，先处理上述 1,800 条并输出到同一个文件夹。暂停 `retry-filtered-remaining` 的扫描器、监督器及启动器后保存正式 SQLite 一致性快照和在途工作目录清单，随后终止进程；未提交批次未写入正式账本。中断回执 `.runtime/jobs/galgame-mfa-all/missing-phone-priority-20261009/historical-interruption/checkpoint.json`，账本快照 `progress-at-interruption.sqlite3` SHA-256 `5bfede4a7b4dfb0c0e012eeb54bccc453c9e4853be849ccf68d67cab498a7d02`。冻结队列总量 1,820,426；按“仍为原 batch_id 且 filtered”精确判断，**1,396,033 条尚待历史重跑，424,393 条已离开原待跑状态**。历史监督器、扫描器、在途子进程已不存在，两个工作锁空闲；`live-status.json` 已标为 `paused_by_user`，旧状态和哈希保留于 `historical-interruption/`。后续恢复须按回执里的同一不可变队列和 `remaining` 阶段续跑，不能将暂停误当作完成。

优先 1,800 条原本均是正式账本已通过的独立音频，此次执行属于**重新对齐并纠正目标音素**，不能从上述历史 filtered 队列的剩余数中扣除。复用前述已经全量运行、经 SHA 核验的同一输入和完整 MFA 结果以节省重复声学计算；其精确官方词典候选仅针对锁定读音附加，保留原发音，未把一个音素拆成两个。对 1,800 份原正式 TextGrid 在 `formal-publish-1800/prior-grid/<game>/` 逐项备份并与旧账本 SHA 一致；原 WAV/TXT/CTC 快照哈希、输入签名、配置 SHA、1,634 份新候选哈希及原账本状态均在 `formal-publish-1800/prepublication.json`。166 条本轮声学/最终筛选失败原因逐项保留，该 166 条原正式 TextGrid 和原 `passed` 账本未被新失败覆盖。1,634 条新候选在写入前与原 WAV 配对，运行 `tools/audit_textgrid_pauses.py`：**1,634 files / 0 failed**；相关规则、批处理和预处理交接回归 **119 passed**。

1,634 份通过的新 TextGrid 已原子写到原目录 `/mnt/Raw/GalgameMFA/<game>/<stem>.TextGrid`，正式账本逐条更新 SHA 与批次来源；100 条一批留下 `formal-publish-1800/publication-journal.jsonl`，NAS 读回核对 **1,634/1,634**，166 条原成品及原账本哈希保持一致，最终回执 `formal-publish-1800/publication-final.json` 为 1,800 输入、1,634 新发布、166 保留原结果、0 错误。写入后再次直接通过 NAS TextGrid 与对应原 WAV 独立审计 **1,634 files / 0 failed**，报告 `formal-publish-1800/audit-published-nas.json`。原始私有完整批次报告复制到正式 `reports/priority1800-<batch_id>.json`；本次并未恢复历史扫描器。

正式 NAS 的 phones 层和正式账本实际核对得到 `i̥` **203 条音频/210 区间**、`ɨ̥` **182/184**、`ɯ̥` **175/176**，详见 `formal-publish-1800/formal-target-coverage.json`。例：`/mnt/Raw/GalgameMFA/Clochette_Haruru_Minamo_ni/e_asumi_a07_010__Clochette_Haruru_Minamo_ni.TextGrid` 的 `i̥` 为 4.53–4.58 秒；`/mnt/Raw/GalgameMFA/CRYSTALiA_Setsuna_ni_Kakeru_Koi_Hanabi/VO07_2088__CRYSTALiA_Setsuna_ni_Kakeru_Koi_Hanabi.TextGrid` 的 `ɨ̥` 为 1.95–2.01 秒；`/mnt/Raw/GalgameMFA/GIGA_Haru_Kiss/99020055__GIGA_Haru_Kiss.TextGrid` 的 `ɯ̥` 为 2.38–2.44 秒。对应 WAV 位于原 `/mnt/Raw/JapGalgame/<game>/wav/`，留存源副本和哈希位于 `private-dictionary-scale/source-snapshot/`、`copy-evidence.json`。这些是正式结果和自动审计证据，不是人工听辨清化元音的语音学真值。既有 `all-phone-coverage-20261008/coverage-live.json` 只统计历史 filtered 重跑队列，已随该任务暂停，不应以其零值否定本批正式输出；这批目标音素数以本段新的 NAS/账本核对为准。其余九种缺音素仍因没有足量可验证音频或稀有候选未过审核而暂缓。

**2026-10-09 用户要求续跑后的状态：** 从 `missing-phone-priority-20261009/historical-interruption/checkpoint.json` 所记录的队列继续使用原 `filtered-retry-20261008/start_retry.sh`、原 375 条规则 SHA `a07189cb24a762248ed43445b50a63823c198c989910c238c544c5caf6322ad9` 和原正式账本；恢复回执 `missing-phone-priority-20261009/historical-resume-receipt.json`。启动前确认无残留扫描器/监督器、`job.lock` 和 `orchestration.lock` 均空闲、`remaining-summary.json` 尚不存在。恢复后监督器为 `running`，扫描器已进入 `retry-filtered-remaining`，进程 1928171 的累计读入字符由 1,862,943,131 增至 2,123,316,258，原证据归档日志已写到 `prior_evidence_saved: 1400`，说明不是空启动；当时尚未有新 2,000 条批次落账，不能提前增加通过数。覆盖只读进程也已恢复，回执 `coverage-resume-receipt.json`，其最新正式队列统计 424,393 条、错误 0。此次续跑不会重复扣减原来正式已通过的 1,800 条优先队列；历史剩余以原 cohort 行状态及后续实时账本为准，尚未宣称全部完成。

**2026-10-09 用户纠正处理对象：切回未处理原始音频。** 此前恢复后的历史 `retry-filtered-remaining` 又处理 30,000 条；用户明确指出应继续正式账本中尚无记录的原始数据。已暂停并停止历史扫描器、监督器和启动器，保存第二次一致性断点 `missing-phone-priority-20261009/historical-interruption-for-raw-20261009/checkpoint.json`：原冻结队列 1,820,426 条，454,393 条已离开原待重刷状态，1,366,033 条仍留待将来重刷；SQLite 快照 SHA-256 `7b326e2d57d8a4a56b41be01d47e3aef8d67804edfcf7a61f81a3f3cb34c7c6d`，未提交工作目录仍保留。新进程位于 `unprocessed-raw-20261009/`，启动回执 `launch-receipt.json`，沿用正式 `/mnt/Raw/JapGalgame` 原三联输入、固定配置/规则、同一个 `/mnt/Raw/GalgameMFA` 输出和正式进度账本。读取 16 份本地 CTC 原始清单，先以启动时正式账本 **2,408,062 个已有源键**筛掉所有已处理项，无论其旧状态为 passed 或 filtered；只对账本中完全不存在的键检查原三联并进入正式 MFA。CTC 清单已完成 16/16 工作者，6,421,468 条成功、1,640 条 CTC 失败；缺三联原键登记在 `unprocessed-raw-20261009/missing-source.jsonl`，不算成功。新监督器状态 `running/unprocessed-original`，前 240 万条本地清单中 2,399,411 条已有账本而跳过、588 条缺三联；此时第一批尚未提交。其后第一批 2,000 条新源已进入 `work/8a9246c1450b41e581e201d91eed189d/` 的准备/对齐，抽查 `GIGA_Mell_Kiss/01000380__GIGA_Mell_Kiss` 等 5 个源键均在提交前查无正式账本行。第一批最终通过数与声学审计必须以完成报告为准，不能把已选入批次写成已通过。历史 filtered 覆盖统计进程已停，原队列保持暂停；这次切换不会继续重刷旧筛除结果。

**原始数据第一批完成核对：** 新流程首个正式批 `8a9246c1450b41e581e201d91eed189d` 确认 2,000 个原账本不存在的源键；真实报告 `reports/8a9246c1450b41e581e201d91eed189d.json`，准备 1,885 条，候选通过 387 条，报告 `total_seconds` 524.7。正式落账最终 **387 passed / 1,613 filtered**，387 份 `/mnt/Raw/GalgameMFA/<game>/<stem>.TextGrid` 逐项与报告及账本 SHA-256 相同，原 WAV 均存在，未把缺输出算作通过。正式 `_commit_batch` 的每条结构/声能审核均为通过后才发布；另一次对全部 387 对的独立 `audit_textgrid_pauses.py` 会反复从 NAS 读取完整 WAV，运行约 9 分钟仍未结束并与正在运行的原始数据 MFA 抢占 NAS 带宽，因此退出码 143 主动中止，记录 `unprocessed-raw-20261009/first-batch-audit-aborted.json`，**不得算作 387/0 的独立审计成功**。原始数据任务保持 `running/unprocessed-original`，第二批 2,000 条已在工作区生成完整候选报告但尚待正式落账，最终状态只能以后续正式报告和账本为准。自动门禁结果不等于人工音素边界真值。

**JA-021/JA-032 复发与覆盖口径复核（2026-10-10 03:57 UTC，只读）：** 正式 `.runtime/jobs/galgame-mfa-all/progress.sqlite3` 此刻为 **734,359 passed / 2,135,703 filtered / 2,870,062 已落账**；filtered 的终态理由中 `no_mappable_pronunciation` 为 **123,531**，`malformed_output` 为 **51,601**，但仅凭汇总理由不能断定每条的具体 G2P、映射或重音根因。近期批次 `reports/130bcca03a8149fbac5fa7fb062862a3.json` 的 2,000 条中有 88 条 `no_mappable_pronunciation`，例如原三联 `/mnt/Raw/JapGalgame/Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei/{wav,txt,ctc}/KRI060206__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei`（报告别名 `u00a28d5fa98eb0f53268ccfa`，whole/timed 均失败，0 发布）。这类准备阶段拒绝没有可信音素秒坐标，时间坐标不适用；其单条根因需保留锁定读音和完整 G2P 候选再分类，不能靠增加任意映射规则。当前固定 map SHA `a07189cb…` 有 375 条规则，模型清单 83 种音素均有完整词典词例的可映射见证；对应定向回归 **221 passed**，只证明规则对这些见证可达，不证明任意语料读音可映射或音频内确有该音素。2026-10-09 的已发布标签扫描报告为 **75/83**，其后正式新批次仍在运行，尚无覆盖当前 734,359 条 passed 的完整标签复扫；先前未观测的 8 种不能追认为当前仍缺或已经补齐。修复状态：本次为只读审计，未改规则、重音、正式 TextGrid/WAV 或账本。剩余范围：按完整当前正式成品复扫 83 种音素及 `??` 声调分布；对近期 `no_mappable_pronunciation` 逐条区分合法新变体、缺音/插音、读音错误；缺失 TextGrid 与声学拒绝继续计失败。自动规则测试与声学门禁均非人工音素或重音真值。

**JA-021 同根因定向修复候选（2026-10-10，隔离工作树，未切换生产）：** 上述真实样本源 TXT 为「お姉ちゃんのおっぱい吸って、お姉ちゃんの手でシコシコしてもらって。」；锁定 `オッパイ` 切成 `オ/ッ/パ/イ`，生产 G2P 缓存 `native-word-cache/native-words.sqlite3` 返回 `o p a i`，没有表示促音的长辅音，所以当前规则正确拒绝。固定 MFA v3 词典 `.runtime/models/japanese_mfa-v3.0.0.dict` SHA-256 `4a0c66760576e4b7f3748f3169e7d5217c0135f857f0b5d34637c93a85fd1c91` 第 42839–42840 行给出完整 `o pː a i`；现有 map 能把原 `/pː/` 同时归属 `ッ/パ`。同词典另证实 `マッタク→m a tː a k ɯ`、`セッカク→s e kː a k ɯ`、`カッテニ→k a tː e ɲ i`，四项现有 map 均可完整投影。隔离候选位于 `.worktrees/dictionary-geminate-20261010/`：仅当该精确读音所有原 G2P 候选均不可映射、且其中一项与固定词典候选**恰好只差一个辅音长度符**时，才选用完整词典候选；原成功候选不变，错读音、错元音及 `ケッコウ/ガッコウ` 等尚缺跨 mora 规则者仍拒绝。真实样本按原 TXT、生产缓存和固定 map 重放，14 个 token 全部可准备，只有 `オッパイ` 候选由 `o p a i` 变为 `o pː a i`；对应单测先红灯 4 项、修后相关 110 passed，隔离完整非真实模型回归 **1005 passed / 16 deselected**。这只验证词典候选和准备阶段，尚未对该 WAV 完成私有 MFA、声能审核或独立 TextGrid/WAV 停顿审计；原样本正式账本仍 filtered、正式 TextGrid 不存在，时间坐标不适用。没有从音频推断 `/pː/` 的实际时长或重音，未改原三联、生产代码、运行中任务、NAS 成品或正式账本。下一步须在安全批次间隙审查候选、对固定原 WAV 做私有完整管线和人工听辨，再决定是否按原 SHA 保留旧产物并正式重试；其他 123,531 条映射筛除不可据此视为恢复。

**JA-021 同候选真实私有 MFA 复核（2026-10-10，补正上段阶段范围）：** 首次在隔离工作树 `.runtime/private-geminate/` 调用生产 preparation resident，被其作业路径隔离拒绝为 `command_failed`；该次 0 准备、0 对齐，失败原样保留，不能当音素阴性。将私有运行/缓存/输出全部移入作业本地 `.runtime/jobs/galgame-mfa-all/private-geminate-20261010/` 后，沿用相同原 WAV/TXT/CTC 与固定模型重新执行完整 resident-timed + context 审核：**1/1 准备成功**，timed MFA 5 个原始输出、context 3 个，`オッパイ` 的原 `/pː/` 区间 **1.48–1.65 秒**，`phone_kana=ッ|パ`、`phone_tone=LL`。但 timed 及 context 都报 `alignment_acoustic_coverage`，0 私有成品、0 正式发布；timed 显式停顿 **2.04–3.44 秒**内 2.22–2.41 秒有活动声能（最大 RMS 约 0.1283），尾部 **6.48–7.958375 秒**内 6.66–6.97 秒亦有活动声能（最大约 0.1599）；context 第一疑点改为 2.33–3.44 秒仍未消失。原 WAV SHA-256 `0082be58ad1cba54b5fa6820c4dcf132d2a9cecf40f134d81a227a8e0862391e`；私有 `run/hybrid-report.json` SHA-256 `8e2e6749a716ea89fe340d0f53c6aa2f60ae3c665f265d3056f5ec36b0f09f68`，timed `postprocess.json` SHA-256 `6bd888f448d18a3180b717b9651c5c16a6cc613dd3ccb891ae618590a95d9867`。根因分开：词典候选解决 G2P 漏促音的准备断点；整句声能覆盖失败属于对齐/审核的另一断点，尚无人工音素金标，不可因 `/pː/` 有自动秒坐标就宣称发音真值。正式原账本仍 `filtered/no_mappable_pronunciation`、正式 TextGrid 缺失，此次私有运行未改生产代码或 NAS。无可发布配对，故 `audit_textgrid_pauses.py` 不应以 0 files 记作成功；后续需先人工核对两处声音归属，再决定是否改对齐/裁剪与正式重跑。

### JA-031 追加：2026-10-10 两个 MFA 常驻服务在主管线的速度与声学波动

用户批准后，在原扫描器不中断、在途窗口不切换的前提下，为后续 `resident-timed --use-prepared` 批次启用第二个独立常驻 MFA 服务。每个服务仍 `num_jobs=1`，原有四组各 500 源和上下文重试、8 个准备/审核进程、原 NAS 输入与正式账本门禁不变；第二服务模型 5 文件、236,001,612 字节与主服务逐文件 SHA-256 一致。正式回执为 `.runtime/jobs/galgame-mfa-all/dual-resident-rollout-20261010/`，批次逐阶段摘要为 `dual-resident-batches.jsonl`，完整说明为 `docs/superpowers/reports/2026-10-10-two-mfa-production-rollout.md`。生产尚未处理过的正式批 `6753835fb081489a823c96bb6f55bdb0`、`612bac3a3c93466ca40ba36136aee4d9`、`5303a3bf63c5487db06d20411ce2ec4f` 各 2,000 源，声学 MFA 分别为 **88.1/90.5/85.9 秒**，相对启用前最近 8 批 **180.2 秒中位数**约减半；前两批 311/295 份正式 TextGrid 逐条发布状态与报告相符，NAS SHA-256 与账本相符，0 缺失/冲突，各抽 12 份配原 WAV 做独立停顿、标点和声能审计，均 **12 files / 0 failed**。未通过的 1,689/1,705/1,644 条保持 filtered，不能算审计通过。自动审计不构成人工音素金标。

**声学边界复现与秒坐标：** 同一 2,000 源隔离 A/B 输入下，单服务 965 条、双服务 967 条、单服务复测 968 条通过；单与双有 8 条通过状态、510 份最终 TextGrid SHA 差异，单服务两次也有 5 条状态、502 份哈希差异。原 WAV `/mnt/Raw/JapGalgame/GIGA_JINKI_RESURRECTION/wav/fem_kan_01429__GIGA_JINKI_RESURRECTION.wav` 在单服务候选 `1.98–4.30 s` 停顿的 `3.38–3.47 s` 检出 90 ms 活动声能而拒绝，双服务候选停顿到 `3.38 s` 截止而通过；`fem_kan_00149__GIGA_JINKI_RESURRECTION.wav` 单服务上下文重试将 `1.92–1.99 s` 停顿起点改到 `1.95 s` 而通过，双服务重试仍从 `1.92 s` 起而拒绝。对应 TXT/CTC 与 WAV 未修改，私有逐条对照、postprocess、原生网格和审计保存在 `/mnt/nvme4/JapanMFA/two-mfa-residents-20261010/`；三组私有候选独立审计 965/967/968 files 均 0 failed，未发布。相同输入下的真实 MFA 重跑存在波动，配置为 `dither=1.0`，但尚不能将每条差异单独归因于并发或 dither；本次服务接入没有重跑或覆盖已有正式成品。

**剩余吞吐范围：** 生产正式报告落盘间隔在启用前 7 个相邻单服务批次为 277.9–305.3 秒；接入后的四个双服务批次间隔为约 319、541、340、248 秒。第四批 `e5c0a5f9668a4adfaa1153418f4a54f1` 正式终态 **423 passed / 1,577 filtered**、MFA 85.0 秒、报告总计 212.5 秒，间隔短于近期单服务，但整线目前没有持续提速证据。原生双服务的计算耗时合计约 168–174 秒，与单服务约 180 秒相近，没有观察到每个 MFA 输入被并发显著拖慢；超额时间仍需分辨预取准备、NAS 源读取、正式提交与发布。常驻 sidecar 持续写健康状态，完整回归 **1005 passed / 5 skipped**；不将阶段加速或自动审核解释为全线吞吐改善或人工边界真值。

**2026-10-10 04:21–05:01 UTC 运行故障及恢复：** 继上述四批后，第五个正式双服务批 `6912cdfe352f45c5b3e554694ace8bba` 完成 2,000 源、**522 passed / 1,478 filtered**，MFA 墙钟 85.6 秒、报告总计 288.2 秒。其后两个 MFA 常驻服务及准备服务在客户端断开连接时分别于 `connection.recv()` 的 `EOFError`、`connection.send()` 的 `BrokenPipeError` 非预期退出；服务端原循环未捕获这两种断连，导致后续批 `177cfbe2987647ea90ba7e25dc7d44fc` 于 04:31 请求原声学 socket 时失败，扫描器 04:33 停止。该批和已预取批 `a07b017faee349b6910255673923fa5e` 的正式账本均 **0 条**，无完整 `hybrid-report.json`，不能记作通过。原工作目录、输入分组和故障日志未清理，文件 SHA、故障状态和账本计数冻结于 `.runtime/jobs/galgame-mfa-all/dual-resident-rollout-20261010/incident-20261010-0421/before-restart.json`；此处没有可信的音素秒坐标，也没有据此发布或覆盖 TextGrid/WAV。客户端为何同一时段断开仍未定位，不能直接解释为两个服务抢占 CPU 或 NAS。

修复在 `src/japanmfa/mfa/native_resident.py` 对断连的请求读取与响应发送返回到监听循环，已用真实 `multiprocessing.Pipe` 断连测试先复现 2 失败、修复后通过；完整回归 **1007 passed / 5 skipped**。原正式账本切换前为 **736,266 passed / 2,143,796 filtered**，故障批无行；确认扫描、编排锁空闲和证据盘挂载后，以原启动脚本重启，同一正式账本继续只选未落账来源。重启后原声学、准备、第二声学三个 Unix socket 和各 PID 均已建立，`dual-resident.enabled=2`、健康状态 `running`，新扫描器正在重新读取本地原始清单；需等待下一正式批次报告验证持续生产。服务根目录互相独立、单服务内部 `num_jobs=1`，本次故障证据指向断连异常处理，尚非资源抢占的实证。

**重启后正式验收与剩余瓶颈：** 首批新工作 `5103b784919f4d868cd162070f44d3e9` 的 2,000 个输入别名与故障未提交批 `177cfbe2987647ea90ba7e25dc7d44fc` 完全相同；原故障目录仍保留。2,000 源中 1,906 条准备成功，完整报告和正式账本均为 **511 passed / 1,489 filtered**，未通过项仍按失败。抽样 3 份正式 TextGrid 在报告、账本、NAS 文件三方 SHA-256 一致，回执为 `dual-resident-rollout-20261010/incident-20261010-0421/recovery-batch.json`；这只做自动产物一致性核对，不是人工音素真值。双 MFA 声学墙钟 **86.3 秒**、服务原生时间合计 **165.7 秒**，未见计算互抢造成约两倍耗时。原始 NAS 输入预检 **85.5 秒**、本地快照 **94.8 秒**，与同 2,000 源故障前的 **92.9/98.9 秒**接近；候选发布阶段 **260.8 秒**。观察中对齐子进程及正式提交扫描器曾处于内核 `D` 状态并等待 `wait_for_response`，源挂载 `/mnt/Raw` 为 CIFS；代码在发布候选时逐条重读原 WAV。现有证据将整线瓶颈指向 NAS 输入和候选发布等待，不能仅据 `D` 状态断言具体文件或排除其他 CIFS 负载。下一批持续吞吐仍须继续观察。

**2026-10-10 06:25 UTC JA-031 吞吐复核与准备失败复发：** 重启后已有 13 个正式双服务 2,000 源批次；MFA 墙钟中位数 **84.9 秒**，启用前最近 8 个单服务批中位数 **180.2 秒**。内部报告总耗时中位数 **261.7 vs 278.3 秒**；正式报告的连续落盘间隔重启后 12 个中位数 **310.4 秒**，启用前 7 个中位数 **286.4 秒**，整线未见持续加速。最近 5 个间隔中位数 **515.9 秒**，实际吞吐下降更明显；各批输入不同，不能把全部差额归因于服务并发。未提交窗口 `.runtime/jobs/galgame-mfa-all/work/79f6b0b72c634545b52671b8cd52fb86/` 的 `input-timings.json` 记录 2,000 源预检 **148.9 秒**、快照 **153.7 秒**；`prepare.log` 仅写 8 个审核进程配置，`run.log` 记录 `preparation window failed`，未产出完整准备 bundle、无正式批报告、账本 **0 行**，故不得将 1,678 个已创建的准备目录当作成功。失败发生在输入准备阶段，无可信音素秒坐标；直接退出原因尚未定位，不能写作资源争用已证实或已修复。原工作目录保留；当前两个声学服务、准备服务和新扫描器状态均为 `running`，后续正式终态及失败根因仍需追踪。

**JA-031 最新阶段归因（2026-10-10 07:08 UTC）：** 与启用前 8 个单服务批的阶段中位数相比，首次故障恢复后的 13 个连续双服务批分别为：声学 MFA **180.2→84.9 秒**，审核 **47.7→50.3 秒**，候选检查与写入 **20.2→94.7 秒**，报告内部准备约 **29.7→30.5 秒**。主要增加发生在候选发布，抵消大部分声学收益。再次启动后的最近 4 个正式双服务批 `c8f8728f…` 至 `fdfa364a…` 的审核中位数 **79.3 秒**、候选发布 **126.6 秒**、报告内部准备约 **39.4 秒**，阶段变慢进一步扩大；MFA 中位数 **95.4 秒**仍明显快于原 180.2 秒。报告之外的 NAS 原始输入预检与快照，在故障批 `177cfbe…` 是 **92.9+98.9 秒**，在另一个准备失败批 `79f6b0…` 为 **148.9+153.7 秒**；这两批来源不同，不能当作同源 A/B，但足以说明额外等待并非 MFA 阶段本身。正式提交的 CIFS 等待尚无独立计时，不应给它编造秒数。各批原输入、失败状态和产物门禁不变；此分析是自动运行计时，不是人工声学边界真值。

**JA-031 2026-10-10 07:30 UTC NAS 读取复核：** 输入样本来自保留的失败窗口 `.runtime/jobs/galgame-mfa-all/work/79f6b0b72c634545b52671b8cd52fb86/run/preflight.json`，按序抽取 128 个原 NAS WAV，共 29.5 MiB。现有代码在预检和快照阶段完整读取同一个 NAS WAV 两次，通过候选发布又会重新读原 WAV；这构成可证实的冗余读取，但不能证明两个声学服务相互争抢 NAS。隔离 8 线程探针中，当前读取模式两轮为 **9.234/4.548 秒**，NAS 单遍流式复制并计算 SHA-256、复核本地副本为 **3.203/3.542 秒**；128/128 SHA 与预检记录相同，源大小和 mtime 前后相同。单 NVMe1 与 NVMe1/NVMe4 分流的单遍复制分别为 **2.716/2.853 秒**与 **2.986/2.606 秒**，未证明双盘更快。无可用声学秒坐标，本次未更改或发布 TextGrid/WAV，故无新边界审计结果；运行态产物状态不因探针改变。建议先采用一个有界 NVMe 快照，准备和候选发布共用，并保留源变化复核、旧产物归档、正式账本和原审计；尚需同一 2,000 源隔离 A/B、故障注入及正式落盘间隔监控，才能验证整线吞吐和发布安全。详细方法与限制见 `docs/superpowers/reports/2026-10-10-two-mfa-production-rollout.md`。

### JA-021 追加：2026-10-10 词典促音候选应用与正式定向重试

获用户批准后，将前述隔离候选精确应用到主工作树 `src/japanmfa/projection.py`，新增固定词典候选表 `src/japanmfa/mfa/dictionary_candidates.py` 和回归 `tests/unit/test_dictionary_geminate_fallback.py`。仅固定 `japanese_mfa_v3`、锁定读音与 G2P 读音一致、原候选全部不可映射、且 G2P 候选与固定词典读音恰好只差一个辅音长度符时补入 `オッパイ/マッタク/セッカク/カッテニ` 的完整候选；补入后仍须逐 mora 通过现有 map。错元音、错读音、原可映射候选及仍缺规则的 `ケッコウ` 保持原判。根因仍是生产 G2P 漏促音长度，不是重音解析器或 83 音素规则入口缺失。主工作树非真实模型回归 **1005 passed / 16 deselected**，`git diff --check` 通过；这些自动测试不是人工音素或重音金标。

切换前用 SQLite 在线备份保留正式账本 `.runtime/jobs/galgame-mfa-all/dictionary-geminate-rollout-20261010/progress-before.sqlite3`（SHA-256 `a09fafd8b5105706fb2cd99777d14914305019b06c9938496d06645e98ee91eb`）及旧代码/账本哈希回执 `before-receipt.json`。旧扫描器在新准备窗口 `79f6b0b72c634545b52671b8cd52fb86` 运行时收到停止信号，准备子进程终止，窗口留下失败工作目录；上一窗口 `d5435d9f685e4d0cbb5907f8ebbe6a9d` 的 2,000 条完整报告已提交，正式计数由备份时 **742,531 passed / 2,161,531 filtered** 到停止时 **743,312 passed / 2,162,750 filtered**。监督器按 `attention_required` 记录此次有意中断；未把未完成准备窗口计为成功。确认所有扫描、准备、声学子进程退出且 `job.lock`、`orchestration.lock` 均空闲后才应用代码；原未落账源仍可由续跑扫描器重新选取。原 NAS 成品中另抽 5 份，比对切换前账本 SHA、切换后账本 SHA 和当前文件 SHA，5/5 不变，见 `old-passed-spotcheck.json`。

正式定向重试源三联 `/mnt/Raw/JapGalgame/Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei/{wav,txt,ctc}/<stem>` 的 `CTS021067`（「全く。」）、`KRI000054_E01`（「ハルちゃん、おっぱい揉む？」）、`AME011031`（「私のオッパイ、私のバイズリ。」）、`KHK030714`（「でも、せっかくの約束だったのに。」）、`KRI060206`（前述长句）。五条旧账本均 `filtered/no_mappable_pronunciation`，旧正式 TextGrid 均不存在；旧诊断逐条保存在 `dictionary-geminate-rollout-20261010/before-targeted/`。正式批 `fce38a37698a4c2eacc92db0b765fb4a` 的报告在 `reports/`，结果 **1 passed / 4 filtered**：`AME011031` 正式 `/mnt/Raw/GalgameMFA/Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei/AME011031__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei.TextGrid` SHA-256 `5ae125b4a2831cc2f5af171970f76915750db2bbe02b902116403c39a39a9837`，配对原 WAV SHA-256 `ec6a3c5a7405a47992e67ea90c0b7ba7ddbd61fd434e7a2c7e318490d4e17cc5`；`/pː/` 自动区间 **1.31–1.53 秒**，`phone_kana=ッ|パ`、`phone_tone=LL`。对该一对真实 TextGrid/WAV 运行 `tools/audit_textgrid_pauses.py`，**1 files / 0 failed**，邻接停顿 0、标点边界不一致 0、可疑停顿声能 0，详见 `dictionary-geminate-rollout-20261010/audit.json` 与 `targeted-evidence.json`；这仍非人工确认的促音/重音真值。

其余 `CTS021067`、`KRI000054_E01`、`KHK030714`、`KRI060206` 都转为 `filtered/alignment_acoustic_coverage`，各无正式 TextGrid，不能把准备成功记成发布成功；`KRI060206` 原 WAV SHA-256 `0082be58ad1cba54b5fa6820c4dcf132d2a9cecf40f134d81a227a8e0862391e`，私有实验已给出 2.22–2.41 秒及 6.66–6.97 秒停顿内活动声能，见上段。四条的新旧诊断和正式报告均保留，声能/对齐问题仍需按原音频进一步处理。正式计数定向批后为 **743,313 passed / 2,162,749 filtered**。原未处理语料启动脚本重新启动，`run_unprocessed.py`、两个 MFA 常驻服务和准备服务恢复，正式账本锁重新持有；本次未批量重刷约 12 万条历史 `no_mappable_pronunciation`，更不能据 1 条通过宣称全部日语音素、重音或全语料已覆盖。后续覆盖统计应重新扫描当前正式成品并区分规则可达性、自动通过和人工语音真值。

**JA-031 追加：2026-10-10 10:31 UTC 单份 NVMe 快照应用与正式发布复核。** 根因中的可证实部分是同一 NAS WAV 在预检、快照和通过候选发布时被重复完整读取；是否还存在其他进程对 NAS 的并发争用，现有证据不能确认。经同源 2,000 条隔离 A/B，单遍复制和本地预检 139.15 秒，旧预检加复制 279.48 秒；每条 WAV/TXT/CTC SHA、时长与 CTC 词项数均一致。另以首个双服务批保留的 3 对真实 TextGrid/WAV 比较旧 NAS 路径与新快照路径的私有候选发布，输出 TextGrid/WAV SHA 3/3 相同、独立审计 3/3 通过。主工作树仅在 `JAPANMFA_NVME_SNAPSHOT_ROOT` 启用时从 NAS 单遍读取并验源，两个 MFA 服务及候选发布复用 NVMe1 上同一份快照；源变化拒绝、旧产物归档、正式账本与原审核门禁继续执行。切换前账本备份、旧 socket 清理和重启证据位于 `.runtime/jobs/galgame-mfa-all/nvme-snapshot-rollout-20261010/`。强制停止旧服务留下的三个无监听 socket 导致第一次重启失败；确认无监听进程后仅删除三个旧 socket，第二次重启恢复三个服务和扫描器，期间无错误新批发布。

新正式批 `b7445160c96e47ecbffeff3dc0749526` 和 `ff2b9b6c39c043bb88194961f769f677` 各 2,000 源，分别为 207/1,793 与 193/1,807 passed/filtered；**400/400** 份通过的 `/mnt/Raw/GalgameMFA/<game>/<stem>.TextGrid` 均与完整报告、SQLite 账本及 NAS 实际 SHA 一致，0 缺失、0 状态或哈希冲突。每批抽 12 份配 `/mnt/Raw/JapGalgame/<game>/wav/<stem>.wav` 运行 `tools/audit_textgrid_pauses.py`，均 **12 files / 0 failed**，回执 `first-batch-check.json`、`second-batch-check.json` 及对应 `*-batch-audit.json`。后续 `cabedaa5bf074320b4cf076a28400939`、`aef3689ce42644e384a39e8eed53eaff` 分别 187/1,813、284/1,716，账本各 2,000 行，成功快照均已清理；这两批未逐文件重新哈希，不能混同前两批的完整核对。四批候选发布时间为 3.35、2.80、2.81、4.56 秒；正式报告连续间隔 210.66、181.06、201.35 秒，中位 201.35 秒，相比旧双服务 310.4 秒的短窗口中位间隔，观察批次吞吐约高 54.2%。这是不同输入和时间的生产对照，不能保证长期同速或把全部差额归因于快照。未重新评估音素秒坐标；自动暂停/标点/声能审计不是人工音素边界真值。仍需持续监控 NAS 输入波动、正式落盘间隔和失败快照的容量占用；失败或缺失 TextGrid 一律保持失败状态。

**JA-026/JA-023、JA-021、JA-033 复发审计（2026-10-10 11:14 UTC，只读设计）：** NVMe 快照后连续 17 个正式 2,000 源批次，34,000 条中 3,486 passed、30,514 filtered；覆盖失败 27,993（filtered 的 91.74%），时间戳冲突 1,270、映射失败 1,001、非支持文本 138、BGM 55、缺少 MFA 输出 13。全批报告路径和分析见 [当前过滤分析与修复设计](superpowers/reports/2026-10-10-current-filter-analysis.md)。同根因声学复发样本 `/mnt/Raw/JapGalgame/Jitaku_Studio_Real_Eroge_Situation/{wav,txt,ctc}/ayame02_1140__Jitaku_Studio_Real_Eroge_Situation`：CTC「お」1.28–3.52 秒，重试后 MFA 1.59–3.53 秒为停顿，其内 1.72–2.15、2.19–2.68、2.74–3.03 秒有活动；`nazuna02_0519` 的 CTC「見届ける」2.72–3.04 秒，MFA 3.04–3.28 秒停顿内 3.12–3.28 秒仍有活动。两者尚不能只凭 CTC 或声能判断音素归属，继续正式 filtered。`kanna02_3033` 在 CTC 第一词 1.84 秒前的 0.57–0.77 秒有活动，需听辨是否为文本外声音，不能自动延长词界。映射样本 `Jitaku_Studio_Real_Eroge_Situation_2/fem_chi_00352__Jitaku_Studio_Real_Eroge_Situation_2` 的「モッタイ」缓存候选 `[m,o,t,a,i]` 无促音长度，仍应拒绝；固定种子抽 50 条映射失败，用每个读音最新可用缓存候选重放现行规则，50 条仍失败，39 条失败读音含「ッ」只是分诊线索，探针没有逐条锁定原批次 adapter identity。根因已证实部分为源锚点与 MFA 暂停几何冲突、以及该候选缺促音；声音是台词或音效、其它映射词的正确候选仍待听辨和词典核对。修复设计为先保留多标签诊断，再分层做可信文本修正或局部重对齐，精确补全有证据的候选，最后隔离复跑同一声学门禁。此次没有改生产代码或发布产物；无新的最终 TextGrid/WAV 可审计，缺失项仍按失败。自动声能与 CTC 不是人工音素金标。

**JA-026 追加：0.2 秒时间阈值与能量词尾延长（2026-10-12，离线复核）。** 四个归档正式批次共 8,000 源、7,517 条可用 timed 证据；从最终音素归属重算 `>0.2 s` 问题，与留存审核结果 7,517/7,517 一致。在其中 1,332 条有直接 timed 证据的正式通过样本上，若把审核阈值改为 `0.15/0.1 s`，会比当前 `0.2 s` 分别多标记 207/398 条，不能由此得出多标记者边界错误。7,517 份中原始无时间问题而后处理后出现问题的 1,513 条，1,465 条同时有 `>0.1 s` 的 `energy_tail_extension`；这只是样本级关联。具体复现归档 `.runtime/jobs/galgame-mfa-all/batch-evidence/010edb3d598249c0bc2cb704721e7f54/run/pipeline-timed/u08f55853e9bb4063607adb49/postprocess.json`，源 `/mnt/Raw/JapGalgame/BaseSon_Shin_Koihime_Musou_Kakumei_Souten_no_Haou/wav/AC_sn_b_syn10+_094__BaseSon_Shin_Koihime_Musou_Kakumei_Souten_no_Haou.wav`：`/e/` 原尾 `8.45 s`、CTC 尾 `8.48 s`、能量延长后尾 `8.79 s`；原差 `-0.03 s` 变最终 `+0.31 s`，终态 `timestamp_mfa_disagreement`。内存几何试验显示简单还原 `8.45 s` 留约 30 ms 活动尾声并触发暂停可疑，`8.48–8.52 s` 候选同时满足时间及局部暂停自动审核。另一已通过对照 `u08204c9c9963d2b2e8a14aba` 的 `1.95–2.08 s` 强活动声段与迟至 `2.08 s` 的 CTC 词首相冲，说明不能全局按 CTC 裁剪或简单收紧阈值。已证实根因之一是能量词尾延长缺少 CTC/最终时间审核约束；具体每段是否属于词尾、CTC 是否准确仍待人工听辨。拟保留 `0.2 s` 正式门禁，给 `>0.1 s` 加诊断标记，仅对明确由词尾延长造成的新冲突生成受声能与时间双门禁的局部候选。完整试验口径、对照和验收见 [离线试验报告](superpowers/reports/2026-10-12-timing-threshold-postprocess-probe.md)。本次未修改生产代码、服务或正式成品；没有新 TextGrid/WAV 可供独立发布审计，样本仍按原失败状态，自动检查不代表人工音素真值。

**JA-026 同根因补充：放宽阈值的反向检验（2026-10-12）。** 同四批 7,517 份后处理证据中，465 条阶段性 `timestamp_mfa_disagreement` 在保持其它审核原样、仅将时间阈值从 `0.2 s` 改为 `0.25/0.3/0.35/0.4 s` 的反事实计算下，分别有 66/142/210/293 条不再因时间门禁失败；其中 54/121/181/264 条伴随 `>0.1 s` 的 `energy_tail_extension`，只是关联。`0.35 s` 会放行上段 `u08f55853e9bb4063607adb49` 的 `8.79 s` 词尾，尽管其 `8.48–8.52 s` 有更接近 CTC 且局部暂停审核通过的候选。放宽可降低拒绝数，但不能据此确认词界正确；可能掩盖过度延长，也可能救回 CTC 错位的真语音，仍需逐类声学与人工听辨。反向试验表及具体口径见同一[离线试验报告](superpowers/reports/2026-10-12-timing-threshold-postprocess-probe.md)。无生产改动或新发布，当前失败样本仍记失败。

**JA-023/JA-026 同类失败的人工检查导出（2026-10-13 04:23 UTC）。** 按正式 SQLite 当前 `filtered/alignment_acoustic_coverage` 和归档 `pipeline-timed/<alias>/postprocess.json` 同时确认，从 `010edb3d598249c0bc2cb704721e7f54`、`caaf8141c95d4e8abb73af6c62afb63a` 两批选取 10 条：BaseSon 与 GIGA 各 5 条，6 条静音边缘活动、4 条停顿内部声岛。原始源 `/mnt/Raw/JapGalgame/<game>/wav/<stem>.wav` 与归档最终音素边界重建成**拒绝候选诊断** TextGrid/WAV，复制至 `/mnt/Raw/1013/acoustic_coverage_failed_10/`；这个已验证的 CIFS 挂载源是 `//192.168.102.202/Research_TTS/Data/Raw`，本机将用户给的 `RS3621` 解析为本机 `192.168.102.108` 且无 SMB 服务，因此**尚不能确认按主机名访问的是同一共享**，已请求路径确认。原产物未覆盖，逐文件 SHA-256 与本地暂存相同，源 WAV SHA、TextGrid SHA、源 key/批次/正文/可疑活动区间均在 `manifest.json`，易读索引在 `review.csv`，显式标记 `NOT_FOR_PUBLICATION`。坐标例：`01_u002460d410a39d2b05c7141c` 对应 `BaseSon_Shin_Koihime_Musou_Kakumei_Souten_no_Haou/AC_sn_b_syn11+_097__BaseSon_Shin_Koihime_Musou_Kakumei_Souten_no_Haou`，可疑暂停 `0.00–1.96 s`；`04_u01fff836d342ca9bf5a5873a` 对应同游戏 `AD_sn_b_keif05_030`，`1.12–3.25 s`；`06_u00650d7ef3e875ce869f1d26` 对应 `GIGA_Kiss_Bell/02021756__GIGA_Kiss_Bell`，`0.59–1.77` 与 `1.89–4.63 s`；`09_u00d4943641c594f96330e5b6` 对应 `GIGA_Kiss_Bell/02030932__GIGA_Kiss_Bell`，`5.43–5.56` 与 `5.97–6.03 s`。全 10 条可疑段、原始音频及哈希见索引。原因目前只确定**最终暂停内检测到活动声能**；这些声音属于漏标台词、错位词、音效或 BGM，须人工听辨，不能凭声能定性，也未修改词界作为“修复”。`tests/unit/test_export_filtered_diagnostics.py`、`test_output_textgrid.py`、`test_pause_audit.py` 共 20 项通过；对十对诊断文件运行 `tools/audit_textgrid_pauses.py` 得 `10 files / 10 failed`（预期：每条至少一个声学可疑暂停），结构错误、相邻停顿和跨轨标点冲突均为 0，明细在 `audit.json`。剩余范围为逐条听辨并决定文本修订、重对齐或维持过滤；十条均未转正式通过，缺失或审核失败不得算发布成功。
