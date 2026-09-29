# JapGalgame Qwen CTC 吞吐提速实施交接

## Metadata

- UTC 快照：2026-09-29T07:01:08Z
- 仓库：`/home/user/JapanMFA`
- 分支：`main`
- revision：`755121e9995047cef1924d3ae1ba0596c0441c2f`
- task slug：`japgalgame-ctc-throughput`
- 计划文件：`handoffs/20260929T070108Z-japgalgame-ctc-throughput.md`
- 工作树状态：dirty。存在大量用户已有的 tracked 修改和 untracked 文件；本任务涉及的 `tools/galgame_qwen_ctc.py`、`tools/galgame_qwen_ctc_supervisor.py`、`tools/run_japgalgame_ctc_full.sh`、相关测试和运行文档均为已有 untracked 文件。
- 规划者动作：仅只读调查；未修改源文件、测试、配置、运行状态或 Git 状态。
- freshness：root 于 2026-09-29T07:08:53Z 复核 revision、status、全部引用文件及行号，目标 handoff 路径不存在。`docs/alignment-issues.md` 于 07:04:06Z 更新，新增 0922jap 边界修复最终验收证据；该更新不改变本 CTC 吞吐方案的约束，已纳入复核。最终写入前再次检查。
- 规划路线：root 已将本任务交给指定的 Sol high 规划工作者；本交接等待 root 验证后原子写入。

## Objective

在不改变 Qwen ForcedAligner 模型语义、最终 TextGrid 名称、失败判定和恢复能力的前提下，提高 `/mnt/Raw/JapGalgame` 中 6,423,108 对 WAV/TXT 的端到端发布吞吐。

当前八卡、16 个模型进程约为 23–25 条/秒，短时增加到 24 个模型进程没有总吞吐收益。目标是在有界本地磁盘中建立按输出目录排序的 staging、长驻 GPU 消费和独立发布流水线，以减少 CIFS 随机小文件读取和元数据等待，并保留当前实现作为即时回退路径。

最低发布门槛是稳定端到端吞吐相对 25 条/秒提高至少 30%，即达到 32.5 条/秒；目标值为至少 40 条/秒。

## Background and current behavior

输入是 `/mnt/Raw/JapGalgame` 下每个游戏的同名 WAV/TXT，输出是同一游戏 `ctc` 目录中的同名 `.TextGrid`。文档明确说明 TXT 是权威文本，使用项目内固定的 `Qwen3-ForcedAligner-0.6B`，既有同名 TextGrid 不覆盖，失败不能计为成功，见 `docs/japgalgame-qwen-ctc-20260928.md:3-7`。

清点结果是 560 个游戏、6,423,108 对 WAV/TXT、缺失配对为 0。现有全量运行将清单分为 16 份，每张 GPU 两个模型进程，batch size 为 16，见 `docs/japgalgame-qwen-ctc-20260928.md:9-11` 和 `tools/run_japgalgame_ctc_full.sh:62-72`。

工作进程当前对每条未完成记录执行以下远端操作：

1. 根据输出父目录调用 `os.scandir` 构建既有文件名集合，见 `tools/galgame_qwen_ctc.py:262-267`。
2. 从 CIFS 单独读取 TXT，见 `tools/galgame_qwen_ctc.py:331-355`。
3. 打开 WAV 头计算时长，见 `tools/galgame_qwen_ctc.py:227-231`。
4. 将远端 WAV 路径交给模型，模型随后读取音频，见 `tools/galgame_qwen_ctc.py:234-237`。
5. 在 CIFS 输出目录写临时文件并以 `os.replace` 发布，见 `tools/galgame_qwen_ctc.py:214-224`。
6. 每次 batch flush 后原子更新本地 worker 状态，见 `tools/galgame_qwen_ctc.py:269-272`、`tools/galgame_qwen_ctc.py:321-329`。

监督器每 30 秒汇总 worker 状态和 GPU 指标，15 分钟无 checkpoint 时终止并有限重启 worker，见 `tools/galgame_qwen_ctc_supervisor.py:120-168`。完成状态保持 `success`、`failed`、`remaining` 和缺失配对相互独立，见 `tools/galgame_qwen_ctc_supervisor.py:30-53`。

## Facts

1. 2026-09-29 早先的稳定采样中，各 GPU 平均利用率约为 0–6.5%，16 个 worker 的等待位置主要是 CIFS `wait_for_response` 和 `folio_wait_bit_common`，总吞吐约 25.5 条/秒，见 `docs/japgalgame-qwen-ctc-20260928.md:37-39`。

2. 增加 8 个额外进程后，原 16 进程降到约 17–18 条/秒，新增进程约 7 条/秒，总计仍约 24–25 条/秒。停止额外进程后原作业回到约 24 条/秒，见 `docs/japgalgame-qwen-ctc-20260928.md:41`。

3. 07:00 UTC 的只读 31 秒复测中，`seen` 从 1,342,665 增至 1,343,337，实际为 21.68 条/秒；当时累计 `success=1,342,967`、`failed=358`。这是短窗口数据，只用于确认瓶颈仍存在，不替代较长基线。

