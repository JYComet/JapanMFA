# JapanMFA 日语五轨强制对齐管线设计

日期：2026-09-22  
状态：已由用户逐节确认，待实施计划

## 1. 目标

JapanMFA 是一个全新的、仅处理日语的强制对齐项目。第一版将给定音频与日文文本转换成五轨 Praat TextGrid，并把 tdmelodic 生成的音拍级东京式高低重音投影到每个 MFA 音素区间。

五条输出轨道固定为：

1. 完整原文；
2. 完整锁定假名；
3. MFA 音素；
4. 按 MFA 音素边界投影的辅助假名；
5. 按 MFA 音素边界投影的 H/L 重音。

第一版以“先可靠跑通纯日语端到端管线”为目标。日英混合、上下文变调和高级质量筛选明确留待后续版本。

## 2. 仓库和环境隔离

- 本地仓库：`/home/user/JapanMFA`
- 远程仓库：`https://github.com/JYComet/JapanMFA.git`
- 默认分支：`main`
- 仓库通过 `git init` 创建，从零开始，不继承 `ASRMFA--Pure` 的提交历史。
- 不导入、修改或依赖 `/home/user/JapMFA` 中的项目源码。
- 可以重新实现已验证的算法思想，但必须在新仓库中拥有独立实现、测试和文档。
- Python 环境、MFA 环境、ASR 环境、模型缓存、临时目录和输出目录均使用 JapanMFA 专属路径。
- 真实测试语料以只读方式访问；任何转换后的音频和中间产物都写入项目输出目录。

设计确认时，旧仓库位于 `codex/ja-en-full-pipeline`，提交为 `55208b4e10cd2f163c1d9116b0502709d41ab656`。新项目实施和验收不得改变该仓库状态。

## 3. 支持范围

### 3.1 第一版支持

- 单条音频处理；
- 目录递归批处理；
- 同名 `.wav`/`.txt` 输入；
- 缺少 `.txt` 时使用 Qwen3-ASR 生成候选文本；
- 存在 `.txt` 时使用 Qwen3-ASR 做校验，但不得自动改写权威文本；
- SudachiPy 分词和默认读音；
- 逐次出现的人工读音覆盖；
- tdmelodic `sy2a(surface, yomi)` 逐词重音推断；
- Japanese MFA v3 音素强制对齐；
- 五轨 TextGrid、结构化 JSON、批次清单和汇总报告；
- 分阶段缓存、可恢复运行和单条失败隔离。

### 3.2 日文可处理性判定

允许汉字、平假名、片假名、日文标点，以及能够规范化成稳定日语读音的数字。拉丁字母、未知符号或任何不能稳定转换成假名的词元会使整条音频标记为 `skipped`。

这是“能否生成确定日语读音”的判定，不是单纯的 Unicode 字符块检查。强制 ASR 使用日语并不能证明语音本身是日语，因此 ASR 输出仍需经过相同的词元与读音校验。

## 4. 总体数据流

```text
.wav + 可选 .txt
        │
        ├── Qwen3-ASR（日语锁定；校验或缺失文本回退）
        ↓
SudachiPy 分词、默认读音和日文可处理性校验
        ↓
按原文位置应用人工覆盖，锁定最终假名
        ↓
假名音拍切分
        ↓
tdmelodic sy2a 逐词生成音拍级 H/L
        ↓
Japanese MFA G2P 生成唯一发音
        ↓
逐词次唯一别名 + 单发音临时词典
        ↓
Japanese MFA v3 强制对齐
        ↓
音拍—音素映射及 H/L 广播
        ↓
五轨 TextGrid + JSON + 批次报告
```

Qwen3-ASR、tdmelodic 和 MFA 各自只有一个职责。Qwen3-ASR 不提供最终时间边界，tdmelodic 不决定最终读音，MFA 不选择候选读音。

## 5. 输入契约

输入目录可递归包含说话人或其他子目录：

```text
corpus/
├── speaker_a/
│   ├── 001.wav
│   ├── 001.txt
│   └── 002.wav
└── speaker_b/
    ├── 003.wav
    └── 003.txt
```

- 每个 `.wav` 是一个话语。
- 同名 `.txt` 为 UTF-8 编码的权威文本。
- 缺少 `.txt` 并非立即失败，而是触发 ASR 回退。
- 重复基名通过相对路径形成唯一话语 ID，例如 `speaker_a/001`。
- 输入目录只读。
- 音频转换只对工作副本进行，并记录原始采样率、声道、时长和转换参数。

## 6. Qwen3-ASR

第一版仅实现本地 Qwen3-ASR 后端：

