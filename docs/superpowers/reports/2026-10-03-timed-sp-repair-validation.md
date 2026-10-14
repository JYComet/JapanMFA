# JapGalgame 语音落入静音区间的修复与历史核查

更新时间：2026-10-03T10:48:42.566864+00:00。本文记录本次实际实现和证据，不替代实时核查报告。

已部署针对短切片上下文不足的失败后重试，生产回归通过。真实验证和首个生产批次均恢复了部分原失败结果。第 4 句仍未解决。冻结范围的 288062 条历史核查已全部完成，其中 75472 条旧通过结果的原 WAV/TG 哈希全部一致；19940 条仍缺历史 TXT/CTC 哈希，自动核查不等同人工音素边界真值。

## 问题发生在哪一层

处理顺序是原 WAV 与文本、原 CTC 时间戳、前端读音与音素字典、按时间切片、MFA 原生对齐、时间还原与后处理、最终结构和声能审核。SP 是输出标记，不会把原 WAV 中的语音变为静音。

十条试听源的重新准备检查确认了前端、mora、字典和别名与原请求一致。部分原生 TextGrid 已把实际有声区域留为空白，后处理将空白表达为 SP，最终声能检查因此拒绝。不能统一归因于标点或词没有转为音素。

目前至少有两类机制。短相邻切片缺少声学上下文时，扩大上下文可以恢复一部分正确对齐；另一类即使音素齐全、搜索范围扩大或使用整句上下文，模型仍把词定位到错误位置。两类不能使用一个强制填充规则处理。

## 第四句的未解决证据

源键：`ASa_Project_Karigurashi_Ren_ai/vo1_1846__ASa_Project_Karigurashi_Ren_ai`；原文本为「タクマ。」。原字典六个音素 `t a k ɯ m a` 均存在。WAV 时长 2.969375 秒，CTC 为 0.48–2.4 秒，实际裁剪 0.48–2.57 秒。

完全保留的模型、图和特征重放仍将单词压到原音频约 0.51–0.76 秒，随后留出有声空白。原裁剪 PCM 与重新从原 WAV 裁剪的 SHA 完全一致，不能归因于裁剪换错音频。扩大 beam、重中心化特征、另一路原模型、整句上下文均未解决。强制屏蔽语音帧的静音路径曾产生约 1.4 秒的元音拉长，因此已拒绝，未进入生产。

用户随后明确确认该句确实只说「タクマ」。因此不能继续将文本不匹配作为该样本的解释。原请求的六音素完整，但原生模型把词定位错误；具体声学模型内部触发仍未证明。该确认不提供逐音素边界真值，不能据此强填音素或把能量区间指定给词。该句继续保留失败，不算修复。

## 实际部署的最小修复

保留原按 CTC 分时间戳的第一轮 MFA。第一轮成功结果不重做；仅对符合条件的时间或声能失败，进行一次更长上下文重试。目标最短片段为 2.4 秒，沿用原长间隔分离规则，不跨越原硬间隔任意合句。原文、读音、词典、模型和音频来源保持。

重试虽使用更长声学上下文，最终审查仍读取原始 CTC 分段和原 0.2 秒时间约束。原成功结果不进入重试；单片段、无法合并的片段及映射准备失败不盲目重试。重试失败保留原终态原因，并另记重试原因。原声能、停顿、标点、轨道、文本和来源配对门禁不变。

生产安装仅涉及 6 个文件：`src/japanmfa/mfa/context_retry.py`、`src/japanmfa/pipeline.py`、`tools/galgame_mfa_hybrid.py`、`tools/galgame_mfa_all.py`、`tests/unit/test_mfa_context_retry.py`、`tests/unit/test_galgame_mfa_all.py`。失败后的诊断 JSON 和 SHA 嵌入完整批次报告，旧常驻外层扫描器也能同步保留；单独 context 诊断文件复制逻辑在外层脚本自然重新启动后生效，当前不依赖它。

