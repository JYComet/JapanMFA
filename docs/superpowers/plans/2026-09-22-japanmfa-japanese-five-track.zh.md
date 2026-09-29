# JapanMFA 日语五轨管线实现计划

> **面向自动化执行者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现本计划。用复选框（`- [ ]`）语法跟踪进度。

**目标：** 构建一条独立的、仅面向日语的管线：锁定假名读音，用 tdmelodic 预测音拍的高/低（H/L），用日语 MFA v3 对齐音素，并导出经过校验的五层 TextGrid 以及审计报告。

**架构：** 一个体量很小的 Python 编排器负责语料发现、不可变领域记录、校验、缓存、投影与输出。Qwen3-ASR、tdmelodic 和 MFA 都以子进程适配器的形式运行在相互隔离的运行时中；数据以 JSON、按行组织的文本、词典文件和 TextGrid 文件的形式跨越这些边界。每一条成功的话语，都有一条可追溯的路径：从源文本，经由锁定的音拍，到最终的 MFA 音素区间。

**技术栈：** Python 3.11、hatchling、Typer、PyYAML、SudachiPy + sudachidict-core、praatio、pytest、Qwen3-ASR 1.7B/0.6B、Montreal Forced Aligner 3.x 配合日语 MFA v3 模型、tdmelodic、FFmpeg。

**规格说明：** `docs/superpowers/specs/2026-09-22-japanmfa-japanese-five-track-design.md`

## 全局约束

- 只在新的 `JapanMFA` 仓库内工作；不得修改或从 `/home/user/JapMFA` 导入源码。
- `main` 保持基于干净的根提交 `7a4f7ca`；特性开发在隔离的 `codex/` 分支/工作树中执行。
- 首个版本仅支持日语。任何不受支持的非日语话语一律标记为 `skipped`（跳过），绝不进行部分对齐。
- `.txt` 存在时即为权威来源。Qwen3-ASR 对它做校验；只有当 `.txt` 缺失时，ASR 才提供候选文本。
- Qwen3-ASR 锁定为 `Japanese`；默认模型为 `Qwen/Qwen3-ASR-1.7B`，可配置为 `Qwen/Qwen3-ASR-0.6B`。
- SudachiPy 的 `SplitMode.B` 提供默认读音；按出现位置（per-occurrence）的 YAML 覆盖用于锁定修正结果。
- tdmelodic 只通过逐 token 的 `sy2a(surface, yomi)` 调用，且不得替换已锁定的读音。
- 日语 MFA v3 是唯一的时间边界权威；不使用 Qwen Forced Aligner。
- 最终 TextGrid 恰好包含 `original`、`kana`、`phones`、`phone_kana`、`phone_tone` 五层，且顺序如上。
- `original` 与 `kana` 各包含一个覆盖全时长的区间。后三层的区间数量与边界必须完全一致。
- 每个非静音音素都必须有非空的假名与声调标签。多音拍音素使用有序标签，例如 `オ|ー` 与 `H|L`。
- 输入语料保持只读。临时产物与最终产物都位于 JapanMFA 自有的 output/cache 目录下。
- 所有实现工作遵循 TDD，且每个任务以针对性测试加一次逻辑提交收尾。

## 评审关注点

- UTF-8 BOM、行尾换行和多行 `.txt` 必须被确定性地归一化，且不得改变所保存的原始文本；任务 2 用测试固定该行为。
- 强制日语识别后仍含拉丁字母或无法发音 token 的 ASR 结果，必须 `skipped`，不得送入 MFA；任务 3 与任务 4 用测试固定该行为。
- 不同说话人目录下的同名文件，以及大小写折叠导致的冲突，必须保留彼此不同的稳定话语 ID，否则必须清晰地使发现阶段失败；任务 2 用测试固定该行为。
- 含 `sil`、`sp`、`spn`、空区间或零时长区间的 MFA TextGrid，必须在不移动相邻边界的前提下被分类与校验；任务 7 用测试固定该行为。
- tdmelodic 的畸形方括号，以及单个 MFA 长音素跨越不同声调音拍的情况，必须失败，或在不臆造边界的前提下产出有序复合标签；任务 5 与任务 8 用测试固定该行为。

---

## 计划的文件结构

```text
pyproject.toml                         包元数据、依赖、CLI 入口
.gitignore                             生成的产物、模型、缓存、环境
environment.yml                        编排器环境
environments/mfa.yml                   隔离的 MFA 环境
environments/asr.yml                   隔离的 Qwen3-ASR 环境
configs/default.yaml                   默认模型、命令、路径、校验设置
src/japanmfa/domain.py                 不可变的跨阶段领域记录与枚举
src/japanmfa/errors.py                 有类型的预期管线错误
src/japanmfa/config.py                 YAML 配置加载与校验
src/japanmfa/corpus.py                 语料发现与源文本加载
src/japanmfa/audio.py                  只读音频探测与 FFmpeg 工作副本
src/japanmfa/asr/qwen3.py              Qwen 子进程客户端与响应校验
src/japanmfa/asr/worker.py             Qwen 运行时 JSONL worker
src/japanmfa/frontend/japanese.py      Sudachi 分词与支持性判定
src/japanmfa/frontend/overrides.py     按跨度（span）寻址的读音覆盖
src/japanmfa/frontend/mora.py          假名归一化与音拍切分
src/japanmfa/accent/tdmelodic.py       批量 sy2a 命令适配器
src/japanmfa/accent/parser.py          方括号重音标记到音拍 H/L 的解析器
src/japanmfa/mfa/g2p.py                日语 MFA G2P 命令适配器
src/japanmfa/mfa/lexicon.py            出现位置别名、转写、锁定词典
src/japanmfa/mfa/runner.py             MFA validate/align 调用
src/japanmfa/mfa/textgrid.py           原始 MFA word/phone 层解析器
src/japanmfa/projection.py             词/音拍/音素的调和与 H/L 投影
src/japanmfa/output/textgrid.py        最终五层写出器与校验器
src/japanmfa/output/reports.py         逐话语与批量的 JSON/JSONL 报告
src/japanmfa/cache.py                  内容指纹与阶段产物的原子发布
src/japanmfa/pipeline.py               阶段编排与结果隔离
src/japanmfa/checks.py                 运行时/模型/预检检查
src/japanmfa/cli.py                    Typer 命令
tools/build_tdmelodic_image.sh         可复现的隔离 tdmelodic 构建包装脚本
tests/unit/...                         纯单元测试
tests/contract/...                     使用假可执行文件的外部命令契约测试
tests/integration/...                  需显式开启的模型/音频集成测试
tests/fixtures/...                     极小的文本、JSON、词典与 TextGrid 夹具
docs/architecture.md                   运行时与数据流文档
docs/input-output.md                   语料、五层结构与报告契约
docs/reading-overrides.md              覆盖文件的编写与校验
docs/accent-mapping.md                 tdmelodic/音拍/音素映射规则
docs/limitations.md                    明确不受支持与未覆盖的行为
docs/test-report-0922jap.md            真实语料证据与发现
```