- 默认模型：`Qwen/Qwen3-ASR-1.7B`；
- 资源不足时允许配置：`Qwen/Qwen3-ASR-0.6B`；
- 识别语言显式设为 `Japanese`，不使用自动语言选择；
- 有 `.txt` 时，ASR 输出只用于报告差异；
- 无 `.txt` 时，ASR 输出是候选原文，必须通过日文可处理性校验；
- 不加载 Qwen3 Forced Aligner，最终时间边界始终来自 MFA；
- `asr.json` 保存模型、版本、语言设置、输出文本、文本来源和校验结果。

Qwen 官方仓库说明 Qwen3-ASR 支持日语，并提供 0.6B、1.7B 和独立 Forced Aligner：<https://github.com/QwenLM/Qwen3-ASR/>

## 7. 日文前端和读音锁定

### 7.1 规范化与分词

- 原始文本原样保留给 `original` 轨和审计记录。
- 处理副本进行 Unicode NFC 规范化。
- SudachiPy 使用 `SplitMode.B`。
- 每个词元保存原文字符范围、表记、词性、默认读音和读音来源。
- 标点保留在原文和结构化数据中，但不作为发音词元。

MFA 当前日文分词实现同样基于 SudachiPy `SplitMode.B`：<https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner/blob/main/montreal_forced_aligner/tokenization/japanese.py>

### 7.2 人工读音覆盖

读音覆盖使用 YAML，并以话语 ID、原文字符范围和预期表记共同定位一次具体出现：

```yaml
utterances:
  speaker_a/001:
    readings:
      - span: [4, 6]
        surface: "今日"
        kana: "キョウ"
```

应用覆盖前必须检查：

- 字符范围合法；
- 该范围的原文与 `surface` 完全一致；
- `kana` 能规范化成有效片假名读音。

任一检查失败时整条话语为 `failed`，不得把覆盖悄悄应用到其他位置。

### 7.3 完整假名

最终锁定读音以规范化片假名保存。`kana` TextGrid 轨使用完整、可读的锁定假名，不暴露 MFA 唯一别名。标点可按原始相对位置保留在显示形式中；JSON 另存不含标点的逐词元和连续发音形式。

## 8. 音拍切分

每个词的锁定读音转换成有序音拍：

- 普通片假名通常各自形成一个音拍；
- 小写 `ャュョ` 及适用的小元音与前一字符组成一个音拍；
- `ッ`、`ン`、`ー` 分别形成独立音拍；
- 未覆盖的组合或不能唯一切分的读音导致显式失败。

每个音拍保存词元索引、词内音拍索引、字符范围和规范化假名，以便从最终音素反向追踪。

## 9. tdmelodic 重音

### 9.1 调用规则

- 每个词元单独调用 `sy2a(surface, yomi)`；
- `yomi` 来自已经锁定的读音；
- 不使用 `s2ya` 重新预测或覆盖读音；
- 不使用句子级推断作为第一版结果。

tdmelodic 官方文档说明 `sy2a` 接收表记和指定读音来推断重音，并提醒句子重音并非其主要训练目标：<https://github.com/PKSHATechnology-Research/tdmelodic/blob/master/docs/pages/onebyone.rst>

### 9.2 输出校验和 H/L 解析

1. 解析 `[` 和 `]` 为音拍边界事件；
2. 删除重音标记后的读音必须与锁定读音在允许的平假名/片假名规范化后相同；
3. `[` 表示其后音拍进入 H；
4. `]` 表示其后音拍进入 L；
5. 若首个音高事件为下降，则首音拍从 H 开始，否则从 L 开始并在上升事件后转为 H；
6. 每个音拍必须恰好获得一个 H 或 L；
7. 无法解析、音拍数不一致或读音不一致均为 `failed`，不得猜测。

原始 tdmelodic 输出、规范化输出、边界事件和最终音拍 H/L 全部写入 `frontend.json`。

## 10. MFA 锁定发音与对齐

Japanese MFA v3 的日文流程会对正常日文做分词和片假名 G2P。为了既锁定读音又保留逐词次身份，管线采用两阶段方法：

1. 将每个锁定片假名词元交给官方 Japanese MFA G2P，得到与声学模型兼容的唯一音素串；
2. 校验每个词元只选定一个发音；
3. 把词典词项替换成逐词次唯一的安全 ASCII 别名；
4. 生成仅包含这些别名和单一发音的临时词典；
5. 临时转录只包含按顺序排列的别名；
6. 使用临时词典和 Japanese MFA v3 声学模型执行对齐，不再对别名启用日文分词；
7. 对齐后依据别名恢复原词元、读音和音拍。

此设计避免把 ASCII 别名误送入日文分词器，也禁止 MFA 为同形词选择其他读音。MFA 官方示例说明日文对齐可使用 `japanese_mfa` G2P 和声学模型：<https://github.com/montrealcorpustools/montreal-forced-aligner/blob/main/docs/source/first_steps/alignment_example.md>