4. 同一时段对 16 个 worker 做 24 次每秒 wchan 采样，共 384 个样本：

   - `wait_for_response`：252 次，65.6%
   - `folio_wait_bit_common`：103 次，26.8%
   - `do_renameat2`：7 次
   - `open_last_lookups`：9 次
   - 无阻塞等待标记：13 次

5. 12 轮、每轮 8 卡的两秒 GPU 采样中，96 个 SM 利用率样本有 89 个为 0%。少量短峰值达到 39%、44%、47%、52% 和 98%，说明 GPU 计算呈间歇突发，绝大多数时间等待上游或下游 I/O。

6. `/home/user/JapanMFA` 位于 ext4，本次调查时约有 478 GiB 可用。`/mnt/Raw` 是 CIFS 3.0，使用 `cache=strict`、`actimeo=1`、4 MiB rsize/wsize。

7. 从 16 个 manifest 随机字节偏移抽取 512 条记录并 stat：

   - WAV 平均 197,388 字节
   - WAV p50 177,606 字节
   - WAV p90 326,544 字节
   - WAV p99 544,392 字节
   - 最大样本 805,548 字节
   - TXT 平均 67 字节
   - 按样本均值推算全部 WAV 约 1.15 TiB

   因此 478 GiB 本地剩余空间不足以全量镜像，但足以容纳数十 GiB 的有界滑动 staging。

8. 对 96 个随机、未缓存样本进行单并发完整 CIFS 读取时，120 秒仍未完成，调查者主动中止。该探针受正在运行的生产作业影响，不能作为绝对带宽值，但其长尾与 wchan 证据一致。不得据此推算全量 ETA。

9. 当前发布采用同目录临时文件和 rename；相关单测明确禁止成功发布后再做冗余 SMB unlink，见 `tests/unit/test_galgame_qwen_ctc.py:149-160`。

10. 当前 reshard 保留总对数和缺失计数，并验证所有记录都被保留，见 `tools/galgame_qwen_ctc.py:100-147` 和 `tests/unit/test_galgame_qwen_ctc.py:66-86`。

11. 监督器已测试 16 shard 在八卡上的均匀映射、完成与失败计数分离，见 `tests/unit/test_galgame_qwen_ctc_supervisor.py:9-38`。

12. `AGENTS.md:1-13` 要求所有 alignment、silence、punctuation、energy 和输出发布问题统一记录在 `docs/alignment-issues.md`。发布纠正过的 TextGrid/WAV 前必须保留旧件及哈希，运行相关回归与 `tools/audit_textgrid_pauses.py`，且缺失 TextGrid 必须计为失败。审计脚本会记录 TextGrid 和 WAV SHA-256，并在任何失败或空样本时返回非零，见 `tools/audit_textgrid_pauses.py:60-84`。

## Assumptions

1. 全量运行期间 WAV/TXT 输入保持只读稳定。实现仍必须记录 staged 输入的源路径、大小和 mtime；若同一源在一次运行中变化，该条必须失败并重新取源，不可继续使用旧 staging。

2. 同一输出目录内按顺序读取、过滤和发布一批记录，会比 16 个独立 worker 在多个目录间交错访问产生更少的 CIFS 元数据等待。该假设必须由实验矩阵验证。

3. 32 GiB staging 上限和 350 GiB 本地可用空间下限不会影响当前机器上的模型、环境和其他用户任务。若实施窗口开始时空间低于门槛，staged 模式必须拒绝启动。

4. 生产切换时可保证旧监督器和 staged 监督器不重叠。当前 `os.replace` 在目标已存在时可能替换它，因此独占发布者是安全不变量。

5. Qwen 对同一 WAV、TXT、模型和 batch 形态的结果足够稳定，可通过字节哈希或 1 微秒容差的解析后比较验证。如果字节不稳定，语义比较是验收依据，但必须解释具体差异。

## Decisions

1. 保留现有 legacy worker 和启动方式，新增显式 `staged` 模式。默认不得静默切换；生产 rollout 必须通过性能和正确性门槛。

2. 不再将“增加模型进程”作为主提速手段。8 或 16 个 GPU worker、batch 16 或 32 只在输入已位于 ext4 的 compute ceiling 实验中选择。

3. staged 模式采用四段流水线：

   - 本地 manifest 调度器按 `output.parent` 合并排序记录。
   - 有界 stager 将 WAV 复制到 ext4，并在本地 chunk manifest 内保存清洗后的 TXT、源指纹、WAV 时长和最终输出路径。
   - 长驻 GPU worker 只读取本地 WAV，结果先写成本地 result bundle。
   - 少量 publisher 按输出目录顺序执行现有临时文件加 rename 发布。

4. manifest 调度使用对 16 个已排序 shard 的 heap merge，不创建全量 6.4M 行内存索引，也不重新扫描 `/mnt/Raw/JapGalgame`。chunk 的初始实验大小为 256、512、1024 条。