### 任务 1：包骨架、领域记录与配置

**文件：**
- 新建：`pyproject.toml`
- 新建：`.gitignore`
- 新建：`src/japanmfa/__init__.py`
- 新建：`src/japanmfa/domain.py`
- 新建：`src/japanmfa/errors.py`
- 新建：`src/japanmfa/config.py`
- 新建：`configs/default.yaml`
- 测试：`tests/unit/test_config.py`
- 测试：`tests/unit/test_domain.py`

**接口：**
- 产出：`PipelineConfig.load(path: Path) -> PipelineConfig`
- 产出：`Utterance`、`SourceText`、`Token`、`Mora`、`Pronunciation`、`PhoneInterval`、`PhoneAnnotation`、`UtteranceOutcome`
- 产出：`OutcomeStatus = aligned | skipped | failed`，以及有类型的 `SkipUtterance` / `StageFailure`

- [ ] **步骤 1：编写会失败的配置与领域测试**

```python
def test_default_config_locks_required_models(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  model: Qwen/Qwen3-ASR-1.7B\n  language: Japanese\n"
        "mfa:\n  acoustic_model: japanese_mfa\n  g2p_model: japanese_mfa\n"
        "audio:\n  sample_rate: 16000\n",
        encoding="utf-8",
    )
    config = PipelineConfig.load(path)
    assert config.asr.language == "Japanese"
    assert config.mfa.acoustic_model == "japanese_mfa"


def test_phone_interval_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="end must be greater"):
        PhoneInterval(start=1.0, end=1.0, label="a")
```

- [ ] **步骤 2：运行针对性测试，确认收集/导入失败**

运行：`pytest tests/unit/test_config.py tests/unit/test_domain.py -q`
预期：失败，因为 `japanmfa.config` 与 `japanmfa.domain` 尚不存在。

- [ ] **步骤 3：添加包元数据与不可变领域记录**

使用 Python 3.11、hatchling、`src/` 布局，CLI 入口点为 `japanmfa = "japanmfa.cli:app"`。用冻结 dataclass 定义以下稳定字段：

```python
@dataclass(frozen=True)
class Utterance:
    utterance_id: str
    audio_path: Path
    text_path: Path | None

@dataclass(frozen=True)
class SourceText:
    original: str
    processing: str
    source: Literal["txt", "asr"]

@dataclass(frozen=True)
class Token:
    index: int
    start: int
    end: int
    surface: str
    part_of_speech: tuple[str, ...]
    reading: str
    reading_source: Literal["sudachi", "override"]

@dataclass(frozen=True)
class Mora:
    token_index: int
    index_in_token: int
    kana: str
    tone: Literal["H", "L"] | None = None

@dataclass(frozen=True)
class Pronunciation:
    reading: str
    phones: tuple[str, ...]

@dataclass(frozen=True)
class PhoneInterval:
    start: float
    end: float
    label: str

@dataclass(frozen=True)
class PhoneAnnotation:
    interval: PhoneInterval
    token_index: int | None
    morae: tuple[Mora, ...]
    kana_label: str
    tone_label: str
    is_silence: bool

@dataclass(frozen=True)
class UtteranceOutcome:
    utterance_id: str
    status: OutcomeStatus
    reason_code: str | None
    message: str | None
    artifact_dir: Path | None
    stage_durations: Mapping[str, float]
```

为不受支持的输入定义 `SkipUtterance(reason_code, message, details)`；为受支持但执行失败的输入定义 `StageFailure(stage, reason_code, message, details)`。

- [ ] **步骤 4：实现有类型的 YAML 配置加载**

拒绝未知的顶层键，以及除 `Japanese` 以外的任何语言。外部命令一律以参数数组形式存储，绝不用 shell 字符串。`configs/default.yaml` 必须写明 1.7B ASR 模型、0.6B 回退模型、日语 MFA 模型、16 kHz 工作音频、静音标签 `["", "sil", "sp", "spn"]`，以及项目自有的 cache/output 默认路径。

- [ ] **步骤 5：运行测试与包的静态检查**

运行：`pytest tests/unit/test_config.py tests/unit/test_domain.py -q`
预期：通过。
运行：`python -m compileall -q src`
预期：退出码 0。

- [ ] **步骤 6：提交包基础设施**

```bash
git add pyproject.toml .gitignore configs src/japanmfa tests/unit/test_config.py tests/unit/test_domain.py
git commit -m "feat: establish JapanMFA domain and configuration"
```

### 任务 2：语料发现、文本语义与工作音频

**文件：**
- 新建：`src/japanmfa/corpus.py`
- 新建：`src/japanmfa/audio.py`
- 测试：`tests/unit/test_corpus.py`
- 测试：`tests/contract/test_audio.py`
- 新建：`tests/fixtures/bin/fake_ffmpeg.py`

**接口：**
- 消费：`Utterance`、`SourceText`、`PipelineConfig`
- 产出：`discover_utterances(root: Path) -> list[Utterance]`
- 产出：`load_source_text(path: Path) -> SourceText`
- 产出：`AudioNormalizer.prepare(source: Path, destination: Path) -> AudioInfo`

`AudioInfo` 是一个冻结记录，包含 `source_path`、`working_path`、`duration`、`source_sample_rate`、`source_channels` 和 `working_sample_rate`。

- [ ] **步骤 1：编写语料发现与文本归一化测试**