MFA 执行前进行语料、词典和模型验证。日志、原始 MFA TextGrid、生成词典、临时转录和对齐统计均保留在话语的 `mfa/` 诊断目录。

## 11. 音拍到音素的映射

- 使用与固定 Japanese MFA 模型版本对应的版本化音素映射表；
- 将每个词元的预期 G2P 音素串与 MFA 实际输出逐词校验；
- 一个音拍对应多个音素时，每个音素继承该音拍的 H/L；
- 同一音拍的辅助假名可在组成音素上重复；
- 静音、短停顿和非语音区间不分配假名或重音；
- 漏音素、多余音素、词边界错位或无法唯一解释的映射导致该话语失败。

若一个 MFA 音素覆盖多个音拍，则不得伪造音素内部时间边界：

- 假名轨使用有序组合，例如 `オ|ー`；
- 重音轨使用有序组合，例如 `H|L` 或 `L|H`；
- JSON 保存组成音拍及其顺序。

## 12. 五轨 TextGrid 契约

最终 TextGrid 固定包含且仅包含以下五个 `IntervalTier`：

| 顺序 | 名称 | 时间结构 | 标签 |
|---:|---|---|---|
| 1 | `original` | 单一区间覆盖完整音频 | 原始完整文本 |
| 2 | `kana` | 单一区间覆盖完整音频 | 完整锁定假名 |
| 3 | `phones` | MFA 音素区间 | MFA 原始音素，含静音 |
| 4 | `phone_kana` | 与 `phones` 逐项相同 | 音素对应的辅助假名 |
| 5 | `phone_tone` | 与 `phones` 逐项相同 | `H`、`L` 或有序组合 |

三个音素级轨道必须满足：

- 区间数量完全相同；
- 每个区间的 `xmin`、`xmax` 完全相同；
- 每个非静音音素的 `phone_kana` 非空；
- 每个非静音音素的 `phone_tone` 非空；
- 静音区间的 `phone_kana` 和 `phone_tone` 为空。

MFA 浮点边界直接保留，不重新取整、不均分、不根据假名人为修正。原文轨和假名轨不按词或音素拆分。

## 13. 输出契约

每条成功话语生成：

```text
output/speaker_a/001/
├── 001.TextGrid
├── alignment.json
├── frontend.json
├── asr.json
└── mfa/
```

批次级输出包括：

- `manifest.jsonl`：每条话语的阶段、状态和原因；
- `summary.json`：成功、跳过、失败数量及原因统计；
- `resolved_config.yaml`：最终配置、依赖版本、模型和路径；
- 带 `run_id` 的运行元数据及阶段耗时。

状态定义：

- `aligned`：五轨和 JSON 全部通过结构与语义校验；
- `skipped`：已知不支持的输入，例如非日文或无可靠读音；
- `failed`：支持范围内出现执行或一致性错误。

不得生成“部分成功”的最终 TextGrid。失败或中断时，中间诊断文件可以保留，但不会被标记为最终结果。

## 14. 质量验证

成功输出至少通过：

- 边界单调、不重叠且位于音频时长内；
- MFA 词别名顺序与前端词元顺序一致；
- 实际音素序列与锁定 G2P 序列一致；
- 每个实际音素可追踪到词元、锁定读音、音拍和 tdmelodic 输出；
- 音拍数与 H/L 数相同；
- 三条音素级轨道结构完全同构。

MFA 似然、音素时长异常、静音比例和 ASR/权威文本差异先作为报告指标保存。第一版在没有真实语料统计基线前不设置任意的自动淘汰阈值。

## 15. CLI

预期命令：

```bash
japanmfa check --config configs/default.yaml

japanmfa run \
  --input /mounted/0922jap \
  --output /path/to/output \
  --config configs/default.yaml \
  --overrides readings.yaml

japanmfa run-file audio.wav \
  --text transcript.txt \
  --output output/

japanmfa inspect output/manifest.jsonl
```

`check` 在运行前验证外部命令、模型、GPU/CPU 能力、可写输出路径及版本兼容性。

## 16. 代码结构

```text
JapanMFA/
├── pyproject.toml
├── environment.yml
├── configs/default.yaml
├── src/japanmfa/
│   ├── cli.py
│   ├── pipeline.py
│   ├── corpus.py
│   ├── config.py
│   ├── models.py
│   ├── asr/qwen3.py
│   ├── frontend/sudachi.py
│   ├── frontend/overrides.py
│   ├── frontend/mora.py
│   ├── accent/tdmelodic.py
│   ├── accent/parser.py
│   ├── mfa/g2p.py
│   ├── mfa/lexicon.py
│   ├── mfa/runner.py
│   ├── mfa/parser.py
│   ├── projection.py
│   ├── output/textgrid.py
│   └── output/reports.py
├── tests/
└── docs/
```