5. staging 使用文件系统队列和 chunk 级 SQLite 状态：

   - `.part` chunk 完整复制后原子改名为 ready。
   - GPU worker 以原子 rename 领取 ready chunk。
   - result bundle 完整写出后原子发布到 result queue。
   - publisher 领取 bundle 后逐个发布；chunk 全部为已存在、成功发布或明确失败后才标记完成。
   - 数据库丢失时，最终 `ctc` 文件存在性和原始 manifest 仍可重建进度。

6. 默认 scratch 上限为 32 GiB，高水位暂停 staging，降到 24 GiB 后恢复；本地剩余空间低于 350 GiB 时立即停止继续 staging，但允许 compute 和 publisher 排空已有队列。

7. 新生产状态目录使用 `.runtime/jobs/japgalgame-ctc-staged-v1-20260929`；原 `.runtime/jobs/japgalgame-ctc-full16-20260928` 保持可直接回退。manifest 可在同一 ext4 文件系统中 hardlink 到新状态目录，但必须先验证大小、SHA-256 和总行数。

8. 不在首轮方案中修改 CIFS mount 选项。挂载参数变化会引入一致性和主机级风险，而且现有证据已支持先消除应用层随机访问。

## Scope

### In scope

- 本地有界 staging、chunk 状态机、GPU 消费和发布解耦。
- 输出目录级排序、一次目录扫描和 publisher 分区。
- staged 与 legacy 两种监督模式。
- 每阶段耗时、字节、队列深度、scratch 水位和发布吞吐指标。
- 单元测试、故障注入、真实模型 A/B、断点恢复和生产 rollout。
- 输出等价性及相关 TextGrid/WAV 审计。
- 文档和必要的 issue ledger 更新。

### Out of scope

- 更换 Qwen 模型、语言、时间戳投影或 TextGrid schema。
- 改写 TXT、修复现有模型失败或重新发布既有成功 TextGrid。
- CIFS 服务端配置、网络拓扑或挂载参数调整。
- 全量复制 1.15 TiB 输入到本地。
- 修改 MFA、音素边界、标点归属或声学后处理。
- 清理用户已有工作树改动。
- 提交、推送或部署。

## Constraints and invariants

1. 保留全部用户已有改动；不得 reset、checkout、清理 untracked 文件或重排无关代码。
2. 输出必须继续位于原始 `ctc` 路径并使用完全相同的文件名。
3. staged 模式不得覆盖已存在的 final TextGrid。
4. 任意时刻只能有一个生产发布监督器。
5. `done` 只在 final TextGrid 已成功 rename 或启动前已存在时增加。
6. 转移、模型、render、publish 的失败必须进入独立错误记录，不能成为成功。
7. supervisor 的 `remaining`、`success`、`failed`、缺失配对和 worker 完成数继续保持可核对。
8. 终止 staged 作业后不得立即删除 scratch；scratch 是未发布结果的恢复来源。
9. 任何纠正既有 TextGrid 的动作均不属于本提速变更。若后续确需纠正，先保留旧件和 SHA-256，再按 `AGENTS.md` 执行回归和 pause audit。
10. 缺失 TextGrid 是失败；验收脚本不得以“文件没找到所以没有违规”判定成功。

## Impacted files and symbols

| 文件 | 现有证据 | 计划变更 |
|---|---|---|
| `tools/galgame_qwen_ctc.py` | catalog/reshard 在 `52-147`；原子发布在 `214-224`；worker 在 `240-358`；CLI 在 `361-382` | 增加 chunk 规划、stage、staged-worker、publish、verify-state 子命令；保留 legacy `worker` |
| `tools/galgame_qwen_ctc_supervisor.py` | GPU 分配在 `24-27`；汇总在 `30-53`；spawn/restart/30 秒监控在 `71-187` | 增加 `--mode staged`，监督 stager、GPU worker 和 publisher 角色；记录阶段指标和 scratch 水位 |
| `tools/run_japgalgame_ctc_full.sh` | 原状态目录与 16 worker 启动参数在 `5-8`、`62-72` | 增加显式 legacy/staged 入口；保持现有 legacy 回退命令 |
| `tests/unit/test_galgame_qwen_ctc.py` | reshard、render、原子发布测试在 `66-160` | 增加 chunk 排序、源指纹、空间水位、claim/recovery、publisher 幂等与不覆盖测试 |
| `tests/unit/test_galgame_qwen_ctc_supervisor.py` | GPU 映射和完成状态测试在 `9-38` | 增加角色生命周期、停止顺序、状态汇总、restart limit 和 staged/legacy 兼容测试 |
| `docs/japgalgame-qwen-ctc-20260928.md` | 当前运行语义和性能证据在 `3-41` | 记录选定参数、A/B 数据、生产命令和回退命令 |
| `docs/alignment-issues.md` | `AGENTS.md` 指定的唯一 ledger | 仅当测试发现新的输出发布、边界、静音、标点或能量问题时追加或更新相同根因条目 |
| `tools/audit_textgrid_pauses.py` | 审计输出与失败语义在 `60-84` | 不改变；仅用于符合五轨 MFA schema 的纠正件，CTC 两轨输出另做结构、时长和哈希校验 |