```python
def test_duplicate_basenames_get_relative_ids(corpus: Path) -> None:
    touch_wav(corpus / "a" / "001.wav")
    touch_wav(corpus / "b" / "001.wav")
    assert [u.utterance_id for u in discover_utterances(corpus)] == ["a/001", "b/001"]


def test_source_text_preserves_original_and_normalizes_processing_copy(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_bytes(b"\xef\xbb\xbf\xe4\xbb\x8a\xe6\x97\xa5\r\n\xe3\x81\xaf\xe6\x99\xb4\xe3\x82\x8c\r\n")
    text = load_source_text(path)
    assert text.original == "今日\r\nは晴れ\r\n"
    assert text.processing == "今日は晴れ"
```

还要测试确定性的字典序、不支持的扩展名被忽略、软链接音频默认被拒绝，以及大小写折叠导致的 ID 冲突抛出 `StageFailure("discovery", "duplicate_utterance_id", ...)`。

- [ ] **步骤 2：运行测试，确认缺失模块导致的失败**

运行：`pytest tests/unit/test_corpus.py -q`
预期：失败，因为 `japanmfa.corpus` 尚不存在。

- [ ] **步骤 3：实现只读的语料发现与源文本加载**

使用 `Path.rglob("*.wav")`，仅在比较时解析路径，绝不向 `root` 之下写入。处理副本要精确剥离一个 UTF-8 BOM；把 CRLF 与其他换行归一化为“无分隔符”，以适配单条话语的处理；对处理副本去除首尾空白；`original` 则保留解码后的源内容（不含 BOM）。

- [ ] **步骤 4：编写会失败的 FFmpeg 命令契约测试**

假可执行文件必须记录 argv 并创建所请求的目标文件。断言传入 `-nostdin`、`-ac 1`、`-ar 16000`、`-c:a pcm_s16le`、显式源路径与显式目标路径，且不使用 `shell=True`。

- [ ] **步骤 5：实现带原子发布目标文件的 `AudioNormalizer`**

先写入 `destination.with_suffix(".partial.wav")`，确认其存在且非空，再 `os.replace`。使用 `subprocess.run(argv, check=True, capture_output=True, text=True)`，并把非零退出转换为 `StageFailure("audio", "ffmpeg_failed", ...)`。

- [ ] **步骤 6：运行针对性测试并提交**

运行：`pytest tests/unit/test_corpus.py tests/contract/test_audio.py -q`
预期：通过。

```bash
git add src/japanmfa/corpus.py src/japanmfa/audio.py tests/unit/test_corpus.py tests/contract/test_audio.py tests/fixtures/bin/fake_ffmpeg.py
git commit -m "feat: discover Japanese corpus inputs safely"
```

### 任务 3：Qwen3-ASR 适配器与日语锁定 worker

**文件：**
- 新建：`src/japanmfa/asr/__init__.py`
- 新建：`src/japanmfa/asr/qwen3.py`
- 新建：`src/japanmfa/asr/worker.py`
- 测试：`tests/contract/test_qwen3_client.py`
- 测试：`tests/unit/test_qwen3_worker.py`
- 新建：`tests/fixtures/bin/fake_qwen_worker.py`

**接口：**
- 产出：`ASRResult(audio_path: Path, language: str, text: str, model: str)`
- 产出：`Qwen3ASRClient.transcribe(audio_paths: Sequence[Path]) -> dict[Path, ASRResult]`
- Worker 协议：stdin 一条 JSON 请求，stdout 一条 JSON 响应；stderr 仅用于诊断。

- [ ] **步骤 1：编写会失败的客户端协议测试**

```python
def test_client_forces_japanese_and_preserves_order(fake_worker: Path, tmp_path: Path) -> None:
    client = Qwen3ASRClient(command=[sys.executable, str(fake_worker)], model="Qwen/Qwen3-ASR-1.7B")
    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    results = client.transcribe(paths)
    assert results[paths[0]].language == "Japanese"
    assert results[paths[0]].text == "今日は晴れ"
```

测试畸形 JSON、结果路径重复/缺失、返回的语言不是日语，以及 worker 非零退出。每一种都必须转成 `StageFailure("asr", ...)`。

- [ ] **步骤 2：运行契约测试，观察导入失败**

运行：`pytest tests/contract/test_qwen3_client.py -q`
预期：失败，因为适配器尚不存在。

- [ ] **步骤 3：实现子进程客户端**

请求 schema 为：

```json
{"model":"Qwen/Qwen3-ASR-1.7B","language":"Japanese","audio_paths":["/abs/a.wav"]}
```

响应 schema 为：

```json
{"results":[{"audio_path":"/abs/a.wav","language":"Japanese","text":"今日は晴れ"}]}
```

要求绝对路径、严格一对一的结​​果覆盖，且 `language == "Japanese"`。不接受自由格式的混合 stdout 流。

- [ ] **步骤 4：围绕注入式假模型编写 worker 单元测试**

定义 `transcribe_request(request: dict, model_factory: Callable) -> dict`。断言 `model.transcribe(audio=[...], language=["Japanese", ...], return_time_stamps=False)` 被调用，且结果被转换为上述协议。

- [ ] **步骤 5：实现真正的 worker 入口点**

仅在 worker 内部导入 `torch` 与 `Qwen3ASRModel`。初始化 `Qwen3ASRModel.from_pretrained(model, dtype=torch.bfloat16, device_map="cuda:0", max_inference_batch_size=32, max_new_tokens=256)`，然后调用 `model.transcribe(audio=[...], language=["Japanese", ...])`。把模型加载隔离在 `_load_model` 中，以便单元测试注入假模型。不要配置强制对齐器，也不要请求时间戳，因为最终边界由 MFA 掌控。

- [ ] **步骤 6：运行测试并提交**

运行：`pytest tests/contract/test_qwen3_client.py tests/unit/test_qwen3_worker.py -q`
预期：在未安装 Qwen 权重的情况下通过。

```bash
git add src/japanmfa/asr tests/contract/test_qwen3_client.py tests/unit/test_qwen3_worker.py tests/fixtures/bin/fake_qwen_worker.py
git commit -m "feat: add Japanese-locked Qwen3 ASR adapter"
```

### 任务 4：Sudachi 前端与按出现位置的读音覆盖

**文件：**
- 新建：`src/japanmfa/frontend/__init__.py`
- 新建：`src/japanmfa/frontend/japanese.py`
- 新建：`src/japanmfa/frontend/overrides.py`
- 测试：`tests/unit/test_japanese_frontend.py`
- 测试：`tests/unit/test_overrides.py`

