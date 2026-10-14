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