## Numbered requirements

1. **R1 — 输出兼容性：** staged 和 legacy 对相同成功输入产生同名、语义等价的 TextGrid；既有 final 文件不被覆盖。

2. **R2 — 有界 staging：** 远端 WAV/TXT 只读取一次进入本地 chunk；scratch 默认不超过 32 GiB，低于 350 GiB 可用空间时停止取新数据。

3. **R3 — I/O 局部性：** 调度器按最终输出父目录成组处理，单次建立该目录既有文件集合；publisher 同一时刻只由一个分区处理该目录。

4. **R4 — 流水线解耦：** stager、GPU worker 和 publisher 可独立推进并受 backpressure 控制；GPU worker 不直接读取 CIFS WAV。

5. **R5 — 可恢复性：** 在 stage、align、result-ready 和 publish 中断后都可恢复；已发布文件跳过，未发布 result bundle 可继续发布，损坏的 `.part` 不计成功。

6. **R6 — 可观测性：** 每 30 秒记录阶段吞吐、远端读取字节、队列深度、scratch 占用、可用磁盘、align 延迟、publish 延迟、失败原因和 GPU 快照。

7. **R7 — 回退能力：** 原 full16 状态和 legacy 命令保持可用；staged 未达门槛时可停止并恢复 legacy，且 staged 已发布结果由 legacy 正确识别。

8. **R8 — 性能门槛：** 真实 CIFS 端到端发布吞吐至少达到 32.5 条/秒和匹配 baseline 的 1.30 倍，两小时 endurance 中任一连续 20 分钟窗口不得低于 30 条/秒。

9. **R9 — 正确性门槛：** 不产生新的 transfer/publish 错误类型；失败率相对匹配 baseline 增加不超过 0.01 个百分点；最终计数满足 `success + failed == paired` 且 `remaining == 0`。

10. **R10 — 安全发布：** 生产切换前停止旧监督器、保留状态快照与哈希、验证新 manifest；在实际 CIFS 上验证原子 no-replace 发布原语及并发竞态测试，验证失败则禁止 staged 生产切换；发现输出发布或声学回归时按 `AGENTS.md` 更新 ledger 并运行适用的审计。

## Ordered implementation plan

### 1. 固化测试契约

负责人：实现窗口 owner。

依赖：无。

- 为 staged chunk 状态机先写失败测试。
- 覆盖 ready claim、worker 崩溃回收、result claim、publisher 部分成功后重启、既有 final 保持原哈希、磁盘水位 backpressure。
- 用 fake aligner 验证同一 manifest 在 legacy/staged 下的成功、失败和输出内容一致。
- 保留现有 catalog、reshard、render 和 atomic publish 测试。

### 2. 增加阶段指标

负责人：实现窗口 owner。

依赖：步骤 1。

- 在不改变 legacy 行为的前提下加入统一 metrics 结构。
- 计时至少包括 source listing/filter、TXT read、WAV copy、align、render、result queue、publish、checkpoint。
- 区分 `seen`、`staged`、`aligned`、`published`、`existing`、`failed`。
- supervisor 继续以 30 秒周期原子写状态。

### 3. 实现目录有序的 chunk planner 和 stager

负责人：实现窗口 owner。

依赖：步骤 1–2。

- 对 16 个本地 JSONL manifest 做 heap merge，排序键为最终 `output.parent`、文件名、shard 和原行号。
- 每个输出目录只执行一次 `os.scandir`，过滤已有 final。
- 以固定 chunk 大小写入 scratch `.part`，复制 WAV、读取和清洗 TXT、从本地 WAV 获取时长。
- 记录源路径、size、mtime、读取字节数和本地文件大小。
- 完成后将 chunk 原子改名为 ready 并更新 chunk 数据库。
- 达到 32 GiB 高水位或 350 GiB free-space floor 时暂停。

### 4. 实现只读本地输入的 GPU worker

负责人：实现窗口 owner。

依赖：步骤 3。

- GPU worker 长驻加载模型。
- 原子领取 ready chunk，批次只传本地 WAV 路径。
- 保留现有 batch 失败二分策略，见 `tools/galgame_qwen_ctc.py:295-319`。
- 将 TextGrid 内容、目标路径、结果哈希和错误记录写入单个 result bundle。
- result bundle 原子可见后才释放输入 chunk。
- worker 异常时将 claim 恢复为 ready；不把部分结果计入完成。

### 5. 实现 publisher 和幂等恢复

负责人：实现窗口 owner。

依赖：步骤 3–4。

- publisher 按输出父目录哈希分区，避免两个 publisher 同时写同一目录。
- 对每项先检查 final；已存在则记录 existing 并保留原哈希。
- 新输出先写同目录临时文件，再使用已在实际 CIFS 上验证的原子 no-replace 发布原语（例如支持时的 `renameat2(RENAME_NOREPLACE)` 或原子 hardlink claim）；目标出现 `EEXIST` 时只记录 existing，绝不回退到 `os.replace`。启动独占锁防止新旧监督器重叠，但锁不替代 no-replace；若挂载不支持可靠原语，staged 模式不得投入生产。
- publisher 崩溃后重新读取 bundle；已发布项跳过，其余继续。
- 整个 bundle 完成后才写 published chunk 状态并允许清理本地 bundle。
- 所有失败保留明确 phase、exception type、源路径和目标路径。