**接口：**
- 消费：`SourceText`
- 产出：`JapaneseFrontend.analyze(text: SourceText) -> tuple[Token, ...]`
- 产出：`load_reading_overrides(path: Path) -> ReadingOverrideSet`
- 产出：`apply_reading_overrides(utterance_id: str, original: str, tokens: tuple[Token, ...], overrides: ReadingOverrideSet) -> tuple[Token, ...]`

- [ ] **步骤 1：编写会失败的日语支持性测试**

```python
def test_sudachi_mode_b_returns_locked_katakana(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    assert "".join(t.surface for t in tokens) == "今日は晴れ"
    assert all(re.fullmatch(r"[ァ-ヿー]+", t.reading) for t in tokens)


@pytest.mark.parametrize("text", ["Tokyoへ行く", "hello", "日本語🙂"])
def test_non_japanese_or_unknown_input_is_skipped(frontend: JapaneseFrontend, text: str) -> None:
    with pytest.raises(SkipUtterance, match="unsupported_japanese_text"):
        frontend.analyze(SourceText(original=text, processing=text, source="txt"))
```

再包含一个被 Sudachi 转换为合法片假名的数字 token，它必须通过。标点必须保留在元数据中，但不得成为可发音 token。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/unit/test_japanese_frontend.py -q`
预期：失败，因为前端尚不存在。

- [ ] **步骤 3：实现 Sudachi 前端**

构造 `Dictionary(dict="core").create(mode=SplitMode.B)`。分词前先拒绝 ASCII 拉丁字母。对每个非符号语素，要求存在匹配归一化片假名的非空 `reading_form()`。保持与 `SourceText.processing` 精确对齐的跨度；若分词结果无法与源文本位置调和，抛出 `StageFailure("frontend", "token_span_mismatch", ...)`。

- [ ] **步骤 4：编写会失败的覆盖测试**

测试一个合法的 `今日` 覆盖、跨度越界、表层文本不匹配、覆盖区间重叠、重复条目、非法假名，以及两处出现但只改动所选字符跨度的情况。

- [ ] **步骤 5：实现严格的 YAML 覆盖应用**

把 `span` 解析为半开区间 `[start, end]`。在应用任何覆盖之前先校验全部覆盖。只替换目标 token 的读音；v1 中要求覆盖边界必须与某一个完整的可发音 token 对齐。设置 `reading_source="override"`。

- [ ] **步骤 6：运行前端测试并提交**

运行：`pytest tests/unit/test_japanese_frontend.py tests/unit/test_overrides.py -q`
预期：通过。

```bash
git add src/japanmfa/frontend tests/unit/test_japanese_frontend.py tests/unit/test_overrides.py
git commit -m "feat: lock Japanese token readings"
```

### 任务 5：音拍切分与 tdmelodic 重音解析

**文件：**
- 新建：`src/japanmfa/frontend/mora.py`
- 新建：`src/japanmfa/accent/__init__.py`
- 新建：`src/japanmfa/accent/tdmelodic.py`
- 新建：`src/japanmfa/accent/parser.py`
- 测试：`tests/unit/test_mora.py`
- 测试：`tests/unit/test_accent_parser.py`
- 测试：`tests/contract/test_tdmelodic.py`
- 新建：`tests/fixtures/bin/fake_tdmelodic.py`

**接口：**
- 产出：`segment_morae(token: Token) -> tuple[Mora, ...]`
- 产出：`AccentRequest(token_index: int, surface: str, yomi: str)`
- 产出：`TdmelodicClient.predict(requests: Sequence[AccentRequest]) -> dict[int, str]`
- 产出：`parse_accent(marked_yomi: str, locked_morae: tuple[Mora, ...]) -> tuple[Mora, ...]`

- [ ] **步骤 1：编写覆盖充分的音拍测试**

```python
@pytest.mark.parametrize(
    ("kana", "expected"),
    [
        ("キョウ", ["キョ", "ウ"]),
        ("ガッコウ", ["ガ", "ッ", "コ", "ウ"]),
        ("コンピューター", ["コ", "ン", "ピュ", "ー", "タ", "ー"]),
        ("ファイル", ["ファ", "イ", "ル"]),
    ],
)
def test_segment_morae(kana: str, expected: list[str]) -> None:
    assert [m.kana for m in segment_morae(token(kana))] == expected
