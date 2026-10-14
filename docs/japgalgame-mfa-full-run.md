# JapGalgame 全量 MFA 执行脚本

脚本已准备好，**目前没有启动全量 MFA**。等全部 Qwen 时间戳写完后，由操作者手动启动：

```bash
cd /home/user/JapanMFA
bash tools/run_japgalgame_mfa_full.sh
```

可先只读预览前三条完整输入，不会启动 MFA，也不会写到成品目录：

```bash
bash tools/run_japgalgame_mfa_full.sh --dry-run --max-items 3
```

正式执行前建议先用 `--max-items 500` 跑一批、查看通过率和耗时，再不带该参数继续；状态数据库会跳过同一配置下输入大小/修改时间未变化且成品哈希匹配的通过项，也会跳过输入未变化的筛除项。`--retry-filtered` 可复查已筛除的条目；管线代码修改后可用 `--reprocess-all` 强制全量重审。默认每批 500 条完整输入，整段和 CTC 锚点候选在该批的一次 MFA 调用内计算；可用 `--batch-size N` 调整，每批重启一次 MFA。

输入按 `<游戏>/wav/<相对路径>.wav`、同名 `txt/*.txt` 和 `ctc/*.TextGrid` 配对；缺少任一文件的 WAV 被略过，待时间戳补齐后下次扫描才会进入 MFA。输入 WAV 必须是单声道、16 kHz、PCM16；CTC 的两轨、原文、时长和词序在单条预检中检查。预检失败只筛掉该条；MFA 整批没有完整报告或源文件在运行中变化则停止并保留工作现场。

唯一成品目录是 `\\RS3621\Research_TTS\Data\Raw\GalgameMFA\<游戏>\<相对路径>.TextGrid`（Linux 挂载点 `/mnt/Raw/GalgameMFA`）。这里**只发布通过管线和最终声能、停顿、标点、轨道结构审核的 TextGrid**，不复制 WAV、TXT 或诊断报告。原 WAV 仍在 `JapGalgame/<游戏>/wav/`，与成品按游戏和相对主名对应。源文件大小/修改时间或配置文件变化后会重新处理；如果旧结果已不适用于新输入，会先归档到本地状态目录，再从成品目录移除。此批运行的自动审核不是人工听辨金标。

本地状态目录是 `.runtime/jobs/galgame-mfa-all/`：`progress.sqlite3` 记录每条通过/筛除和输入签名，`reports/` 保留每批完整结果和别名映射，`filtered/` 保留未通过条目的源路径、原因及可用的后处理诊断，`obsolete/` 保存被替换的旧 TextGrid。异常批次会留下 `work/<批次>/align.log` 和候选现场。重启同一命令可续跑；同一状态目录有进程锁。真实新问题须按 `AGENTS.md` 继续记入 `docs/alignment-issues.md`，不能把筛除条目当作校验通过。

本脚本使用现有 `tools/galgame_mfa_from_ctc.py` 混合管线，采用原时间轴 WAV、原 TXT 和已生成的 Qwen TextGrid，不运行 ASR 或重新生成时间戳。`tools/run_japgalgame_mfa_full.sh` 负责设定 MFA、TD-Melodic 环境并传递命令行参数。全量作业只在手动运行上述命令时开始。