### 6. 扩展 supervisor 和启动脚本

负责人：实现窗口 owner。

依赖：步骤 2–5。

- 新增显式 `--mode legacy` 和 `--mode staged`。
- staged 模式分别监督一个 planner/stager、8 或 16 个 GPU worker、1–4 个 publisher。
- 停止顺序为 stager、GPU worker、publisher；给 publisher 有界排空时间后保留 scratch。
- 旧 supervisor、状态文件和启动命令保持兼容。
- 启动前验证 scratch marker、状态目录、模型路径、磁盘空间、manifest 哈希和旧 supervisor 已停止。

### 7. 运行 correctness canary 和故障注入

负责人：验证 owner。

依赖：步骤 6。

- 固定 4,096 条真实样本，在隔离本地输出根分别执行 legacy 和 staged。
- 对所有成功项先比 SHA-256；若字节不同，解析两层 tier 并以 1 微秒容差比较边界、标签和总时长。
- 在四个阶段分别发送 SIGTERM：复制中、align 中、result-ready 后、发布一半后。
- 每次重启后验证 final 无截断、既有 sentinel 哈希未变、所有项恰好归入 success 或 failed。

### 8. 执行性能实验矩阵

负责人：性能验证 owner。

依赖：步骤 7。

- 使用尚未发布的真实生产记录。
- 各 cohort 按 WAV 字节 decile、类别数和样本数匹配；cohort 总字节差不超过 3%，类别数差不超过 5%。
- 单元格预热 5 分钟，正式测量至少 20 分钟且至少 30,000 个新发布项。
- finalist 采用 ABBA 顺序重复两次，减弱 CIFS 时段波动。
- 只按新发布 final 数计算端到端吞吐，不能以 staged 或 aligned 数代替。

### 9. 两小时 endurance 与生产切换

负责人：运行 owner。

依赖：步骤 8 达到 go gate。

- 新建 staged v1 状态，保留原 full16 状态。
- 运行至少两小时或发布至少 250,000 项，取较晚满足者。
- 每 20 分钟检查吞吐、失败类型、scratch、GPU、publisher backlog 和 CIFS wait。
- 通过后继续生产；失败则执行回退步骤。

### 10. 文档与 issue ledger

负责人：实现窗口 owner。

依赖：步骤 7–9。

- 在运行文档记录实际参数、基线、结果、选择依据、状态目录和回退命令。
- 若发现输出发布、TextGrid、边界、静音、标点或能量问题，更新 `docs/alignment-issues.md` 的相同根因条目，保留历史证据，并区分自动检查与人工语音判断。

## Experiment matrix

| Cell | 输入/输出 | GPU worker | Batch | Stage worker | Publisher | Chunk | 目的 |
|---|---|---:|---:|---:|---:|---:|---|
| E0 | CIFS 输入，CIFS final | 16 legacy | 16 | 0 | worker 内联 | 原行为 | 30 分钟匹配基线 |
| E1 | 预置 ext4 输入，ext4 输出 | 8 | 16 | 0 | 本地 | 512 | 单 worker/卡 compute ceiling |
| E2 | 预置 ext4 输入，ext4 输出 | 8 | 32 | 0 | 本地 | 512 | batch 32 ceiling 与显存风险 |
| E3 | 预置 ext4 输入，ext4 输出 | 16 | 16 | 0 | 本地 | 512 | 两 worker/卡是否仍有计算收益 |
| E4 | CIFS staged 输入，CIFS final | E1–E3 最优 | 最优 | 4 | 1 | 256 | 保守 I/O 并发 |
| E5 | CIFS staged 输入，CIFS final | 最优 | 最优 | 8 | 2 | 512 | 默认候选 |
| E6 | CIFS staged 输入，CIFS final | 最优 | 最优 | 16 | 4 | 1024 | 检查 CIFS 饱和点 |
| E7 | CIFS staged 输入，CIFS final | E4–E6 最优 | 最优 | 最优 | 最优 | 最优 | ABBA 重复和两小时 endurance |

选择规则：

- E1–E3 只决定 GPU worker 和 batch，不计入端到端提速。
- E4–E6 中选择达到吞吐门槛且 stage/publish 并发最低的配置。
- 若更高并发吞吐提升小于 5%，选较低并发。
- 任一配置出现新 transfer/publish 错误、scratch 越界、既有 final 哈希变化或恢复失败，直接淘汰。
- 若所有 staged 配置低于 32.5 条/秒，停止生产切换，保留 legacy。

## Observable acceptance criteria