```

拒绝开头的组合小假名以及不受支持的码点。

- [ ] **步骤 2：实现音拍切分并通过其测试**

实现前先运行：`pytest tests/unit/test_mora.py -q`（失败）。实现一个显式的小假名集合，以及独立成拍的特殊集合 `{ッ, ン, ー}`。再次运行，预期通过。

- [ ] **步骤 3：编写会失败的重音解析器测试**

覆盖 `キ[カイガ]クシュー`、一个带提前 `]` 的“首拍高”形式、一个类似平板型（heiban）的末尾高音段、不配对/嵌套的方括号、出现两次上升却没有下降、标记落在音拍二合假名内部，以及标记读音与锁定读音不一致。断言结果中每个锁定音拍恰好有一个 `H`/`L`。

- [ ] **步骤 4：实现基于边界事件的解析**

在比较相等性之前，先把平假名/片假名转换为同一种规范片假名形式。只在完整音拍之间解析标记。若第一个事件是下降，则初始音高设为 H；否则设为 L。`[` 把其后的音高置为 H，`]` 把其后的音高置为 L。对结构上不可能的事件序列直接拒绝，而不是去修补它。

- [ ] **步骤 5：编写并实现批量 tdmelodic 命令契约**

向单个进程发送每个请求一行 `surface,yomi`，要求每个请求恰好对应一行非空输出，按 `token_index` 保持请求顺序，拒绝单个字段中出现逗号/换行，并把退出码或数量不匹配转换为 `StageFailure("accent", ...)`。测试必须使用 `fake_tdmelodic.py`，不使用 Docker。

- [ ] **步骤 6：运行测试并提交**

运行：`pytest tests/unit/test_mora.py tests/unit/test_accent_parser.py tests/contract/test_tdmelodic.py -q`
预期：通过。

```bash
git add src/japanmfa/frontend/mora.py src/japanmfa/accent tests/unit/test_mora.py tests/unit/test_accent_parser.py tests/contract/test_tdmelodic.py tests/fixtures/bin/fake_tdmelodic.py
git commit -m "feat: derive mora-level Japanese pitch labels"
```

### 任务 6：日语 MFA G2P、出现位置别名与锁定词典

**文件：**
- 新建：`src/japanmfa/mfa/__init__.py`
- 新建：`src/japanmfa/mfa/g2p.py`
- 新建：`src/japanmfa/mfa/lexicon.py`
- 测试：`tests/contract/test_mfa_g2p.py`
- 测试：`tests/unit/test_locked_lexicon.py`
- 新建：`tests/fixtures/bin/fake_mfa.py`

**接口：**
- 产出：`MfaG2pClient.pronounce(readings: Sequence[str], work_dir: Path) -> tuple[Pronunciation, ...]`
- 产出：`LockedLexicon.build(utterance_id: str, tokens: tuple[Token, ...], pronunciations: tuple[Pronunciation, ...]) -> LockedLexicon`
- 产出：`LockedLexicon.write(corpus_dir: Path, dictionary_path: Path) -> None`

`LockedLexicon` 是一个冻结记录，包含 `utterance_id`、有序的 `aliases`、`transcript`、`tokens` 和 `pronunciations`；所有元组的 token 数量一致。

- [ ] **步骤 1：编写会失败的 G2P 命令测试**

断言适配器写出一份由锁定片假名组成的 UTF-8 词表，以 argv 数组形式调用配置的 MFA 可执行文件，读取 MFA 词典输出，按输入位置保留重复读音，并拒绝缺失、多重或不在词表内的读音。假命令应支持预期的 `mfa g2p INPUT japanese_mfa OUTPUT` 形态并记录 argv。

- [ ] **步骤 2：实现带窄版本兼容接缝的 `MfaG2pClient`**

创建 `_build_command(input_path, output_path) -> list[str]`，作为唯一与版本相关的函数。把制表符或空白分隔的词典行解析为 `Pronunciation(reading, phones)`。若安装的日语 MFA 版本需要 `--dictionary_path` 或其他有文档记载的选项，只调整 `_build_command`，并在任务 11 中把该版本固定在环境文件里。

- [ ] **步骤 3：编写别名/词典测试**

```python
def test_aliases_are_unique_per_occurrence() -> None:
    lexicon = LockedLexicon.build("speaker/001", tokens("今日 今日"), pronunciations(...))
    assert lexicon.aliases == ("jmfa_000000", "jmfa_000001")
    assert lexicon.transcript == "jmfa_000000 jmfa_000001"
    assert len(set(lexicon.aliases)) == 2
```

还要断言别名只包含 `[a-z0-9_]`、词典中每行只有一个读音，以及 token/读音数量或读音不匹配时抛出 `StageFailure("mfa_g2p", ...)`。

- [ ] **步骤 4：实现确定性的锁定词典写出**

别名编号按 token 顺序生成，而不是基于哈希。写出一个包含别名的语料级 `.lab` 文件，以及每个别名一行的词典。持久化一个伴随文件 `aliases.json`，把别名映射到 token 序号、表层文本、读音、音拍与音素。使用原子写入。

- [ ] **步骤 5：运行测试并提交**

运行：`pytest tests/contract/test_mfa_g2p.py tests/unit/test_locked_lexicon.py -q`
预期：通过。

```bash
git add src/japanmfa/mfa tests/contract/test_mfa_g2p.py tests/unit/test_locked_lexicon.py tests/fixtures/bin/fake_mfa.py
git commit -m "feat: build MFA-locked occurrence lexicons"
```

### 任务 7：MFA 对齐运行器与原始 TextGrid 解析

**文件：**
- 新建：`src/japanmfa/mfa/runner.py`
- 新建：`src/japanmfa/mfa/textgrid.py`
- 测试：`tests/contract/test_mfa_runner.py`
- 测试：`tests/unit/test_mfa_textgrid.py`
- 新建：`tests/fixtures/mfa/aligned.TextGrid`
- 修改：`tests/fixtures/bin/fake_mfa.py`

**接口：**
- 产出：`MfaRunner.validate(corpus_dir: Path, dictionary: Path, work_dir: Path) -> None`
- 产出：`MfaRunner.align(corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path) -> Path`
- 产出：`parse_mfa_textgrid(path: Path, silence_labels: frozenset[str]) -> MfaAlignment`
- `MfaAlignment` 包含有序的词区间与音素区间，并保留原始标签与静音分类。

定义 `RawMfaInterval(start, end, label, tier_name)`，满足 `end >= start`；定义 `MfaWord(alias, start, end)` 与 `MfaPhone(label, start, end, word_alias, is_silence)`。`MfaAlignment` 包含有序的 `words`、时长为正的 `phones`，以及针对空区间或零时长原始条目的 `diagnostic_intervals`。零时长的非静音音素属于解析失败；零时长的空/静音条目仅作为诊断记录保留。

- [ ] **步骤 1：编写命令构造与失败隔离测试**

断言校验先于对齐运行，且命令等价于：

```text
mfa validate CORPUS DICTIONARY japanese_mfa --output_directory WORK
mfa align CORPUS DICTIONARY japanese_mfa OUTPUT --temporary_directory WORK --clean
```

确切的 MFA 3.x 参数必须在实现期间用 `mfa ... --help` 核实，并固定在一个构造方法中。测试非零退出、缺少输出 TextGrid，以及 stderr 捕获。

- [ ] **步骤 2：实现运行器并通过契约测试**

使用 `subprocess.run` 与 argv 数组，不使用 shell。把 stdout/stderr 复制到确定性的日志文件。绝不允许把 `--clean` 或临时输出指向语料、仓库根目录、家目录或用户提供的宽泛路径；要求使用生成的、按话语归属的工作目录。

- [ ] **步骤 3：编写原始 TextGrid 解析测试**

夹具必须包含词别名、普通音素、`sil`、`sp`、`spn`、一个空区间和一个零时长区间。断言：

- 层名是显式发现的，而不是按数字位置推断；
- 原始音素标签与浮点边界被保留；
- 配置的静音标签被归类为静音；
- 空/零时长区间保留为诊断记录，但不移动相邻边界；
- 区间重叠或递减时抛出 `StageFailure("mfa_parse", "invalid_boundaries", ...)`。

- [ ] **步骤 4：使用 praatio 实现解析器**

通过配置接受 MFA 标准的词层与音素层名称的各种变体。把条目转换为不可变的领域区间。把每个非静音音素关联到包含它的词区间；拒绝跨越两个词或没有所属词的音素。

- [ ] **步骤 5：运行测试并提交**

运行：`pytest tests/contract/test_mfa_runner.py tests/unit/test_mfa_textgrid.py -q`
预期：通过。

```bash
git add src/japanmfa/mfa/runner.py src/japanmfa/mfa/textgrid.py tests/contract/test_mfa_runner.py tests/unit/test_mfa_textgrid.py tests/fixtures/mfa tests/fixtures/bin/fake_mfa.py
git commit -m "feat: run and parse Japanese MFA alignments"
```

### 任务 8：音拍到音素的调和与声调投影

**文件：**
- 新建：`src/japanmfa/projection.py`
- 新建：`src/japanmfa/mfa/phone_map.py`
- 新建：`src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml`
- 测试：`tests/unit/test_projection.py`
- 测试：`tests/unit/test_phone_map.py`

**接口：**
- 产出：`PhoneMap.load(path: Path) -> PhoneMap`
- 产出：`project_annotations(alignment: MfaAlignment, lexicon: LockedLexicon, token_morae: dict[int, tuple[Mora, ...]], phone_map: PhoneMap) -> tuple[PhoneAnnotation, ...]`

- [ ] **步骤 1：根据观测到的日语 MFA 音素建立会失败的测试矩阵**

至少覆盖简单 CV、腭化音拍、`ン`、`ッ`、长音、锁定模型若会输出的清化元音拼写，以及静音。每个测试夹具都要写明锁定假名、G2P 音素、对齐后的音素、预期的音拍分组，以及预期的音素声调标签。

- [ ] **步骤 2：加入带严格校验的版本化音素映射加载器**

该 YAML 文件写明确切的模型族（`japanese_mfa_v3`），并把假名/音拍模式映射到预期音素组。拒绝重复规则、未知规则字段，以及配置的模型族不匹配。归一化别名必须显式列出；绝不笼统地剥离 IPA 修饰符。

- [ ] **步骤 3：实现词与音素的调和**

要求 MFA 词别名顺序等于 `LockedLexicon.aliases`。对每个词，要求排序后的非静音对齐音素在经过有文档记载的模型专属归一化之后，等于锁定读音。用确定性的动态规划匹配器把音素映射到音拍分组；只有当恰好存在唯一最小代价映射时才接受结果。

- [ ] **步骤 4：实现 H/L 广播与复合标签**

```python
def labels_for_phone(morae: tuple[Mora, ...]) -> tuple[str, str]:
    kana = "|".join(m.kana for m in morae)
    tone = "|".join(cast(str, m.tone) for m in morae)
    if not kana or any(m.tone is None for m in morae):
        raise StageFailure("projection", "unlabeled_phone", "...", {})
    return kana, tone
