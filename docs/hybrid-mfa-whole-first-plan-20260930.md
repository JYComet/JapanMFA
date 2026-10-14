# 实施顺序：整段批量 MFA 与按失败回退

1. 在 `tests/contract/test_mfa_runner.py` 写批量输出校验的失败用例；给 `MfaRunner` 增加返回多份 TextGrid 的安全批量入口，保持原单文件入口行为。
2. 在 `tests/integration/test_pipeline_fake_backends.py` 写带 CTC 时仍可用完整 WAV 对齐的失败用例；给 `JapanMFAPipeline` 增加只改变 MFA 输入选择的 `whole` 模式，后处理继续检查 CTC。
3. 新建 `src/japanmfa/mfa/hybrid_batch.py`：由已锁定的管线准备产物构造全局唯一词典和完整/CTC 锚点窗口批次、校验输入哈希与输出覆盖、恢复每条本地别名；锚点批次保留完整 WAV，不创建裁剪 WAV。先写对应单测和失败验证。
4. 扩展 `tools/galgame_mfa_from_ctc.py` 增加 `--alignment-strategy hybrid`：准备输入，完整批量运行并检查，按明确的拒绝原因选回退条目，仅对这些条目生成 `speaker` 层 CTC 窗口并批量对齐；每次候选保留独立目录和原因，最终只发布通过且不使共享现有合格结果退化的版本。先写选择逻辑/结果保护测试。
5. 运行定向测试、全套非真实模型测试、真实前 50 条隔离试跑和发布审计；把耗时、逐条状态及新复现记录到 `docs/alignment-issues.md`，同步到 `0922jap` 诊断目录。