- **AC1：** 4,096 条 parity canary 中，legacy/staged 成功集合和失败分类相同；成功输出字节相同，或解析后 tier、标签、边界和总时长在 1 微秒内相同。
- **AC2：** 预置 sentinel TextGrid 在 staged canary 前后 SHA-256 完全一致；同一目标的两个并发 publisher 和外部 writer 竞态测试在实际 CIFS 上只允许一个创建成功，其他返回 existing，旧内容哈希不变。
- **AC3：** GPU worker 打开的所有 WAV 路径均位于验证过的 ext4 scratch 根；真实模型 canary 中没有 GPU worker 直接打开 `/mnt/Raw` WAV。
- **AC4：** scratch 占用从不超过配置高水位加一个最大 in-flight chunk；低于 350 GiB free-space floor 后 30 秒内不再创建新 `.part`。
- **AC5：** 对每个输出父目录，planner 的远端目录扫描次数为 1；两个 publisher 不同时 claim 同一父目录分区。
- **AC6：** 四个故障注入点重启后均无截断 final、无丢失 result bundle、无重复覆盖，最终 `success + failed == cohort size`。
- **AC7：** supervisor 状态每 30 秒包含阶段计数、各队列深度、scratch 字节、free bytes、阶段延迟和 GPU snapshot。
- **AC8：** finalist 两次 ABBA 测量的合并新发布吞吐至少为 32.5 条/秒，且至少为匹配 E0 baseline 的 1.30 倍。
- **AC9：** endurance 的每个连续 20 分钟窗口至少 30 条/秒，全部窗口中位数至少 32.5 条/秒。
- **AC10：** staged 失败率比匹配 baseline 增加不超过 0.01 个百分点，且没有新增 `transfer` 或 `publish` 根因。
- **AC11：** staged 停止后，legacy 以原 full16 state 启动，跳过 staged 已发布文件，并在 10 分钟内恢复到旧基线的 90% 以上。
- **AC12：** 最终 verifier 报告 `remaining=0`、`success + failed=6,423,108`、`missing_txt=0`、`missing_wav=0`；任何缺失 final 都出现在失败清单。
- **AC13：** 相关自动测试、shell syntax 和 diff whitespace 检查全部通过。
- **AC14：** 若后续包含符合五轨 MFA schema 的纠正件，旧 TextGrid/WAV 及 SHA-256 已保留，pause audit 有非空结果且所有未豁免样本通过；失败样本已记入 ledger。普通 Qwen CTC 两轨 TextGrid 使用 AC1、AC2、AC12 的结构、时长、哈希与缺失项校验，不能将五轨审计器的 schema 错误当成声学失败。

## Requirement-to-acceptance traceability

| Requirement | Acceptance | Verification |
|---|---|---|
| R1 | AC1, AC2 | parity canary、SHA-256、praatio 解析比较 |
| R2 | AC4 | 模拟高水位和真实 endurance 指标 |
| R3 | AC5 | planner/publisher 指标和并发 claim 测试 |
| R4 | AC3, AC7 | 打开路径审计、阶段队列与 supervisor JSON |
| R5 | AC6 | 四阶段 SIGTERM 故障注入和恢复 verifier |
| R6 | AC7 | 30 秒状态采样 schema 测试 |
| R7 | AC11 | staged 停止后启动 legacy 并观察 skip/吞吐 |
| R8 | AC8, AC9 | E0–E7 实验结果和两小时 endurance |
| R9 | AC10, AC12 | 错误分类差异和全量 verifier |
| R10 | AC2, AC13, AC14 | 状态/哈希快照、测试、audit 和 ledger 检查 |

## Verification commands and expected signals

以下 staged CLI 参数属于本实施计划的目标接口，完成实现后执行。

```bash
cd /home/user/JapanMFA
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q \
  tests/unit/test_galgame_qwen_ctc.py \
  tests/unit/test_galgame_qwen_ctc_supervisor.py
```

期望：全部通过，无 deselected failure。

```bash
cd /home/user/JapanMFA
PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q -m 'not real_models'
```

期望：退出码 0；不得低于当前文档记录的 403 passed、15 deselected，除非测试总数因本变更增加。

```bash
cd /home/user/JapanMFA
bash -n tools/run_japgalgame_ctc_full.sh
git diff --check
```

期望：两条命令退出码均为 0。

```bash
cd /home/user/JapanMFA
.runtime/envs/orchestrator/bin/python tools/galgame_qwen_ctc.py verify-state \
  --state .runtime/jobs/japgalgame-ctc-staged-v1-20260929 \
  --source-state .runtime/jobs/japgalgame-ctc-full16-20260928
```

期望：JSON 输出包含 manifest 总数 6,423,108、manifest 哈希匹配、无重复目标、无未分类项；canary 阶段按其 cohort 大小报告。

```bash
cd /home/user/JapanMFA
.runtime/envs/orchestrator/bin/python -u tools/galgame_qwen_ctc_supervisor.py \
  --mode staged \
  --state .runtime/jobs/japgalgame-ctc-staged-v1-20260929 \
  --source-state .runtime/jobs/japgalgame-ctc-full16-20260928 \
  --scratch .runtime/scratch/japgalgame-ctc-staged-v1-20260929 \
  --python .runtime/envs/asr/bin/python3.10 \
  --gpus 8 \
  --workers 8 \
  --batch-size 16 \
  --stage-workers 8 \
  --publish-workers 2 \
  --chunk-size 512 \
  --scratch-max-bytes 34359738368 \
  --scratch-min-free-bytes 375809638400 \
  --model .runtime/models/qwen3-forced-aligner-0.6b
```