实际部署回执：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/apply-receipt.json`。原批次全部落账后在安全间隙安装，扫描器短停 23.107 秒并恢复，健康准备和对齐子进程先正常结束。常驻模型没有重启或重新加载。80 项当前代码哈希一致，原 startup 证据保持。未改源 NAS、既有通过 TG、模型、dither、映射和门禁。

## 测试和真实验证

| 验证 | 实际结果 | 解释范围 |
|---|---|---|
| 生产相关与全非真实模型回归 | 768 passed，15 real_models deselected，22.21 秒 | 不是把真实声学测试跳过后宣称声学成功 |
| 保留原第一轮结果的 500 条完整验证 | 原 104 条通过的源集合和 TG SHA 全部不变；231 条重试、26 条恢复；370 条仍拒绝 | 第二轮确实执行私有原生 MFA；全部最终门禁运行 |
| 独立重新生成特征的 500 条完整验证 | 128 通过、372 拒绝；230 条重试、25 条恢复 | 含真实初轮和重试；dither 导致重新生成特征差异，不能直接把 128 与上一实验 130 的差归因于重试 |
| 诊断持久化与最终审核重放 | 原 104 条 SHA 不变，26 条恢复，231 份重试诊断保留 | 重用已经保留的原生输出，不冒充又一次新声学对齐 |
| 首个生产批次管线报告 | 2000 条中 1210 通过、790 筛除；533 条重试恢复 154 条 | 原第一轮通过 1056 条，同批次通过率 52.8% 升到 60.5%；全 2000 条已落账，额外 3 条 NAS 哈希抽查一致 |

首个生产批次准备约 26.700 秒，初轮与重试 MFA 合计 131.684 秒，最终审查 196.938 秒，本地候选发布 406.791 秒，管线报告计时 762.113 秒。此口径不含外层全部源检查与 NAS 发布，不能直接当端到端耗时或全量 ETA。期间观察到 NAS 元数据等待；短暂让出历史核查 I/O 未证明其为根因，后续发布已逐条推进，不能把静态读写字节计数直接判为死锁。

首批全部发布及完整落账已经验证，回执在：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/first-production-receipt.json`。只对标准发布脚本落账后的结果计入生产通过数。该批 533 次重试中 532 份后处理诊断可保留，另 1 条在原生输出缺失阶段失败，保留 missing_output 原因，不伪造后处理成功。

26 条已完整验证的历史筛除结果已通过既有标准发布入口恢复，全部 NAS SHA 和账本读回一致。回执：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-correction-receipt.json`。扫描器在安全批次间隙短停 48.784 秒并恢复；原失败记录保留，原通过结果不属于该集合，未覆盖。

## 历史数据核查范围和当前结果

冻结原账本为 288062 条：75472 条 passed、212590 条 filtered。冻结后新增生产数据单独统计，不混入旧数据准确性结论。固定账本：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-baseline.sqlite3`。

冻结范围已全部检查 288062/288062 条。75472 条旧 passed 中，55532 条自动核查通过，19940 条因缺历史 TXT/CTC SHA 标记 review_required；未发现旧通过结果的结构、停顿、声能或 WAV/TG 哈希异常。该结果不构成人工音素真值认证。

212590 条旧 filtered 中，212564 条仍需真实声学或映射重试验证其可恢复性；26 条已在冻结后合法修复。主审计最初将这 26 条记录为 nonpassed_source_has_published_grid，随后逐键与历史修复回执和当前账本比对，26 个键完全相等、均属于同一修复批次，没有未解释的额外发布。冻结审计原记录保留，追加 reconciliation.json，不倒改历史。
通过结果检查源三联身份、可用原始 SHA、CTC 与文本词序、TG SHA、轨道与文本、标点、停顿及原 WAV 声能，并检查读取期间文件变化。缺少原始三联 SHA 的旧条目标记 review_required，不能凭新算哈希倒推历史身份，也不能仅因缺证断言成品错误。

另从当时保存的完整发布报告补充比对原 WAV 和 TG SHA：全部 75472 条历史 passed 的两类哈希均一致，异常 0。补充检查使用已读取的文件哈希与原报告，不再次扫描 NAS；19940 条 TXT/CTC 原 SHA 缺口仍保留。
filtered 的源身份与终态原因核查不证明其筛除正确，不等同实际重新声学处理。全部 212590 条原最终原因已有完整报告分类：170143 条声能覆盖、21243 条音素映射、13996 条时间分歧、其余原因见 `/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-final-reasons.json`。这些是拒绝原因，不是统一的源数据质量判定。