```

一个音拍映射到多个音素时，在每个音素上重复它的假名与声调。一个音素映射到多个音拍时，输出有序的复合标签。静音则把两个标签都置空，并设 `token_index=None`。

- [ ] **步骤 5：测试歧义与“不臆造边界”行为**

增加一个长音素映射到声调 `H`、`L` 的用例；断言得到一条注解，它保留原始 MFA 区间且 `tone_label == "H|L"`。再增加一个映射有歧义的用例，断言抛出 `StageFailure("projection", "ambiguous_mora_phone_mapping", ...)`。

- [ ] **步骤 6：运行测试并提交**

运行：`pytest tests/unit/test_phone_map.py tests/unit/test_projection.py -q`
预期：通过。

```bash
git add src/japanmfa/projection.py src/japanmfa/mfa/phone_map.py src/japanmfa/mfa/data tests/unit/test_projection.py tests/unit/test_phone_map.py
git commit -m "feat: project mora pitch onto MFA phones"
```

### 任务 9：五层 TextGrid 与结构化报告

**文件：**
- 新建：`src/japanmfa/output/__init__.py`
- 新建：`src/japanmfa/output/textgrid.py`
- 新建：`src/japanmfa/output/reports.py`
- 测试：`tests/unit/test_output_textgrid.py`
- 测试：`tests/unit/test_reports.py`

**接口：**
- 产出：`write_five_tier_textgrid(path: Path, duration: float, original: str, kana: str, annotations: Sequence[PhoneAnnotation]) -> None`
- 产出：`validate_five_tier_textgrid(path: Path, duration: float, silence_labels: frozenset[str]) -> None`
- 产出：`write_json(path: Path, payload: Mapping[str, object]) -> None`
- 产出：`append_manifest(path: Path, outcome: UtteranceOutcome) -> None`
- 产出：`summarize(outcomes: Sequence[UtteranceOutcome]) -> dict[str, object]`

- [ ] **步骤 1：编写会失败的五层黄金测试**

构造包含语音、静音、一个多音素音拍，以及一个 `H|L` 长音素的注解。断言层名与顺序完全等于：

```python
["original", "kana", "phones", "phone_kana", "phone_tone"]
```

断言前两层各包含一个 `[0.0, duration]` 区间，而后三层中每个条目的序列化 `xmin/xmax` 值逐字节等价。

- [ ] **步骤 2：实现写出器与校验器**

使用 praatio 写出 long 格式的 TextGrid。三个音素级层要在对 `PhoneAnnotation` 的同一次循环中构建，以确保边界不会产生分歧。原子发布之前，重新打开写出的文件并校验层数/层序、时长、单调性、边界一致性、静音区间为空，以及非静音区间的完整性。

- [ ] **步骤 3：编写报告测试**

测试 `aligned`/`skipped`/`failed` 计数、稳定的 reason code 分组、Unicode JSON、JSONL 追加加锁，以及一个畸形结果被拒绝。断言报告中的路径尽可能相对于输入/输出根目录，且不序列化任何 API key 或环境中的密钥。

- [ ] **步骤 4：实现原子 JSON 与批量报告**

以 UTF-8 写出，使用 `ensure_ascii=False`、键排序和末尾换行。JSON 通过相邻的临时文件加 `os.replace` 发布。包含 `run_id`、工具/模型版本、来源类型、各阶段耗时、reason code 与追踪 ID。

- [ ] **步骤 5：运行测试并提交**

运行：`pytest tests/unit/test_output_textgrid.py tests/unit/test_reports.py -q`
预期：通过。

```bash
git add src/japanmfa/output tests/unit/test_output_textgrid.py tests/unit/test_reports.py
git commit -m "feat: export validated five-tier alignments"
```

### 任务 10：指纹化缓存、管线编排与 CLI

**文件：**
- 新建：`src/japanmfa/cache.py`
- 新建：`src/japanmfa/pipeline.py`
- 新建：`src/japanmfa/cli.py`
- 测试：`tests/unit/test_cache.py`
- 测试：`tests/integration/test_pipeline_fake_backends.py`
- 测试：`tests/contract/test_cli.py`

**接口：**
- 产出：`stage_fingerprint(stage: str, inputs: Mapping[str, object]) -> str`
- 产出：`StageCache.load_or_run(stage: str, fingerprint: str, producer: Callable[[Path], T]) -> T`
- 产出：`JapanMFAPipeline.run(input_root: Path, output_root: Path, overrides: Path | None) -> BatchResult`
- 产出 Typer 命令：`check`、`run`、`run-file`、`inspect`

- [ ] **步骤 1：编写缓存失效与原子性测试**

断言相同的音频/文本/配置/模型取值会复用同一阶段，修改某个覆盖会使前端及其下游阶段失效但不影响 audio/ASR，生产者抛异常时绝不发布完成标记，以及残留的部分目录被安全忽略。

- [ ] **步骤 2：实现规范化指纹与阶段缓存**

对规范化 JSON 做哈希，内容包含阶段名、输入 SHA-256 值、解析后的配置子集、模型标识与适配器版本。一个完成的阶段目录包含 `result.json` 与 `complete.json`，二者指纹相同。发布时重命名缓存父目录下新生成的子目录，绝不通过删除一个未解析完成的路径来发布。

- [ ] **步骤 3：编写完整的假后端管线测试**

使用极小的假 WAV、权威文本、假 Qwen、假 tdmelodic、假 MFA G2P/对齐，以及一个 MFA TextGrid 夹具。断言管线写出一个合法的最终 TextGrid、四份 JSON/报告产物，以及一行 `aligned` 的 manifest 记录。再增加三个用例：

- 强制日语 ASR 对缺失 `.txt` 的条目返回 `Tokyo` → `skipped`；
- tdmelodic 输出畸形 → `failed`，批量继续；
- 一个 MFA 失败与一个合法条目并存 → 一个 `failed`、一个 `aligned`。

- [ ] **步骤 4：实现阶段编排**

阶段顺序为 audio → source/ASR → frontend/overrides → mora/accent → G2P/lexicon → MFA → projection → output。逐话语只捕获 `SkipUtterance` 与 `StageFailure`；意外异常转为 `failed` 并附上 traceback 路径，随后继续处理。只有在 TextGrid 校验器通过之后才发布最终结果。

- [ ] **步骤 5：用 Typer 的 `CliRunner` 编写 CLI 测试**

断言 `run` 拒绝相同的输入/输出根目录，拒绝嵌套在输入语料内部的输出目录，接受绝对路径的 config/override，只在批量级设置失败时返回非零，且 `inspect` 会从 manifest 打印 aligned/skipped/failed 计数。

- [ ] **步骤 6：实现四个 CLI 命令**

`run-file` 在不修改源目录的前提下构建一个临时的单项 manifest。`run` 打印最终摘要路径，并接受一个可选的正数 `--limit`，仅用于在确定性发现之后限制冒烟测试规模。`inspect` 是只读的。`check` 委托给任务 11 的预检 API。

- [ ] **步骤 7：运行测试并提交**

运行：`pytest tests/unit/test_cache.py tests/integration/test_pipeline_fake_backends.py tests/contract/test_cli.py -q`
预期：通过。

```bash
git add src/japanmfa/cache.py src/japanmfa/pipeline.py src/japanmfa/cli.py tests/unit/test_cache.py tests/integration/test_pipeline_fake_backends.py tests/contract/test_cli.py
git commit -m "feat: orchestrate resumable JapanMFA runs"
```

### 任务 11：可复现环境、预检与用户文档

**文件：**
- 新建：`environment.yml`
- 新建：`environments/mfa.yml`
- 新建：`environments/asr.yml`
- 新建：`tools/build_tdmelodic_image.sh`
- 新建：`src/japanmfa/checks.py`
- 新建：`tests/contract/test_checks.py`
- 新建：`README.md`
- 新建：`docs/architecture.md`
- 新建：`docs/input-output.md`
- 新建：`docs/reading-overrides.md`
- 新建：`docs/accent-mapping.md`
- 新建：`docs/limitations.md`

**接口：**
- 产出：`run_preflight(config: PipelineConfig) -> PreflightReport`
- 消费任务 1–10 所定义的全部稳定公开接口。

- [ ] **步骤 1：查看工具实际的 help 输出并固定兼容版本**

在隔离的候选环境中运行：

```bash
mfa version
mfa g2p --help
mfa validate --help
mfa align --help
python -c "import qwen_asr; print(getattr(qwen_asr, '__version__', 'unknown'))"
```

把解析出的确切版本记录进环境 YAML 文件；仅当官方 API 实际不同时，才调整任务 3、6、7 中那些窄口径的命令/构造接缝。不得削弱领域契约。

- [ ] **步骤 2：使用假命令编写会失败的预检测试**

覆盖可执行文件缺失、MFA 主版本不符、日语模型缺失、output/cache 不可写、Qwen 无 CUDA 且显式禁止 CPU、tdmelodic 探针返回畸形输出，以及完全合法的环境。报告中包含逐项通过/失败检查与可操作的命令，绝不包含密钥。

- [ ] **步骤 3：实现预检**

使用有界的子进程超时。检查所配置可执行文件的身份/版本、模型路径或模型注册表是否存在、通过临时子文件检查 output/cache 可写性，以及一次确定性的 tdmelodic `sy2a` 探针——其未标记的读音应等于所提供的 yomi。

- [ ] **步骤 4：添加隔离环境清单与 tdmelodic 构建包装脚本**

编排器与 MFA 环境固定 Python 3.11。Qwen3-ASR 环境固定 Python 3.12，遵循 Qwen 官方的隔离环境快速上手指南。shell 包装脚本必须使用 `set -euo pipefail`，从配置好的 tdmelodic commit 构建，确定性地打标签，且绝不修改旧仓库或全局 Conda 环境。

- [ ] **步骤 5：编写运维文档**

记录安装、模型下载、预检、单文件与批量用法、五层语义、覆盖示例、reason code、恢复方式、环境隔离，以及明确的 v1 限制。写清两条确切的规则：已存在的 `.txt` 为权威，以及 `H|L` 长音素约定。

- [ ] **步骤 6：运行测试与链接检查并提交**

运行：`pytest tests/contract/test_checks.py -q`
预期：通过。
运行：`python -m compileall -q src && git diff --check`
预期：退出码 0。

```bash
git add environment.yml environments tools/build_tdmelodic_image.sh src/japanmfa/checks.py tests/contract/test_checks.py README.md docs
git commit -m "docs: add isolated runtime and operating guide"
```

### 任务 12：真实模型集成与 `0922jap` 验收

**文件：**
- 新建：`tests/integration/test_real_qwen.py`
- 新建：`tests/integration/test_real_tdmelodic.py`
- 新建：`tests/integration/test_real_mfa.py`
- 新建：`tests/integration/test_real_pipeline.py`
- 修改：`docs/limitations.md`
- 修改：`docs/test-report-0922jap.md`

**接口：**
- 校验完整的公开 CLI 与产物契约。
- 产出规格说明中“完成定义”所要求的证据。

- [ ] **步骤 1：添加需显式开启的真实后端测试**

给测试打上 `@pytest.mark.real_models` 标记，除非显式设置了模型路径/环境标志，否则跳过。每个测试使用有界的本地夹具，并断言 schema/契约层面的行为，而不是对任意音频断言脆弱的精确转写文本。

- [ ] **步骤 2：让一条真实话语依次通过每个隔离后端**

运行：

```bash
pytest -m real_models tests/integration/test_real_qwen.py -v
pytest -m real_models tests/integration/test_real_tdmelodic.py -v
pytest -m real_models tests/integration/test_real_mfa.py -v
```

预期：Qwen 报告 `Japanese`；tdmelodic 的输出可往返回到锁定的 yomi；MFA 产出词层与音素层，且别名序列与锁定的一致。

- [ ] **步骤 3：把 Windows 共享解析为只读的 Linux 路径**

找到与 `\\RS3621\Research_TTS\Data\Raw\0922jap` 对应的现有挂载点。把解析出的路径与挂载模式记录进测试报告。未经用户新的授权，不要挂载、重新挂载、覆盖、重命名或写入源共享目录。

- [ ] **步骤 4：运行预检与一次小规模真实端到端抽样**

```bash
japanmfa check --config configs/default.yaml
japanmfa run --input /resolved/read-only/0922jap --output /home/user/JapanMFA/runs/0922jap-smoke --config configs/default.yaml --limit 3
pytest -m real_models tests/integration/test_real_pipeline.py -v
```

预期：至少有一条受支持的日语话语为 `aligned`，其 TextGrid 恰好包含五个合法层，且所有扫描到的条目都有终态。

- [ ] **步骤 5：在不修改源目录的前提下运行全语料**

```bash
japanmfa run --input /resolved/read-only/0922jap --output /home/user/JapanMFA/runs/0922jap-full --config configs/default.yaml
japanmfa inspect /home/user/JapanMFA/runs/0922jap-full/manifest.jsonl
```

预期：每个被发现到的 WAV 都被分类；尽管存在条目级的 skip/fail，进程仍正常退出。

- [ ] **步骤 6：检查有代表性的 TextGrid 并记录证据**

至少选取：一个简单词序列、一个长音、一个鼻音或促音、一条 ASR 回退条目（若存在），以及一条 skipped/failed 条目。在 `docs/test-report-0922jap.md` 与 `docs/limitations.md` 中记录层名、边界一致性检查、声调覆盖情况、截图或文件路径、reason code、汇总计数、工具/模型版本、耗时，以及所有新暴露出的行为。

- [ ] **步骤 7：校验旧仓库与完整的新项目**

运行：

```bash
git -C /home/user/JapMFA rev-parse HEAD
git -C /home/user/JapMFA status --short --branch
pytest -q
python -m compileall -q src
git diff --check
git status --short --branch
```

预期：旧仓库 HEAD 仍为 `55208b4e10cd2f163c1d9116b0502709d41ab656`；其仅保留两个原本就存在的未跟踪 handoff 文件；新项目所有非可选测试通过；提交报告后，新项目中没有遗留的计划外改动。

- [ ] **步骤 8：提交验收证据**

```bash
git add tests/integration docs/limitations.md docs/test-report-0922jap.md
git commit -m "test: validate JapanMFA on Japanese corpus"
```

## 最终评审与交付

- [ ] 调用 `superpowers:requesting-code-review`，对照已确认的规格说明与本计划做整分支评审。
- [ ] 使用 `superpowers:receiving-code-review` 处理评审发现，并重跑受影响的测试。
- [ ] 调用 `superpowers:verification-before-completion`；用全新输出重跑完整的非可选测试套件、真实模型冒烟测试、五层校验器、`git diff --check`，以及旧仓库完整性检查。
- [ ] 调用 `superpowers:finishing-a-development-branch` 呈现集成选项。
- [ ] 只有在验证之后，并按用户选定的集成动作推送；若创建了 pull request，将其关联到本任务。

## 自审记录

- 规格覆盖：规格说明的全部 22 个小节都映射到任务 1–12 或最终评审；没有遗留未覆盖的需求。
- 占位符扫描：没有残留 `TBD`、实现类 `TODO`、“与……类似”式的表述，或未写明的错误处理步骤。
- 类型一致性：`Token`、`Mora`、`Pronunciation`、`PhoneInterval`、`PhoneAnnotation`、`LockedLexicon`、`MfaAlignment` 与 `UtteranceOutcome` 都在被消费之前引入，且全文拼写唯一。
- 评审关注点：五类高风险输入在任务 2、3/4、7、5/8 中都有显式测试。
- 外部 API 风险被收敛在 `_load_model` 与 MFA 命令构造接缝中；真实集成之前先固定已核实的版本。