期望：启动检查通过；旧 supervisor 已停止；30 秒状态中三个阶段均可见；worker 只读取 scratch WAV。

若后续另有符合五轨 MFA schema 的纠正 TextGrid/WAV 被准备到隔离目录，先保留旧产物和哈希，再执行：

```bash
cd /home/user/JapanMFA
.runtime/envs/orchestrator/bin/python tools/audit_textgrid_pauses.py \
  .runtime/canary/mfa-corrected-pairs \
  --output .runtime/canary/mfa-corrected-pause-audit.json
```

期望：输出 `files` 大于 0；无豁免样本时 `failed` 为 0。任何失败必须作为失败记录并进入 ledger。该命令要求五轨 MFA TextGrid；本任务普通两轨 CTC 文件不得送入该审计器，必须用 parity canary 与发布 verifier 检查。

## Safe rollout and checkpoint recovery

1. 记录当前 supervisor/worker JSON、manifest 和启动脚本 SHA-256。
2. 向 PID 1720239 对应的旧 supervisor 发送 SIGTERM，并等待其按现有 finally 路径终止 children 和写 final status，见 `tools/galgame_qwen_ctc_supervisor.py:169-186`。
3. 确认 16 个旧 worker 均已退出后再允许 staged publisher 启动。
4. 创建新的 staged state；hardlink 或复制 manifest 后逐个核对大小和 SHA-256，核对 `paired=6,423,108`。
5. scratch 根必须包含本运行创建的 marker 和 exact run id。恢复或清理不得作用于 marker 不匹配的目录。
6. 启动时处理状态：

   - `.part`：验证不完整后重新 stage。
   - claimed ready 且 owner PID 不存在：回到 ready。
   - 部分 result：丢弃部分文件并重新 align。
   - 完整 result bundle：直接进入 publisher。
   - 部分 publish：保持既有 final，继续剩余项。
   - published chunk：核对完成记录，不重新取源。

7. producer、consumer 和 publisher 的 checkpoint 只存本地；最终输出存在性仍是跨状态目录的恢复依据。
8. 生产继续前先完成两小时 endurance。未达门槛时不扩大运行。

## Risks and mitigations

| 风险 | 影响 | 缓解 |
|---|---|---|
| CIFS 总吞吐而非随机访问是硬上限 | staging 无显著提速 | E4–E6 达不到 1.30 倍即回退，不继续增加进程 |
| publisher 成为新瓶颈 | GPU 提速但 final 积压 | 独立测量 publish 延迟和 backlog，在 1、2、4 publisher 中选择 |
| 两个 supervisor 或外部 writer 重叠 | `os.replace` 可能覆盖已有 final | 启动前锁、PID 检查和旧 worker 清零；实际 CIFS 上的原子 no-replace 原语及竞态验证是生产硬 gate |
| 本地磁盘被占满 | 模型或系统失败 | 32 GiB cap、350 GiB floor、chunk backpressure |
| crash 后状态库与 spool 不一致 | 重算、丢结果或误计完成 | 启动 reconcile，以 final 和完整 bundle 为依据 |
| stage 源在复制时改变 | 本地输入不一致 | size/mtime 前后核对；变化即失败并重新取源 |
| chunk 太大 | 长尾、恢复重算过多 | 测试 256/512/1024，默认从 512 开始 |
| 高 stage 并发再次压垮 CIFS | 主作业吞吐下降 | 4/8/16 梯度实验，选择最小达标并发 |
| 模型 batch 改变输出 | parity 不通过 | batch/worker 选择同时受 AC1 约束 |
| 现有 358 个失败与新 I/O 失败混淆 | 错误率误判 | phase 和 exception type 分栏，对匹配 cohort 比较 |
| 工作树已有大量改动 | 误覆盖用户工作 | 仅编辑列出的文件；逐文件 diff，不清理或重置 |

## Rollback

1. 向 staged supervisor 发送 SIGTERM。
2. 等待 stager 停止；允许 publisher 在配置的排空期限内结束当前 bundle。
3. 保留 `.runtime/jobs/japgalgame-ctc-staged-v1-20260929` 和 scratch，不删除、不改名。
4. 确认 staged GPU worker 和 publisher 全部退出。
5. 直接恢复原 legacy supervisor：

```bash
cd /home/user/JapanMFA
.runtime/envs/orchestrator/bin/python -u tools/galgame_qwen_ctc_supervisor.py \
  --state .runtime/jobs/japgalgame-ctc-full16-20260928 \
  --python .runtime/envs/asr/bin/python3.10 \
  --gpus 8 \
  --workers 16 \
  --batch-size 16 \
  --model .runtime/models/qwen3-forced-aligner-0.6b
```