实时主报告：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-audit/report.md`；逐项记录：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-audit/results.sqlite3`；状态：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-audit/status.json`。原发布哈希补证：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-audit/report-provenance.sqlite3` 和 `report-provenance-status.json`。历史核查已完成，自动化发送消息保持暂停。追加核对回执：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/historical-audit/reconciliation.json`。

## 接续工作与验收边界

1. 首个生产批次和 26 条历史修复的发布回执均已完成；后续交接应先读取这两份回执，不重复发布或重新启动已完成实验。
2. 冻结范围 288062 个唯一键和 75472 个旧 passed 已全部核对，26 条冻结后修复已单独对账。后续新增生产结果不混入该历史结论。
3. 对 actual issues 逐项定位；对缺历史 TXT/CTC SHA 保留未知。对 filtered 的正确性还需按真实原请求选择适用修复进行完整重试，不能宣称全部已恢复。当前已确认并发布 26 条特定历史恢复结果。
4. 第 4 句准确文本已经用户确认，仍是未解决的原生模型定位失败。已尝试的搜索范围、特征重中心化、整句上下文不再重复；后续需另行验证有独立音素时间证据的对齐方案，不能把强制时长/能量掩码当正确边界。禁止扩大允许误差或静音豁免提高通过率。
5. 自动门禁、哈希和词序一致均不等同人工音素边界真值。此前试听确认仅限实际听过的样本，不能外推所有通过或筛除结果。

原始实验、失败尝试、日志、模型/图/特征、候选 SHA 和回执统一保留在 `/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-timed-sp-repair-20261003/`。项目追加问题历史在 `/home/user/JapanMFA/docs/alignment-issues.md`；原交接设计文档保持原件，不将历史未知改写为已证明。

## 历史检查快照（已被上述完成报告覆盖）

记录时间：2026-10-03T10:53:46.968443+00:00。生产账本：{'filtered': 222556, 'passed': 85506}。冻结范围已检查 67072/288062 条，其中旧 passed 检查 45568/75472 条，当前异常 {}。原报告 WAV/TG SHA 补证已核验 45312 条、异常 {}。完整核查仍未结束；后续请以实时报告为准。

## 后续生产停机及恢复

记录时间：2026-10-03T12:35:15.563834+00:00。生产在批次 57ce145ac63a4595bdc1fc87d7544d39 的第 3 组原生对齐完成后，SQLite 导入 word_intervals.csv 时遭遇 database is locked，导致完整批次未落账。原 work、模型、日志、数据库和故障状态已保留。锁的持有者未知，未将证据快照读者追认为原因。

最小修复仅在本作业串行 resident 的 align 调用内，给自己 temporary_directory 下 sqlite3 .import 增加 .timeout 5000；不重新执行部分导入、不吞异常，持续锁仍失败；其他数据库、普通 SQL 和 G2P 不受影响。这个设置是 SQLite 锁等待策略，不是整个导入/批次 5 秒总时限。

实际测试：短暂真实读锁红灯复现；修复后短锁导入正确、持续锁仍报错、跨目录数据库不改变、异常后原调用恢复。原失败组 1488 个音频在私有真实 MFA 下完成 1488 个 TG 导出，注入 0.3 秒读锁的真实 word 导入耗时约 0.352 秒并成功。这个实验不计生产通过数，不替代完整最终审核。

独立审查通过后安装仅 2 文件：src/japanmfa/mfa/native_resident.py 和 tests/unit/test_sqlite_import_wait.py。实际生产相关 7 passed，全回归 772 passed/15 deselected（27.58 秒）；81 项生产代码哈希记录，startup 原 SHA 不变。原生模型、dither、音素/映射、质量门禁未改。回执：`/home/user/JapanMFA/.runtime/jobs/galgame-mfa-all/staged-sqlite-import-wait-20261003/apply-receipt.json`。

沿用原 progress.sqlite3 和原启动脚本恢复 after-ctc-complete 阶段；CTC 已结束，6421468 成功、1640 失败、remaining=0。故障时生产账本 86887 passed / 229175 filtered；恢复后的新进度以 live-status 为准。旧常驻进程已经随故障退出，本次恢复需重新启动常驻进程；正常后续批次仍复用常驻模型。自动发送消息仍暂停。


## 2026-10-04 CTC 假设验证

原三联重算 10 条，9 条字节一致；第 7 条局部边界改变，零时长词3→5。第 4 条批量仍0.48–2.4，单条为0.48–2.48。两个变化候选已完整私有真实 MFA/最终审核，0通过2声能拒绝，未改生产源或账本。第4句仍未修复；不排除其他CTC系统误差，但重算未解决这两条。详见 /home/user/JapanMFA/docs/superpowers/reports/2026-10-04-ctc-regeneration-verification.md。
