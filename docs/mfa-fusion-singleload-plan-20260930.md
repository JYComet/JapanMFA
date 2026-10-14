# 日语逐词时间戳融合与单次 MFA 加载实施方案

目标是在不放松既有声能、标点和六轨审计的条件下，移植旧项目可验证的逐词 MFA/CTC 仲裁，并把整段与锚点候选放进同一次 MFA 调用，避免二次模型启动。已有 50 条试验表明：双候选 100 份语料一次 MFA 为 25.85 s；原来 50 条整段加 14 条回退两次 MFA 合计 42.50 s。两次方案都得到 40/50 自动通过，但单次加载改变了 `0020`、`0055` 的个别结果，因此候选不能无条件替换旧成品。

1. 在 `tests/unit/test_mfa_hybrid_batch.py` 先写失败测试，再给 `src/japanmfa/mfa/hybrid_batch.py` 增加双语料构造器：完整 WAV 两种视图共用一份全局唯一词典；语料文件名区分整段与锚点；严格验证输入 WAV 哈希和输出覆盖。`tools/galgame_mfa_hybrid.py` 只调用一次 `MfaRunner.align_many`，先审查整段，再只对失败项读取已经算好的锚点结果。报告分别记录总候选数、实际用到的回退条目与一次 MFA 耗时。
2. 在 `tests/unit/test_mfa_word_fusion.py` 先写 `0007` 真实起音不被 0.3 s 阈值拉回、CTC 零时长不缩放、CTC/Sudachi 不同分词不按索引错配、安静边界可收缩、连续有声边界可扩张等失败测试。`src/japanmfa/mfa/word_fusion.py` 按源文本字符跨度匹配词，只在 0.15–0.30 s 差异且声能、相邻词、标点允许时调整候选边界；内部音素按单词保持顺序做有界重映射。>0.30 s 或无证据的冲突只记录并交给锚点候选，绝不靠比例拉长发声穿过安静区。
3. 在 `tests/integration/test_pipeline_fake_backends.py` 先写跨轨投影与诊断测试，再把融合接在 `JapanMFAPipeline` 的 MFA 解析之后、后处理之前。保留原始 MFA 边界和 CTC 边界在报告中，最终输出仍由同一组音素注释生成 `words`、`phones`、`phone_kana`、`phone_tone`；原声能、相邻停顿、标点和时间戳拒绝规则全部执行。
4. 隔离重跑同一前 50 条，与旧 `dither=1.0` 双批方案逐条对照。只发布通过所有正式审计的新成品，旧共享成品保持哈希不变；失败包留证据。记录耗时、改动边界、自动通过/拒绝差异及仍需人工听审的范围到 `docs/alignment-issues.md`，同步到 `0922jap` 诊断目录。
