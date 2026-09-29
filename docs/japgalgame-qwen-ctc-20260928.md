# JapGalgame Qwen 逐词时间戳批处理（2026-09-28）

## 输入与输出

输入：`/mnt/Raw/JapGalgame/<游戏>/wav/<名字>.wav` 与同名 `txt/<名字>.txt`。处理使用 TXT 的日文文本作为权威文本，不调用 ASR 重写它。模型是项目内固定的原生 `Qwen3-ForcedAligner-0.6B`，在原 WAV 时间轴上预测逐词起止时间。输出：`<游戏>/ctc/<名字>.TextGrid`。每个文件有 `words` IntervalTier；Qwen 若产生零时长词，原始点时间保存在 `zero_duration` TextTier，绝不人为扩大音素/词时长。标点无独立声学时间，仍由原 TXT 保留。文件夹名称 `ctc` 沿用用户要求，实际模型是 Qwen ForcedAligner，不是 CTC 网络。

成对检查、模型错误与写入错误不会悄悄跳过。缺少 WAV/TXT 的清单项记在 `catalog_errors.jsonl`，推理失败记在每卡的 `worker_<卡号>_errors.jsonl`；不存在可用时间戳时不生成伪成功 TextGrid。既有同名 TextGrid 不被覆盖。时间戳可作后续 MFA 的分组和边界审计输入，不能直接视为音素金标。

## 作业和监控

原始目录清单位于 `.runtime/jobs/japgalgame-ctc-20260928/`。清点已完成：**560 个游戏、6,423,108 对 WAV/TXT，缺失配对均为 0**。`tools/run_japgalgame_ctc_full.sh` 已为全部游戏准备 `ctc` 目录（新建 556 个，4 个此前已存在），停止重叠的试验进程，将完整清单重分为 16 份，然后在八张卡上各启动两个持久工作进程。重分片校验得到仍为 6,423,108 条，`repaired_ctc_paths=0`，说明本批语料没有触发带点主名的旧清单问题。每进程加载一次模型，以批次 16 推理。成功文件使用同目录临时文件后原子发布；重启时会跳过已发布文件。监督器 `tools/galgame_qwen_ctc_supervisor.py` 每 30 秒核查进程心跳、GPU 显存/利用率和累计数量，工作进程异常退出时有限次重启。全量状态写在 `.runtime/jobs/japgalgame-ctc-full16-20260928/`，**当前仍在处理，不可将清点完成误写为时间戳全部完成**。

检查状态：

```bash
cat .runtime/jobs/japgalgame-ctc-full16-20260928/supervisor.json
cat .runtime/jobs/japgalgame-ctc-20260928/catalog_summary.json
tail -f .runtime/jobs/japgalgame-ctc-20260928/launcher.log
```

`supervisor.json.progress` 中 `paired` 是分母，`success` 是已存在或新生成的 TextGrid 数，`failed` 是已扫描但推理/写入失败的数量，`remaining` 是尚未扫描的配对。完成后仍需核对 `success + failed == paired`，同时单列缺少配对的 WAV/TXT；出现 `complete_with_failures` 时按错误清单修复并重跑，不降低校验门槛。

`success` 仅表示模型结果被保存为结构有效的 TextGrid，不代表所有词都具有可用于 MFA 的正时长声学锚点。对 wave2 的 256 个固定随机样本统计，零时长词占比的均值约 0.120、中位数为 0；21 条达到 50% 及以上，6 条达到 75% 及以上，其中 `CTS022013__Hulotte_Ore_no_Sugata_ga_Toumei_ni_Invisible_to_Suuki_na_Unmei` 的两个词全为零时长。此类点在 `zero_duration` 轨保留原模型证据，后续 MFA 输入筛选必须单独判定可用性，不能只看文件存在。该抽样来自一个游戏附近的清单，不推论为整个语料的错误率。

## 已完成的预运行验证

- 8 条真实 WAV 的本地 canary：8/8 成功，所有 TextGrid 可由 `praatio` 解析；零时长词保存在独立点层。
- 共享目录 canary：`0verflow_Shiny_Days/ctc/01-00-a00-0060__0verflow_Shiny_Days.TextGrid` 已原子写入并可读取。
- 64 条吞吐测试：单 GPU 批次 16/32 均无失败；这只是短音频样本，不能直接推算全量完成时间。
- 6,400 条每卡双进程试验：6,397 条成功，3 条拒绝；三条已在 `docs/alignment-issues.md` 的 JA-011/JA-012 逐一分析。增加到每卡三进程时，共享盘元数据操作开始明显排队，因此全量计划固定为每卡两进程。
- 将上述 6,400 条试验清单重分为 16 份并实际运行全量配置：16 个工作进程全部走完清单，6,397 条已存在的 TextGrid 被识别，3 条真实模型失败再次被拒绝；监督器正确返回 `complete_with_failures`，没有把失败计为成功。
- 从已完成的 6,400 条清单固定种子随机抽取 128 条：128/128 个共享盘 TextGrid 可重新解析，文件名与 WAV 主名对应，均有 `words` 和 `zero_duration` 两轨，顶层时长与 WAV 差距不超过 2 微秒。
- `さ、Let's go!` 的独立撇号问题已在共享目录真实重跑成功，见同一问题台账 JA-010。
- 全量作业中 `５`/`5` 宽度形式误判已按 JA-016 修复并用真实样本重跑成功。15:38 UTC 平稳重启全量监督器加载修复后，16 个进程均重新启动；已发布 TextGrid 通过恢复检查跳过，错误数不再包含该已修复样本。
- 自动测试：`PYTHONPATH=src:. .runtime/envs/orchestrator/bin/python -m pytest -q -m 'not real_models'` 最近一次为 403 passed、15 deselected；`bash -n tools/run_japgalgame_ctc_full.sh` 与 `git diff --check` 均通过。

## 2026-09-29 共享盘吞吐复测

在全量作业稳定运行时，每 2 秒采样一次、共 12 次：八卡 GPU 利用率均值分别约为 5.3%、0%、6.5%、0%、0%、0%、1.6%、4.9%，大多数采样点为 0%。16 个工作进程的等待位置以 CIFS `wait_for_response`（129 次）与 `folio_wait_bit_common`（47 次）为主；同一时间全量进度约 25.5 条/秒。显卡都加载了模型，但当前瓶颈是共享盘的小文件读写/元数据响应。

从全量清单中抽取与当前进度不重叠的 4,000 条，在每张卡额外加一个进程作短测。稳定阶段原 16 进程降到约 17–18 条/秒，新增 8 进程约 7 条/秒，合计约 24–25 条/秒；比原配置没有可靠增益。已停止这组试验，保留其成功写出的 912 条 TextGrid，主作业到达时会跳过。停止后原作业重新接近 24 条/秒。继续增加同类 GPU 进程不能说明算力被充分利用；若要显著提速，应先改变共享盘 I/O 路径并证明发布/恢复仍安全。