6. legacy worker 会重新扫描 manifest 并跳过 staged 已发布 final。确认 10 分钟内吞吐回到旧基线的 90% 以上。
7. 回退不删除 staged 已发布的有效新 TextGrid；也不覆盖任何旧 TextGrid。
8. scratch 清理属于后续独立操作，只能在 result bundle 已全部发布或明确作废、marker 和 run id 匹配后进行。

## Open Questions and blockers

| 问题 | 证据 | 影响 | Owner | 决策路径 |
|---|---|---|---|---|
| 目录有序 staging 能将 CIFS 输入提升到多少 | 随机 96 条读取超过 120 秒；未做生产干扰下的目录顺序基准 | 决定是否能达到 1.30 倍 | 性能验证 owner | E4–E6，未达门槛即回退 |
| 最佳 GPU worker 是 8 还是 16 | 远端 I/O 下 16→24 无收益，但不能说明本地输入下的 compute ceiling | 决定显存和模型副本数 | 性能验证 owner | E1 对 E3 |
| batch 32 是否保持输出等价 | 既有 64 条试验无失败，但不是全量代表，见 `docs/japgalgame-qwen-ctc-20260928.md:25-30` | 可能提高 GPU 利用率或改变结果 | 验证 owner | E2 加 AC1；不等价则用 16 |
| publisher 数量 1、2、4 哪个最优 | 当前 wchan 已出现 rename 和 lookup，但占比远低于读等待 | 决定 final 写入上限 | 性能验证 owner | E4–E6，以最低达标并发为准 |
| 32 GiB cap 是否需要缩小 | 当前约 478 GiB free，其他任务未来可能用盘 | 影响 staging 深度和主机安全 | 运行 owner | 每次启动检查 free space；低于 350 GiB 拒绝 |
| CIFS 是否支持可靠原子 no-replace 发布 | 当前 `os.replace` 会替换既有目标；锁只约束本方案进程 | 外部 writer 竞态下有覆盖风险 | 实现 owner | 在实际挂载上测试 `renameat2(RENAME_NOREPLACE)` 或原子 hardlink claim；AC2 失败则禁止 staged 生产切换 |

这些问题均有实验决策路径，不阻塞实现开始；它们阻塞生产 rollout。

## Execution checklist

- [ ] 确认 `/home/user/JapanMFA` 和本 handoff 路径。
- [ ] 重读 `AGENTS.md`，保留所有用户改动。
- [ ] 记录新的 UTC、revision、status 和引用文件哈希。
- [ ] 为 R1–R7 先写测试。
- [ ] 实现 metrics，不改变 legacy 行为。
- [ ] 实现 chunk planner、stager、GPU worker、publisher。
- [ ] 实现 staged supervisor 和启动前检查。
- [ ] 运行 targeted tests、全套非真实模型 tests、shell syntax 和 diff check。
- [ ] 运行 4,096 条 parity canary。
- [ ] 完成四阶段故障注入。
- [ ] 运行 E0–E6 并生成固定格式结果。
- [ ] 只在 AC1–AC10 全通过后开始 E7。
- [ ] 两小时 endurance 通过后才继续生产。
- [ ] 发现发布或 alignment 问题时更新唯一 ledger。
- [ ] 记录最终参数、吞吐、错误和回退命令。
- [ ] 完成全量 verifier；缺失项计为失败。
- [ ] 不提交、不推送，除非用户另行授权。

## Readiness decision and gate results

| Gate | 结果 |
|---|---|
| 指定 Sol high 规划路线 | 通过；root 已完成路由 |
| 仓库、AGENTS 和工作树发现 | 通过 |
| revision/status/UTC 记录 | 通过 |
| 代码、测试、运行状态和 I/O 证据 | 通过 |
| Facts/Assumptions/Decisions/Open Questions 分离 | 通过 |
| 范围、约束和既有工作保护 | 通过 |
| requirements 与 acceptance 全量映射 | 通过 |
| 性能实验与回退门槛 | 通过 |
| freshness 哈希复核 | 通过 |
| 目标路径冲突检查 | 通过；目标不存在 |
| 仓库修改 | 通过；规划者为零修改 |
| 生产 rollout | 未通过且预期如此；必须先完成实现、canary、A/B 和 endurance |
| handoff 写入 | 待 root 原子写入 exactly one planned file |

结论：实现交接已准备好。当前证据足以开始 staged pipeline 的实现和实验，但不足以直接切换生产运行。

## Next-window startup

1. 进入仓库：

```bash
cd /home/user/JapanMFA
```

2. 打开唯一交接文件：

```bash
sed -n '1,260p' handoffs/20260929T070108Z-japgalgame-ctc-throughput.md
```

3. 重新执行只读 freshness：

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
git rev-parse HEAD
git branch --show-current
git status --short --branch
cat .runtime/jobs/japgalgame-ctc-full16-20260928/supervisor.json
df -hT /home/user/JapanMFA /mnt/Raw
```

4. 若 revision、相关文件或运行状态已变化，先刷新受影响证据和基线；不要覆盖用户改动。
5. 从“固化测试契约”开始实施，完成正确性 gate 前不要停止当前生产作业，完成 A/B 准备后再安排独占切换窗口。