运行环境分层：

- `japanmfa`：编排、SudachiPy、音拍/重音映射、TextGrid 和报告；
- `japanmfa-mfa`：MFA 和 Japanese MFA v3 模型；
- `japanmfa-asr`：Qwen3-ASR GPU 运行时；
- tdmelodic：优先使用独立容器或隔离命令环境。

编排器通过严格的标准输入/输出适配器调用外部工具。模型路径、命令、版本和资源参数均由配置提供，不写死进业务代码。

## 17. 缓存、恢复和文件安全

- 每个阶段根据音频内容、文本、读音覆盖、配置和模型版本计算指纹；
- 指纹一致的已完成阶段可以复用；
- 上游变化只使相应下游缓存失效；
- 结果先写入话语专属临时目录，验证后原子发布；
- 单条失败不阻断其他话语；
- `--force` 只能覆盖当前话语自己的 JapanMFA 输出；
- 不提供针对任意用户目录的递归清理操作；
- 模型和工具缓存不能指向旧项目目录。

## 18. 测试策略

实现遵循测试驱动开发：先添加失败测试，再实现最小功能，最后重构。

### 18.1 单元测试

- Unicode 与日文可处理性判定；
- Sudachi 词元模型；
- 按字符范围应用读音覆盖；
- 普通假名、拗音、促音、拨音和长音的音拍切分；
- tdmelodic 标记解析和读音一致性检查；
- 音拍 H/L 到音素的广播；
- 多音拍长音素的组合标签；
- 五轨 TextGrid 结构验证。

### 18.2 契约和集成测试

- Qwen3-ASR、tdmelodic 和 MFA 适配器的命令契约；
- 锁定假名到 Japanese MFA G2P；
- 唯一别名词典和临时转录；
- 小型音频端到端对齐；
- 缺失模型、工具退出失败和中断恢复；
- 非日文整条跳过且保留原因。

外部大型模型测试必须有明确标记，普通单元测试不得因为没有 GPU 或模型缓存而失败。

## 19. 真实语料验收

验收语料：`\\RS3621\Research_TTS\Data\Raw\0922jap`。

运行前解析并记录实际 Linux 挂载路径，保持源目录只读。验收标准：

- 每个扫描到的音频恰好得到 `aligned`、`skipped` 或 `failed`；
- 单条异常不终止批处理；
- 每个 `aligned` 音频具有通过验证的五轨 TextGrid 和完整 JSON；
- 每个非静音音素具有可追溯的重音；
- 汇总成功率、跳过原因、失败原因和阶段耗时；
- 抽取代表性结果进行 Praat 可视化检查；
- 将环境、命令、统计、样例和发现的问题写入 `docs/test-report-0922jap.md`；
- 验证旧 `/home/user/JapMFA` 仓库分支、提交和工作区未被修改。

## 20. 已知限制和后续优化

第一版不实现：

- 日英混合、纯英文和自动语言切换；
- 复合词、短语和句子级重音变调；
- 跨词连读、助词附着和语境消歧；
- 平板型与尾高型在孤立词 H/L 序列之外的上下文差异；
- MFA 声学模型自适应训练；
- 基于真实语料统计的自动质量淘汰阈值；
- 用 ASR 自动覆盖已有权威文本；
- 用 Qwen3 Forced Aligner 替代 MFA；
- 为跨多个音拍的 MFA 音素伪造内部边界；
- 人工校订 GUI 或交互式 TextGrid 编辑器；
- 长录音自动切句、说话人分离和多说话人录音。

上述项目必须在 `docs/limitations.md` 中持续维护。实现过程中遇到但未覆盖的新读音、音拍、MFA 音素或 tdmelodic 输出形式也必须记录，不能通过静默回退隐藏。

## 21. 必需文档

- `README.md`
- `docs/architecture.md`
- `docs/input-output.md`
- `docs/reading-overrides.md`
- `docs/accent-mapping.md`
- `docs/limitations.md`
- `docs/test-report-0922jap.md`
- 可复现的安装、模型准备、环境检查和运行说明

## 22. 完成定义

第一版只有在以下条件全部成立时才算完成：

1. 新仓库具有独立、可审计的干净 Git 历史；
2. 单元测试和不依赖大型模型的契约测试全部通过；
3. 至少一个真实日语话语完成 Qwen 校验、读音锁定、tdmelodic、MFA 和五轨导出；
4. `0922jap` 批次完成扫描和分类，并产出测试报告；
5. 每个成功结果通过五轨结构与音素重音完整性检查；
6. 所有未实现、未覆盖或暂时不可靠的情况记录在限制文档中；
7. 旧 `JapMFA`/`ASRMFA--Pure` 仓库未被修改；
8. 最终实现经过代码审查和完成前验证。
