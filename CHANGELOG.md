# 更新日志

版本号两处同步：`src/__init__.py` 的 `VERSION`、`src/blender_manifest.toml` 的 `version`。

## 1.8.0

- **每段自带音轨**：每段渲完立刻截本段音频 → `atempo` → mux 回段文件（画面 `-c:v copy` 不重编），
  段文件单独拿出去也有属于自己的声音；拼接成片时用 `-an` 丢掉段内音轨，再贴一条连续音轨。
  新增 `_resolve_audio_mode()` / `_audio_window()` / `_segment_audio()`。
- **段号修正**：原来三段工程会打印「第 25 段」「第 31 段」（误用帧任务累计下标），改回真实段序号。
- 验收：三段 1-24×1 / 25-48×4 / 49-72×1，段文件时长 1.00 / 0.25 / 1.00 s，
  频段校验 440 / 880 / 1320 Hz 各自命中；201 帧真机工程 `音轨 ✓ mean -18.8 dB`。

## 1.7.0

- **锁定界面**（`lock_ui`）：渲染时把所有 `VIEW_3D` 切线框、关叠加层与 gizmo，`_tag_redraw` 只刷侧栏。
  独立进程模式下父进程 CPU/帧 0.943→0.373 s、0.460→0.347 s（两轮配对），墙上时间不变；
  结束（成功/失败/取消）逐条还原 shading / overlay / gizmo。
- **渲染窗口当进度看**：本进程模式自动弹 Blender 渲染窗口显示实时画面，面板按模式提示有没有窗口。
- **孤儿渲染兜底**：关掉 Blender 窗口后后台渲染不再偷跑。第一版用驱动脚本内线程查父进程失败
  （渲染循环握着 GIL，线程抢不到执行权），改为独立看门狗 `_bg_watch.py`，
  用 Blender 自带 `python.exe` 每 0.5 秒查父进程存活，父进程消失即收掉渲染进程；
  另有 `atexit` 钩子 `_reap_child_on_exit()` 管正常退出。
- 验收：带锁跑完 201 帧，`VP_RESTORED True`、`max_gap 0.24`、`gaps_over_1s=[]`。

## 1.6.0

- **独立进程渲染**（默认）：`save_as_mainfile(copy=True, relative_remap=True)` 落临时副本，
  每段 `Popen([blender.exe, -b, 副本, --python, _bg_driver.py, --, job.json])`，
  父进程子线程只读 stdout 抓帧号、主线程每 0.25 s 刷面板 →
  主循环心跳 `max_gap≈0.25 s`，Windows 看门狗探测基本不再「无响应」。
- **随时停止**：停止 = `terminate()` 子进程，0.45 秒内生效，不留残留进程与半截文件。
- **子进程异常退出兜底**：第一段失败自动退回本进程渲染，再失败才报错（带退出码 + 日志尾部 + 日志路径）。
- 修「段内进度不动」：Blender 实际打的是小写 `render | Video append frame 1`，
  `_RE_FRAME` 改 `re.IGNORECASE` + 多关键词。
- 修「剩余时间来回跳」：`_eta_seconds()` 改 EMA（0.75 旧 + 0.25 新，前 3 帧直接采信）。
- 速度代价基本为零：同工程 30 帧，本进程 55.8 s vs 独立进程 57.0 s。

## 1.5.0

- **渲染 job 化**：`bpy.ops.render.render("INVOKE_DEFAULT", animation=True)` 返回 `RUNNING_MODAL`，
  `tick()` 只轮询 `bpy.app.is_job_running("RENDER")`，整段假死消失。
- 但每帧仍占主线程 1.3~2.2 s（EEVEE 的 GPU 工作跑在主线程），重帧还会闪「未响应」。
- 停顿归因实验（`tests/ssr_stall_probe.py`）：把输出从 VIDEO 换成 PNG，`max_gap` 仍 2.09 s
  → **停顿来自 EEVEE 渲染本身，不是 ffmpeg 编码**。这条结论直接推出 1.6.0 的独立进程方案。

## 1.4.4

- 修用户工程复现的真 bug「第 1 段没有产出视频文件」：每段使用独立 rawdir，
  避免上一轮同名文件被覆盖导致差集为空。
- 用户真实工程 0–200 帧真机跑通：201 帧 → 6.70 s mp4 + AAC，
  音频与源 AAC 波形对齐（lag 0 样本，corr 0.9999）。

## 1.4.3 及更早

- 分段渲染 + ffmpeg 拼接、视频直出 / PNG 序列、音频四模式、画质档位、实时进度、
  成片 dB 复检、`legacy/render_segment_speed.py` 纯脚本版。
