# 交接文档 · Blender 分段倍速渲染插件（seg_speed_render）

> 换设备继续开发时，**先读完这一份**。所有踩过的坑都记在第五节，重踩一遍要花好几个小时。
>
> - 当前版本：**v1.8.0**（`src/__init__.py`，2422 行）
> - 交接时间：2026-11-07
> - 上一台机器：Windows，`D:\Program Files\Blender Foundation\Blender 5.2\`
> - 本文件在 `docs/` 下，仓库根目录结构/安装/用法见 [`../README.md`](../README.md)，版本历史见 [`../CHANGELOG.md`](../CHANGELOG.md)

---

## 一、这个项目是什么

一个 Blender 扩展。让**同一条时间线**里，不同帧区间用不同的**帧步长**渲染：

| 段 | 帧区间 | 步长 | 效果 |
|---|---|---|---|
| 1 | 1–1000 | 1 | 正常速度 |
| 2 | 1001–3200 | 4 | 4 倍速，只渲 1/4 的帧 |
| 3 | 3201–3500 | 1 | 恢复正常速度 |

渲完自动用 ffmpeg 拼接成一个成片，并按段自动变速音频。

**用户是视频创作者，不会写代码**。所有交付必须是：装上去、按 N、点按钮就能用。

---

## 二、核心原理（为什么必须这么绕）

`scene.frame_step` 是**全局标量，不能打关键帧**，无法在一条时间线上分段。所以唯一路线是：

```
按段分别渲染 → 每段独立 frame_step → 得到若干个视频片段 → ffmpeg 拼接
```

**倍速是"免费"的**，靠这一点实现：

- 输出的每一段都用**同一个 fps** 编码
- 段 2 是 2200 帧按步长 4 采样 = 550 帧，用 24fps 播 = 22.9 秒
- 但原本 2200 帧应该是 91.7 秒
- → 播放时自然变成 4 倍速

**不需要任何变速滤镜，画面和音频的时间轴天然对齐。**

音频要单独处理：把原音频按「段的源时间区间」截出来，用 `atempo` 压缩到「段的输出时长」，再按段顺序拼回去。

---

## 三、当前状态：做到了什么

### 已验证通过（真机 EEVEE，非模拟）

| 功能 | 状态 |
|---|---|
| 多段渲染 + 拼接成片 | ✅ 三段 1-24×1 / 25-48×4 / 49-72×1 → 54 帧 / 2.25 秒 / 精确匹配 |
| 视频直出（不落 PNG 序列） | ✅ Blender 直接出 mp4，段文件拼完自动删 |
| PNG 序列模式（可选） | ✅ 连续编号 `shot_00000…` + 自动合成 |
| 音频：VSE 场景混音 | ✅ 频率标记法验证，440Hz/1320Hz 位置准确 |
| 音频：外部文件 | ✅ mp3/wav 均可，含源文件静音体检 |
| 音频：自动模式 | ✅ 有 VSE 条带用 VSE，没有退回文件 |
| 音频：跨场景取音频 | ✅ 音频在场景 B、渲染场景 A，可正常取用 |
| 音频：变速跟随 | ✅ 4 倍速段音频同步压缩（atempo 链） |
| 成片复检 | ✅ mux 后回头测 dB，静音就报失败而不是假装成功 |
| 实时进度 | ✅ 段内百分比 / 当前帧 / 已用 / 剩余，每帧刷新 |
| 帧率单一来源 | ✅ 面板 fps 与场景 fps 同步，渲染时临时改、结束还原 |
| 画质档位 | ✅ 5 档 CRF17/20/23/26/29，实测码率表见第七节 |
| 干净环境安装 | ✅ 临时 `BLENDER_USER_RESOURCES` 装 zip → `STATUS Installed` |
| **用户真实工程 0–200 帧** | ✅ v1.4.4 真机跑通：201 帧 → 6.70 秒 mp4 + AAC 音轨，音频与源 AAC 波形对齐（lag 0 样本，corr 0.9999） |
| **渲染时界面不卡（v1.5.0）** | ✅ 渲染 job 化：整段 270 秒的假死消失，主循环每帧都回来（实测 `max_gap=2.22s`） |
| **渲染时界面零卡顿（v1.6.0）** | ✅ 独立进程渲染：主循环心跳 `max_gap≈0.25s`（1725 次心跳 / 201 帧），Windows 看门狗 235 次探测仅 2 次短暂无响应（启动存副本、收尾合成） |
| **随时停止（v1.6.0）** | ✅ 点停止 0.45 秒内杀掉后台进程，无残留进程、无半截文件 |
| **后台进程被外力杀掉** | ✅ 自动退回本进程渲染并完成（真机实测：杀 PID → 退出码 4294967295 → 改回本进程 → 正常出片） |
| **多段 + 音频（v1.6.0 回归）** | ✅ 三段 1-24×1 / 25-48×4 / 49-72×1 走独立进程 → `完成：final.mp4 ＋音轨 ｜ 时长 2.25 秒 ｜ mean -30.1 dB` |
| **锁定界面（v1.7.0）** | ✅ 渲染时视口切线框、关叠加层、只刷侧栏；父进程 CPU/帧 0.943→0.373 s、0.460→0.347 s（两轮配对），墙上时间不变；结束 shading/overlay/gizmo 全部还原 |
| **渲染窗口当进度看（v1.7.0）** | ✅ 本进程模式自动弹 Blender 渲染窗口显示实时画面；面板按模式提示有没有窗口 |
| **带锁跑完用户工程 201 帧（v1.7.0）** | ✅ 367.5 s 出片 6.700 s（201 帧 + AAC）；`VP_RESTORED True`、`max_gap 0.24`、`gaps_over_1s=[]` |
| **关窗口不留孤儿进程（v1.7.0）** | ✅ 外部 `Stop-Process -Force` 杀父进程 → 1 秒内后台渲染被看门狗收掉，进程数归零 |
| **每段自带音轨（v1.8.0）** | ✅ 三段回归：`seg_01_x1.mp4` / `seg_02_x4.mp4` / `seg_03_x1.mp4` 各自 `h264 + aac 48k 2ch`，时长 1.00 / 0.25 / 1.00 秒；频段校验 440 / 880 / 1320 Hz 各自命中 → 段文件单独拿出去也有属于自己的声音 |
| **段号显示（v1.8.0）** | ✅ 原来三段工程会打印「第 25 段」「第 31 段」（用了帧任务累计下标），改回真实段序号 |
| **1.8.0 真机 201 帧（用户工程 debug.blend）** | ✅ 第 1 段渲完立刻 `已合上本段音轨：seg_01_x1.mp4（6.70 秒）`；段文件与成片都是 `h264 1920×1080 + aac 48 kHz 2ch`、6.700 s；段音量 mean −18.8 dB / max −1.3 dB；成片 `音轨 ✓ mean -18.8 dB`；`max_gap 0.43`、`gaps_over_1s=[]`、`VP_RESTORED True` |

### v1.5.0 / v1.6.0：把「渲染时界面无响应」彻底解决

用户原话：**「那渲染时界面无响应的问题呢？」**

**第一层根因**：`_tick_video` 里 `bpy.ops.render.render(animation=True)` 是阻塞调用，
整段（用户工程 4.5 分钟、全片 15 小时）期间主循环停摆，Windows 直接把窗口标「未响应」。

**v1.5.0 修法**：改成 `bpy.ops.render.render("INVOKE_DEFAULT", animation=True)`
（返回 `{'RUNNING_MODAL'}`，渲染进 Blender 的 Render job），`tick()` 只轮询
`bpy.app.is_job_running("RENDER")`。实测整段假死消失，但**每渲染一帧主线程仍被占住
约 1.3 秒**（EEVEE 的 GPU 工作跑在主线程），心跳 `max_gap=2.22s`、Windows 探测 153 次挂起 8 次。

**停顿归因实验**（`tests/ssr_stall_probe.py`）：同一帧段把输出从 VIDEO 换成 PNG，
`max_gap` 仍是 2.09s、每帧 1.8~1.95s → **停顿来自 EEVEE 渲染本身，不是 ffmpeg 编码**。
也就是说：只要还在界面进程里渲，单帧超过 5 秒的重场景就还会闪「未响应」。

**v1.6.0 修法**：新增面板开关 **「渲染执行方式：独立进程 / 本进程」**（默认独立进程）。
- `bpy.ops.wm.save_as_mainfile(filepath=..., copy=True, relative_remap=True)` 把当前场景
  另存一份临时副本（不动用户文件、不改当前路径、相对路径仍指向原贴图/声音）
- 每段 `subprocess.Popen([blender.exe, -b, 副本.blend, --python, _bg_driver.py, --, job.json])`，
  `CREATE_NO_WINDOW` 不弹黑框；`_bg_driver.py` 由扩展自动生成，负责帧范围/步长/快门/fps/输出路径
- 子线程 `_pump_child` 只读 stdout 的 `Video append frame N` 更新帧号（**不碰 RNA**），
  主线程 `tick()` 每 0.25 秒发一次面板进度
- 停止 = `terminate()` 子进程，立即生效（不再「等本段渲完」）
- 子进程异常退出：第一段失败则自动改回本进程渲染（`self.use_subproc=False`），
  仍失败才报错，报错里带退出码 + 日志尾部 + `seg_speed_render.log` 路径
- 收尾删掉临时副本、驱动脚本、job.json；`_segments_tmp\seg_speed_render.log` 留着排障

**速度代价**：基本没有。同一工程 30 帧实测：本进程 55.8 秒（含启动），独立进程 57.0 秒（含两个进程启动）。

**顺手修的两个观感问题（v1.6.0 内）**：
- 段内进度不动：`_RE_FRAME` 原本大小写敏感地匹配 `Fra:` / `Append frame`，
  但 Blender 实际打的是小写 `render | Video append frame 1`，于是「段内 0/201」永远不动。
  改成 `re.IGNORECASE` + 多关键词。
- 「剩余约 x 分」来回跳：`elapsed/done*(total-done)` 是累计平均，段首几帧（建缓存、子进程启动）
  会把估计拉飞（实测 15.4 → 11.3 → 9.4 → 8.3 分）。`_eta_seconds()` 加了 EMA
  （0.75 旧 + 0.25 新，前 3 帧直接采信），数字才单调收敛。

**实测（用户真实工程 0–200，201 帧）**：
```
[seg-speed] 独立进程渲染已就绪：…\_segments_tmp\_bg_20261106_233530_25104.blend
[seg-speed] 第 1 段启动后台渲染：帧 0–200 步长 1
FINAL_TEXT 完成：seg_speed.mp4（1.2 MB） ＋音轨 ｜ 时长 6.70 秒 ｜ 音轨 ✓ mean -18.8 dB
HEARTBEAT ticks=1725 job_ticks=0 max_gap=1.95 gaps_over_1s=[1.95]
WIN_CHECKS=235 HUNG=2
```
（`job_ticks=0` 是预期的：父进程里根本没有 Render job 了。）

### v1.7.0：新增「锁定界面」

用户原话：**「新增：插件选项卡新按钮"锁定界面"，开启时 blender 的 3D 视图关闭，
以获得更好的离线渲染性能，只更新插件上的进度条」**（后来又补了一句：「调起 blender
自己的渲染窗口，这也可以直观展示进度，并且锁定了 3D 视口，这非常好」）

**做法**（`lock_ui` 开关，默认关）：
- `start()` 里渲完第一帧前 `_lock_ui()`：遍历所有 window/screen/area，把每个 `VIEW_3D`
  的 `shading.type` 存下来改成 `WIREFRAME`，`overlay.show_overlays = False`，
  `show_gizmo = False` —— 视口不再重算材质预览/叠加层，只留一张线框
- `_tag_redraw()` 增加 `panel_only` 语义：锁定时只 tag `PROPERTIES` 整块 +
  `VIEW_3D` 的 `UI/HEADER/TOOL_HEADER` 三个 region，**3D 内容区不 tag**，
  所以侧栏进度照常动、画面区不重画
- 渲染窗口（本进程模式下 Blender 自己弹的那个）不受影响，仍是实时画面 —— 面板里
  按模式给提示：本进程「会弹出渲染窗口，画面进度直接看得见」，独立进程「不弹窗口，
  进度只看此面板」
- 结束（成功/失败/取消）都走 `_restore()` → `_unlock_ui()` 逐条还原 shading/overlay/gizmo

**实测收益（30 帧 100–129，同一工程，交替跑两轮）**：

| 组 | 模式 | 锁定 | 墙上时间 | 父进程 CPU | CPU/帧 |
|---|---|---|---|---|---|
| a | 独立进程 | 关 | 62.6 s | 28.3 s | 0.943 s |
| a | 独立进程 | **开** | 58.0 s | **11.2 s** | **0.373 s** |
| b | 独立进程 | 关 | 63.0 s | 13.8 s | 0.460 s |
| b | 独立进程 | **开** | 62.2 s | **10.4 s** | **0.347 s** |
| c | 本进程 | 关 | 56.6 s | 113.4 s | 3.780 s |
| c | 本进程 | 开 | 57.6 s | 115.5 s | 3.850 s |

结论（别夸大）：**独立进程模式下父进程 CPU 减半**（两轮配对 0.943→0.373、0.460→0.347），
界面重绘不再和后台渲染抢 CPU/GPU；**墙上时间基本不变**（渲染在子进程里，父进程画不画视口
都不影响它）。本进程模式下没有任何差别 —— 渲染本身就占着主线程。
所以「锁定界面」的正确定位是：**省电/省风扇/界面更顺，顺带保证视口不抢 GPU**，
不是「让渲染变快」。

**带锁跑完整 201 帧（用户工程 debug.blend，0–200，`tests/ssr_final_lock_test.py`）**：
wall 367.5 s，`界面已锁定：1 个 3D 视图切线框` → 渲染中 `VP_DURING WIREFRAME` →
`界面已还原（1 个 3D 视图）`、`VP_AFTER == VP_BEFORE`、`VP_RESTORED True`，
`max_gap 0.24`（`gaps_over_1s` 为空，比不锁的 2.31 更稳），
成片 `seg_speed.mp4` 1,274,366 B / 6.700 s / 201 帧 + AAC 48 kHz 立体声；
收尾后 `_segments_tmp` 只剩段文件与日志，无 `_bg_*` 临时件。

### v1.7.0 顺手补的：孤儿渲染进程兜底

**发现过程**：做 201 帧验收时，用户不小心关掉了 Blender 窗口，父进程以
`0xC000013A`（关闭 / Ctrl+C）退出 —— 结果后台那个渲染子进程**照样在渲**，
独立烧了 445 秒 CPU、占 1.5 GB 内存。关一次窗口，机器就在后台偷偷满载。

**第一版修法失败**：在驱动脚本里起个线程每 2 秒查父进程 PID（`OpenProcess` +
`GetExitCodeProcess == 259`）。实测父进程被杀 10 秒后子进程还在渲 ——
因为 `bpy.ops.render.render(animation=True)` 整个渲染循环握着 Python 的 GIL，
线程抢不到执行权。**结论：需要独立进程，线程不行。**

**第二版（现在）**：
- `_WATCH_SRC` 写成 `_segments_tmp\_bg_watch.py`，用 Blender 自带的
  `<安装目录>/<版本>/python/bin/python.exe`（`_python_exe()` 探测，约 20 MB，
  比再起一个 Blender 轻得多）启动：
  `python.exe _bg_watch.py <parent_pid> <child_pid> <log>`
- 每 0.5 秒看一次：父进程没了 → `TerminateProcess` 渲染子进程并往日志写一行；
  渲染子进程自己结束了 → 看门狗自己退出（不常驻）
- 父进程**正常**退出（关窗口、文件→退出）走 `atexit` → `_reap_child_on_exit()`
- `_launch_segment()` 每起一段渲染就起一个看门狗，`_finish()` 一并删掉 `_bg_watch.py`

**实测**：`tests/ssr_parent_kill_test.py` 起 0–40 帧后台渲染，外部
`Stop-Process -Force` 杀父进程 → **1 秒内** blender/python 进程数归零，日志末尾：

```
[seg-speed] 父进程 27680 已消失，后台渲染 20068 已被看门狗收掉
```


### v1.8.0：每段渲完立刻合上本段音轨

**用户原话**：「现在片段没有声音？你是想最后合成声音吗？如果是，请改成每段合成声音」。

**原来的行为**：`seg_0N_xS.mp4` 只有画面，音轨留到最后统一贴到成片上 —— 单独把段文件
拷出去剪辑时是哑的，用户以为插件没出声音。

**现在的行为**（`_finalize_video_segment` → `_segment_audio`）：
- 每段渲完立刻截本段那段源音频（`_audio_window`）、按 1/step 做 atempo、`mux` 回段文件，
  画面 `-c:v copy` 不重编码（快，且不掉画质）
- 成片仍然走原来的「统一贴一条连续音轨」：拼接时 `-an` 丢掉段内音轨，
  避免逐段 AAC 在接缝处出现 priming 空隙；成片音轨失败时才回退成「按段拼接」`keep_audio=True`
- 段级静音不算错误（`allow_silence=True`）：用户工程开头 1 秒本来就是静音，
  以前会直接报「音轨是静音」，现在只记一笔
- 段级失败只写 `audio_fail`，不毁画面；`seg_speed_audio.log` 前几行现在就是段级记录

**顺带修的段号 bug**：`第 %d 段` 之前用的是帧任务累计下标，三段工程会打印
「第 25 段 / 第 31 段」。全部改用 `self.seg_index + 1`（临时文件名仍用 `idx`）。

**实测（`tests/ssr_3seg_rawdir_test.py`，WORKBENCH 320×180，1-24×1 / 25-48×4 / 49-72×1）**：

```
[seg-speed] 第 1 段已合上本段音轨：seg_01_x1.mp4（1.00 秒）
[seg-speed] 第 2 段已合上本段音轨：seg_02_x4.mp4（0.25 秒）
[seg-speed] 第 3 段已合上本段音轨：seg_03_x1.mp4（1.00 秒）
完成：final.mp4（0.1 MB） ＋音轨 ｜ 时长 2.23 秒 ｜ 音轨 ✓ mean -30.1 dB
TMP_LEFT ['seg_01_x1.mp4', 'seg_02_x4.mp4', 'seg_03_x1.mp4', 'seg_speed_render.log']
```

段文件探针：三个都是 `h264 320×180 + aac 48000 Hz 2ch`，`format duration` 1.000000 /
0.250000 / 1.000000；频段校验（80 Hz 带宽 + volumedetect）seg_01 在 400–480 Hz 得
-34.7 dB、seg_02 在 840–920 得 -35.5、seg_03 在 1280–1360 得 -35.6 —— 每段装的是自己那段声音。

**代价**：每段多一次 AAC 编码（192 kbps，画面不重编），201 帧段大约多 1~2 秒。

### v1.4.4 修掉的真 bug（用户工程复现）

**症状**：渲染 201 帧全部成功、`seg_000000-0200.mp4` 也写出来了，面板却报
`第 1 段没有产出视频文件（… 本段新增文件：一个新文件都没有）`，于是不加音轨、不合成片。

**根因**：Blender 视频输出名只由「前缀 + 起止帧」决定。上一轮中断留下的
`_segments_tmp\seg_000000-0200.mp4` 被本轮**同名覆盖** → 目录快照前后差集为空 →
`produced` 判空。v1.4.3 用差集本来是对的，但差集在「同名覆盖」下必然失效。

**修法**（`_RenderSession.__init__` / `start` / `_tick_video`）：
每次渲染新建专属目录
`_segments_tmp/_raw_YYYYmmdd_HHMMSS_<pid>/`，快照只在这个空目录里做；另加 mtime 兜底
（`getmtime >= raw_stamp - 2`），拿到的产物再改名成 `seg_01_x1.mp4` 存进 `_segments_tmp`。
成功收尾时删掉 rawdir；`keep_segments` 只保留段视频（音频中间 wav 用完即删）。

**顺带修的三处**：
- `_compose_video` 现在会先 `os.makedirs(dirname(video))`（用户把成片指到 `rending\com\` 这类子目录）
- 没有 ffmpeg 时单段仍能复制成片，不再整段放弃
- `_final_check` 加 `-vn`：只解码音轨，22 分钟的成片复检不用再白解一遍画面

### 待验证（用户侧）

1. 用户真实工程的**长区间**（0–40640，约 15 小时渲染）还没跑过；短区间 0–200 已闭环
2. 用户报的「没声音」在这一版已用源 AAC 实测通过（mean −18.8 dB，波形对齐），长片需再确认一次

---

## 四、代码地图

文件：`src/__init__.py`（2422 行）。行号基于 **v1.8.0**，改动后会漂移，用函数名 grep。

### 数据层

| 行 | 名字 | 职责 |
|---|---|---|
| 53 | `SSRSegment` | 单个段：`start` / `end` / `step` |
| 58 | `frame_count(self)` | 本段输出帧数 = `len(range(start, end+1, step))` |
| 64 | `_scene_items(self, context)` | 给「音频场景」下拉框动态列所有 `bpy.data.scenes` |
| 73 | `SSRSettings` | 全部设置，挂在 `scene.ssr` |

`SSRSettings` 关键属性：

```
segments: CollectionProperty(SSRSegment)
output_mode: VIDEO | PNG
render_process: SUBPROC | INPROC      ← v1.6.0：独立进程 / 本进程
lock_ui: False | True                 ← v1.7.0：锁定界面（渲染时关掉视口实时显示）
out_dir / prefix / fps / fps_base
quality: PERC_LOSSLESS | HIGH | MEDIUM | LOW | VERYLOW
audio_mode: AUTO | NONE | FILE | SCENE
audio_file / audio_scene / audio_offset / audio_volume / audio_follow_speed
auto_shutter / auto_compose / keep_segments / video_path / ffmpeg_path
progress_text / running / cancel_flag / progress / est_seconds
```

### 工具函数

| 行 | 名字 | 说明 |
|---|---|---|
| 206 | `_abs_dir` | 相对路径 → 绝对路径（相对 .blend 所在目录） |
| 228 | `_segment_frames` | 单段帧数 |
| 234 | `_total_frames` | 所有段合计输出帧数（面板统计用） |
| 238 | `_find_exe(name, explicit="")` | 找 ffmpeg：显式路径 → `shutil.which` → `~/bin` → `C:\ffmpeg\bin` → Blender 安装目录旁 |
| 261 | `_python_exe` | **v1.7.0**：找 Blender 自带的 `python/bin/python.exe`，看门狗用它，比再起一个 Blender 轻得多 |
| 278 | `_tag_redraw` | 强制面板重绘（渲染回调里靠它让字跳起来）；「锁定界面」时带 `panel_only=True` 只刷侧栏 |
| 334 | `_real_fps(s)` | `s.fps / (s.fps_base or 1.0)`，处理 23.976 |
| 342 | `_crf_of(quality)` | 档位 → CRF 值 |
| 346 | `_configure_video(scene, quality="HIGH", fps=None)` | **关键**：设 MP4/H.264/CRF/GOOD/gopsize=fps×4 |
| 373 | `_configure_png(scene)` | 切回图片序列模式 |
| 388 | `_DRIVER_SRC` | **v1.6.0**：后台渲染驱动脚本源码（写进 `_bg_driver.py` 执行） |
| 440 | `_WATCH_SRC` | **v1.7.0**：孤儿看门狗源码（写进 `_bg_watch.py`，用 Blender 自带 python 跑） |
| 513 | `_RE_FRAME` | 从子进程 stdout 抓帧号（`Video append frame N` / `Fra:N`） |
| 517 | `_pump_child(stream, sink, log_path)` | 子线程读子进程输出，只写 `sink` 字典，不碰 RNA |
| 548 | `_atempo_chain(speed)` | 生成 atempo 滤镜链（ffmpeg 单级限 0.5~2.0，超出要拆） |
| 564 | `_ffmpeg_run(ffmpeg, args, timeout=1800)` | 统一调用 + 收集 stderr |
| 579 | `_audio_stats(ffmpeg, path, duration=None)` | 返回 `(mean_db, peak_db)`，用 volumedetect |
| 605 | `target_scene(s)` | 解析 `audio_scene` 为空时用当前场景 |
| 614 | `_final_check(ffmpeg, video)` | 成片体检：`"时长 2.25 秒 ｜ 音轨 ✓ mean -24.1 dB"` |
| 644 | `_vse_report(scene)` | 打印 VSE 条带清单，诊断用 |
| 662 | `_mixdown_scene_audio(path, scene=None, ...)` | VSE 混音成 wav |
| 751 | `_concat_videos(ffmpeg, files, out_path, quality="HIGH", keep_audio=False)` | 流复制拼接，失败回落实体编码；`keep_audio=False` 时用 `-an` 丢掉段内音轨（v1.8.0） |

### 渲染会话

| 行 | 名字 | 说明 |
|---|---|---|
| 878 | `_on_render_post` | 每帧渲染完的回调（只累加 `rendered_frames`，线程安全） |
| 889 | `_on_render_progress(text=None, depsgraph=None)` | 只缓存 `stats_text`，挂 `bpy.app.handlers.render_stats` |
| 903 | `_RenderSession` | 整个渲染任务的状态机 |
| 1003 | `start()` | 存快照 → 配视频 → 注册 handler → 独立进程预备 → `timers.register(self.tick)` |
| 1049 | `_publish()` | 把进度写进 `s.progress_text` + `_tag_redraw` |
| 1066 | `tick()` | **调度器**：取消判定 → VIDEO 走 `_tick_video`，PNG 走 `_tick_png` |
| 1088 | `_apply_shutter(step)` | 运动模糊快门按 1/step 缩小（本进程模式用） |
| 1105 | `_prepare_subproc()` | **v1.6.0**：`save_as_mainfile(copy=True, relative_remap=True)` 落临时副本 + 写驱动脚本 |
| 1130 | `_tick_subproc()` | 子进程轮询 / 启动下一段 / `_after_child` 收账 |
| 1146 | `_launch_segment()` | 写 job.json → `Popen([blender, -b, 副本, --python, 驱动, --, job])` → 起读流线程 → 起看门狗 |
| 1190 | `_spawn_watcher()` | **v1.7.0**：起 `python.exe _bg_watch.py <父PID> <子PID> <日志>`，界面被强杀时收掉渲染进程 |
| 1212 | `_poll_subproc()` | 从 `child_sink["frame"]` 算段内进度 |
| 1221 | `_after_child(rc)` | rc≠0 → 第一段自动退回本进程；rc=0 → `_finalize_video_segment` |
| 1241 | `_publish_subproc()` | 独立进程模式的面板文案（`后台渲染 帧 a–b ｜ 段内 n/m`） |
| 1263 | `_stop_child()` | `terminate()` → 6 秒不退则 `kill()` |
| 1278 | `_tick_video()` | 本进程模式：渲一整段 → 定位产物 → 重命名 → 下一段 |
| 1324 | `_dispatch_render()` | `INVOKE_DEFAULT` 丢进 Render job，失败退回阻塞 |
| 1347 | `_poll_video_job()` | 轮询 `bpy.app.is_job_running("RENDER")` |
| 1376 | `_publish_job()` | 本进程模式的面板文案（用 `scene.frame_current`） |
| 1403 | `_finalize_video_segment()` | 在 rawdir 里认领产物 + 半截文件识别 + 改名 `seg_0N_xS.mp4` + **v1.8.0** 调 `_segment_audio` 给段文件合音轨 |
| 1481 | `_tick_png()` | 逐帧 `write_still`，连续编号 |
| 1555 | `_restore()` | 还原场景全部设置 |
| 1590 | `_finish(cancelled, message="")` | 收尾：杀子进程 → 还原 → 删临时副本 → 拼接 → 加音轨 |
| 2015 | `_reap_child_on_exit()` | **v1.7.0**：`atexit` 钩子，正常退出时 `terminate()` 后台渲染 |
| 1655 | `_resolve_audio_mode(s)` | **v1.8.0**：AUTO 时判定用 SCENE 还是 FILE，结果缓存到 `audio_mode_used` |
| 1676 | `_audio_window(mode, s, idx, start, end)` | **v1.8.0**：算出这一段对应的音频来源与窗口内起点 `t0`；SCENE 只混这一段 |
| 1701 | `_segment_audio(s, idx, start, end, step, seg_path)` | **v1.8.0**：截本段音频 → atempo → mux 回段文件（画面 `-c:v copy`） |
| 1778 | `_attach_audio(ffmpeg, s, video)` | 逐段截音频 + atempo + concat + mux + 复检（成片那条链路，日志带段级记录） |
| 1937 | `attach_audio_standalone(...)` | classmethod，给 PNG 合成模式复用 |
| 1950 | `_compose_video(s, elapsed)` | 拼接主流程，含成功/失败文案 |

### 算子

| 行 | bl_idname | 用途 |
|---|---|---|
| 795 | `seg_speed.add_segment` | 加段 |
| 818 | `seg_speed.remove_segment` | 删段 |
| 833 | `seg_speed.move_segment` | 上下移 |
| 856 | `seg_speed.reset_from_scene` | 用场景帧范围重置 |
| 2034 | `seg_speed.render` | 开始渲染 |
| 2081 | `seg_speed.audio_diag` | 诊断音频（VSE 条带 + 试混 + dB） |
| 2124 | `seg_speed.sync_fps` | 跟随场景帧率 |
| 2143 | `seg_speed.cancel` | 取消 |
| 2157 | `seg_speed.compose` | PNG 序列合成视频 |

### UI

| 行 | 名字 | 说明 |
|---|---|---|
| 2247 | `SSR_UL_segments` | 列表行：`起始 → 结束 ×步长` |
| 2266 | `SSR_PT_main` | 面板，`bl_label` 带版本号（`分段倍速渲染 v1.8.0`），VIDEO 模式多一行「渲染执行方式」 |
| 2407 | `register()` / `unregister()` | `CLASSES` 元组必须列全所有类 |

---

## 五、Blender 5.2 API 踩坑清单 ⚠️ 最重要的一节

**这些全是实测出来的，别凭 4.x 记忆写代码。**

### 5.1 视频输出必须先设 `media_type`

```python
# ❌ 报错：TypeError: enum "FFMPEG" not found in ('AVIF','JPEG','OPEN_EXR','PNG',...)
scene.render.image_settings.file_format = "FFMPEG"

# ✅ 正确顺序
scene.render.image_settings.media_type = "VIDEO"     # 4.5+ 引入
scene.render.image_settings.file_format = "FFMPEG"
```

切回图片序列要先 `media_type = "IMAGE"`。**保存/还原设置时 `media_type` 也要一起存。**

### 5.2 视频输出文件名会把帧范围拼进去

设 `render.filepath = ".../seg_01"`，实际产出是 `seg_01001-1000.mp4`（前缀 + 6 位起始帧 + `-` + 6 位结束帧）。

**不要猜文件名**。用渲染前后的目录快照差集，但**必须在一轮独占的空目录里做**：

```python
# __init__：每轮一个新目录，避免上一轮同名文件被覆盖导致差集为空
self.rawdir = os.path.join(self.tmpdir, "_raw_%s_%d" % (time.strftime("%Y%m%d_%H%M%S"), os.getpid()))

def _snap(d):
    return set(glob.glob(os.path.join(d, "**", "*"), recursive=True))

existing = _snap(self.rawdir)          # 空目录 → 差集必然有效
self.raw_stamp = time.time()
bpy.ops.render.render(animation=True)
new_files = sorted(p for p in (_snap(self.rawdir) - existing) if os.path.isfile(p))
video_ext = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpg", ".mpeg")
produced = [p for p in new_files if os.path.splitext(p)[1].lower() in video_ext]
```

**绝不能写死 `.mp4`**（v1.4.2 → v1.4.3 的真 bug 就是它，导致误判「第 1 段没有产出视频文件」，还连带跳过加音轨、不写日志）。

**也不能在共享目录里做差集**（v1.4.3 → v1.4.4 的真 bug）：上一轮中断留下的
`seg_000000-0200.mp4` 与本轮同名，Blender 直接覆盖 → 差集为空 → 同样报「没有产出」。
所以 1.4.4 起用 `_raw_<时间戳>_<pid>` 独占目录 + 5 行 mtime 兜底。

### 5.3 没有 `bpy.app.handlers.render_progress`

5.2 可用的渲染回调只有：

```
render_pre  render_init  render_stats  render_write  render_post
render_complete  render_cancel
```

**`render_stats` 的第一个参数是状态文本字符串**，不是 scene：

```python
def _on_render_progress(text=None, depsgraph=None):
    # text 形如 'Time: 00:01.11 (Saving: 00:00.03)'
    fr = bpy.context.scene.frame_current   # 当前帧要自己取
```

改 handler 之前先 `dir(bpy.app.handlers)` 实测，别信记忆。

### 5.4 渲染阻塞：三层事实，别再踩回去

```python
# ❌ 阻塞：整段渲完才回主循环 → 窗户整段「未响应」；15 小时片就是 15 小时假死
bpy.ops.render.render(animation=True)

# ⭕ 进 Render job：主循环活，但 EEVEE 每帧仍占主线程 1.3~2.2 秒（5 秒以上的重帧还会闪「未响应」）
bpy.ops.render.render("INVOKE_DEFAULT", animation=True)   # 返回 {'RUNNING_MODAL'}

# ✅ 零卡顿：另开 Blender 进程渲染（v1.6.0 默认），父进程只轮询子进程 stdout
subprocess.Popen([bpy.app.binary_path, "-b", tmp_blend, "--python", driver, "--", job],
                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 creationflags=0x08000000,   # CREATE_NO_WINDOW
                 universal_newlines=True, encoding="utf-8", errors="replace")
```

要点：

- `execute` 里把渲染丢给 timer 驱动（`bpy.app.timers.register(self.tick, first_interval=0.05)`），
  `execute` 自己立刻返回 `{"FINISHED"}`
- Render job 的帧范围在**启动时快照**：渲染中改 `scene.frame_end` 无效（实测 `STILL_RUNNING ... frame_end 修改无效`），
  所以「靠截断帧范围来取消」这条路是死路
- `bpy.app.is_job_running("RENDER")` 可读，但**没有 Python 侧 kill job 的 API**
- `window.event_simulate(type="ESC")` 需要 `--enable-event-simulate`，插件里用不了
- 后台进程的 stdout 是 `00:06.563  render  | Video append frame 1`，
  解析要用不区分大小写的 `re.compile(r"(?:fra:|append frame|saved:)\D{0,40}?(\d{1,7})", re.I)`
- 后台渲染**不吃 `-o` 覆盖**：媒体类型是 VIDEO 时文件名由场景内 `render.filepath` 决定，
  必须在驱动脚本里用 Python 设 `scene.render.filepath`

### 5.4.1 后台渲染的驱动脚本（`_bg_driver.py`）

```python
scene = bpy.data.scenes.get(job["scene"]) or bpy.context.scene
scene.frame_start, scene.frame_end, scene.frame_step = job["start"], job["end"], job["step"]
scene.render.filepath = job["filepath"]
with bpy.context.temp_override(scene=scene):      # 后台没有 window，必须用 temp_override 指定场景
    bpy.ops.render.render(animation=True)
```

保存副本要 `copy=True`（只写副本，不动用户文件、不改当前文件路径），
`relative_remap=True`（否则 `//sounds\C0646.aac` 这类相对路径会指到临时目录里）。

### 5.5 `bpy.ops.sound.mixdown` 是**异步写盘**

调用返回时文件还没落盘。必须轮询等大小稳定（约 0.5s）。第一版立即检查 → 误判失败 → 回落默认参数产出 49340 字节的 FLAC 头文件。

```python
bpy.ops.sound.mixdown(
    filepath=path, check_existing=False,
    container="WAV", codec="PCM", format="S16", mixrate=48000,
)
# 然后轮询 os.path.getsize 直到稳定
```

正确产物：`RIFF` 头 578638 字节 = 3.00s @48kHz 16bit stereo。

枚举已核实：
- `container` = `['AAC','AC3','FLAC','MATROSKA','MP2','MP3','OGG','WAV']`
- `codec` = `['AAC','AC3','FLAC','MP2','MP3','PCM','VORBIS']`
- `format` = `['U8','S16','S24','S32','F32','F64']`

### 5.6 `se.strips` 在 5.x 是空集合、布尔值为 False

```python
# ❌ 会掉进后备分支，报 AttributeError: 'SequenceEditor' object has no attribute 'sequences'
strips = getattr(se, "strips", None) or se.sequences

# ✅
strips = getattr(se, "strips", None)
if strips is None:
    strips = getattr(se, "sequences", [])
```

### 5.7 序列编辑器是 **per-scene** 的

音频放在场景 B，渲染场景 A 只混 A 的 VSE → 空。必须提供「音频场景」选择（`audio_scene`），或在 `_mixdown_scene_audio` 里临时 `win.scene = scene`。

### 5.8 引擎名没变

```python
sc.render.engine = "BLENDER_EEVEE"   # 5.2 仍是这个，没有 BLENDER_EEVEE_NEXT
# 可选值：('BLENDER_EEVEE', 'BLENDER_WORKBENCH', 'CYCLES')
```

### 5.9 材质节点名随语言/版本变

`mat.node_tree.nodes["Principled BSDF"]` 会 `KeyError`。测试脚本里直接：

```python
mat.diffuse_color = (r, g, b, 1)
```

### 5.10 改 `CLASSES` 元组后必须实测

曾经 `SSR_OT_audio_diag` 没进 `CLASSES`（用 `\r\n` 做替换但文件是 `\n`，静默失败）→ 面板按钮不显示、点了没反应。

验证：

```python
import bpy
print(hasattr(bpy.ops.seg_speed, "audio_diag"))
```

### 5.11 不要在文件头用 `Replace('import os', ...)` 插内容

曾经插入版本号时把 `import os` 吃掉了 → 整个模块 `NameError: name 'os' is not defined` → 面板每帧报错、渲染卡死 200s 超时。

### 5.12 视频输出不写音频

段渲染必须 `r.ffmpeg.audio_codec = "NONE"`（避免占位音轨干扰拼接），音频全部由 ffmpeg 事后加。

---

## 六、音频链路（最容易出错的部分）

### 数据流

```
源音频（VSE 条带 或 外部文件）
   ↓ 每段渲完立刻做一次：按段源时间区间截取 [-ss t0 -t dur]
   ↓                     atempo 压缩到段输出时长
   ↓                     mux 回段文件（-c:v copy -c:a aac -b:a 192k）
seg_01_x1.mp4（自带声音，单独拿出去也有音轨）
   ↓ 全部渲完：再走一遍同样流程，把整条音轨贴到拼接后的成片上
   ↓ 拼接时用 -an 丢掉段内音轨（避免逐段 AAC 在接缝处留 priming 空隙）
成片.mp4
   ↓ 复检 volumedetect
"音轨 ✓ mean -24.1 dB"
```

段级音轨（v1.8.0）和成片音轨走的是同一个 `_audio_window` / `_segment_audio`，
区别只在：段级允许静音（开场留白不算错误）、失败时只记 `audio_fail` 不毁画面。

### 关键公式

```python
t0  = (seg_start - frame_start) / fps + audio_offset   # 源音频里的起点（秒）
dur = (seg_end + 1 - seg_start) / fps                  # 源音频里截多长（秒）
speed = step                                           # 压缩倍数
```

输出时长 = `dur / step`，正好等于这一段的播放时长。

### 为什么必须复检

**静音 WAV 也有 578638 字节**。只检查文件大小会一边显示「＋音轨」一边交出无声文件。v1.3.9 起：

```python
chk = _final_check(ffmpeg, video)
if "音轨 ✓" not in chk:
    return fail("音轨已写入但复检不通过 —— %s" % chk)
```

`_final_check` 用 `ffmpeg -t DUR -i video -af volumedetect -f null -` 读 `mean_volume`：

- `> -60 dB` → 有声音
- `< -60 dB` → 几乎是静音，报失败

### 日志

每次 `_attach_audio` 都写一份 `seg_speed_audio.log` 到成片旁边，记录：面板 fps、时间线起点、声音来源、自动判定详情、每段截取区间与字节数、成片复检、最终结果。

**用户报「没声音」时，第一件事就是要这个日志。**

---

## 七、画质与体积（实测数据）

1080p / 24fps / EEVEE，地面 + 24 个随机彩色方块 + 相机环绕 + 太阳光，12 帧样本：

| 档位 | CRF | 体积 | 码率 |
|---|---|---|---|
| 几乎无损 | 17 | 295982 B | 4.74 Mbps |
| 高质量 | 20 | 194223 B | 3.11 Mbps |
| 标准 | 23 | 148262 B | 2.37 Mbps |
| 小体积 | 26 | 113769 B | 1.82 Mbps |

- CRF 每 +6，码率约减半
- CRF ±1，体积约 ±12%
- `gopsize` 从 18 帧改到 96 帧（4 秒关键帧间隔），**省 13.9%，画质不变**（640×360 / 120 帧实测：150931 B → 129930 B）

---

## 八、环境复现（换设备要做的事）

### 必备

| 项 | 版本 | 说明 |
|---|---|---|
| Blender | **5.2**（≥4.2） | 装在 `D:\Program Files\Blender Foundation\Blender 5.2\`；测试脚本已改为相对路径（`ADDON = ../src/__init__.py`），只有调用 `blender.exe` 的命令要按本机路径改 |
| ffmpeg | 任意近期版 | 需在 PATH，或放 `~/bin`，或 `C:\ffmpeg\bin` |

### 插件安装位置

```
%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\seg_speed_render\
    __init__.py
    blender_manifest.toml
```

即 `C:\Users\<用户>\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\seg_speed_render\`

### 开发时的循环

```powershell
# 1. 改 src/__init__.py
# 2. 语法检查（必做，Blender 的报错很难读）
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python-expr `
  "import py_compile; py_compile.compile(r'<abs>\__init__.py', doraise=True); print('SYNTAX_OK')"

# 3. 同步到扩展目录
Copy-Item src\__init__.py "$env:APPDATA\Blender Foundation\Blender\5.2\extensions\user_default\seg_speed_render\"

# 4. 跑测试（见下节）
```

---

## 九、测试脚本

全部在 `tests/`，都用同一套模式：

```python
# 头部：只在插件没注册时才 exec，避免重复注册报错
if not hasattr(bpy.types.Scene, "ssr"):
    exec(open(PLUGIN, encoding="utf-8").read())

# 自建场景（含相机，否则报「无法渲染，没有摄像机」）
cam = bpy.data.cameras.new("Cam")
cobj = bpy.data.objects.new("Cam", cam)
bpy.context.collection.objects.link(cobj)
cobj.location = (7, -7, 5)
cobj.rotation_euler = (1.1, 0, 0.785)
bpy.context.scene.camera = cobj

# 结尾：延时自动退出
bpy.app.timers.register(quit_now, first_interval=8.0)
```

| 脚本 | 测什么 | 通过标志 |
|---|---|---|
| `ssr_video_test.py` | 三段视频直出 + 音频文件 | `FINAL_TEXT 完成：final.mp4 … ＋音轨` |
| `ssr_png_test.py` | PNG 序列 + 合成 | 8 张 `t_00000…00007` + 成片 |
| `ssr_scene_test.py` | VSE 场景混音 | `FINAL_TEXT … ＋音轨` |
| `ssr_auto_test.py` | AUTO 跨场景取音频 | `Audio: aac (LC), 48000 Hz, stereo` |
| `ssr_silent_test.py` | 静音检测（应失败） | `（音频失败：…几乎是静音（mean -91.0 dB）…）` |
| `ssr_long_test.py` | 10 分钟长音频不超时 | `DONE in 7.0s` |
| `ssr_mp4src_test.py` | mp4 源条带提取音频 | 逐点测频 440Hz/1320Hz |
| `ssr_mp3_test.py` | mp3 直放 | `音轨 ✓ mean -24.4 dB` |
| `ssr_filemode_test.py` | FILE 模式 | `源音频体检：mean=-24.3 dB` |
| `ssr_fps_test.py` | 面板 fps 与场景 fps 同步 | `30.00 fps / 1.00 秒`、`RESTORED fps=24` |
| `ssr_bitrate_test.py` | 各档 CRF 码率 | 见第七节表 |
| `ssr_gopsize_test2.py` | gopsize 对体积影响 | 省 13.9% |
| `ssr_ui_test.py` | 实时进度文本 | `PROBE frame=120 ｜ 第 2/2 段 ｜ … 段内 100%` |
| `ssr_keep_test.py` | 保留分段文件 | 段文件不删 |
| `ssr_multiscene_test.py` | 多场景 | — |
| `ssr_mixdown_test.py` | mixdown 异步落盘探测 | RIFF/WAV 578638 字节 |
| `ssr_real_debug_test.py` | **用户真实工程** debug.blend 0–200 | `第 1 段没有产出视频文件` → 1.4.4 后变 `完成：seg_speed.mp4 … 6.70 秒` |
| `ssr_3seg_rawdir_test.py` | 三段＋倍速＋FILE 音频＋保留分段 | `2.25 秒`、`TMP_LEFT` 只有三个段文件 |
| `ssr_real_ui_test.py` | **界面卡不卡**（心跳 + 外部看门狗） | `max_gap` 与 `HUNG` 计数 |
| `ssr_stall_probe.py` | 停顿归因：视频 vs PNG 输出 | PNG 也 `max_gap≈2` ⇒ 停顿来自 EEVEE |
| `ssr_subproc_progress_test.py` | 独立进程模式段内进度 | `段内 0/30 → 29/30` |
| `ssr_subproc_cancel_test.py` | 独立进程随时停止 | `STOPPED_AFTER_CANCEL 0.45s`、`LEFTOVER_BLENDER=0` |
| `ssr_child_kill_test.py` | 后台进程被外部杀死 | 日志出现「改回本进程渲染」 |
| `ssr_inproc_timing_test.py` | 独立进程 vs 本进程耗时 | 30 帧 57.0 s vs 55.8 s |
| `ssr_invoke_probe.py` / `ssr_invoke_cancel_probe.py` / `ssr_invoke_trim_probe.py` / `ssr_invoke_stop_probe.py` | 早期探针（job 模式、ESC 取消、改 frame_end 截断） | 见 5.4 结论；仅存档 |
| `ssr_lock_test.py` | **锁定界面收益**（`SSR_LOCK`/`SSR_PROC`/`SSR_START`/`SSR_FRAMES`/`SSR_TAG`） | 渲染中 `VP_DURING WIREFRAME`、结束后 `VP_AFTER` 回 MATERIAL；写 `lock_state_<tag>.json` 的 wall / CPU / progress 采样 |
| `ssr_final_lock_test.py` | **带锁 201 帧最终验收**（心跳 + 视口三态 + 面板进度） | `VP_RESTORED True`、`FINAL_TEXT 完成：seg_speed.mp4 … 6.70 秒 ｜ mean -18.8 dB`、`max_gap 0.24` |
| `ssr_parent_kill_test.py` | **孤儿进程兜底**：外部强杀父进程 | 1 秒内 blender/python 进程数归零，日志出现「父进程 … 已消失，后台渲染 … 已被看门狗收掉」 |
| `ssr_final_accept_test.py` | 1.6.0 版 201 帧验收（无锁对照） | `max_gap 2.31`、`PROG_SAMPLES 269` |
| `ssr_recover_project.py` | **运维脚本**（不是回归）：`-- seg01` 重渲首段、`-- compose` 重拼 + 贴音轨、`-- all` 两步都做；调用插件自己的 `_configure_video` / `_concat_videos` / `attach_audio_standalone`，参数与正常流程一致 | `RECOVER_SEG01` / `RECOVER_CONCAT` / `RECOVER_AUDIO` / `RECOVER_FINAL` 四个标记 |

### 跑法

```powershell
$p = Start-Process -FilePath "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  -ArgumentList '--python', "tests\ssr_video_test.py" `
  -RedirectStandardOutput "logs\out.txt" -RedirectStandardError "logs\err.txt" -PassThru
$p | Wait-Process -Timeout 280 -ErrorAction SilentlyContinue
if (-not $p.HasExited) { $p.Kill() }
Get-Content logs\out.txt | Select-String "FINAL_TEXT|Traceback"
```

⚠️ **不要用 GUI 截图法测 UI** —— 1920×1200 全屏 PNG 会把 DSH 卡死。要验证面板文字，自己挂一个 `render_stats` 打印 `s.progress_text`。

### 频率标记验证法（验证音频位置是否正确）

```powershell
# 生成 0-1s 440Hz、1-2s 880Hz、2-3s 1320Hz
ffmpeg -f lavfi -i "sine=frequency=440:duration=1" `
       -f lavfi -i "sine=frequency=880:duration=1" `
       -f lavfi -i "sine=frequency=1320:duration=1" `
       -filter_complex "[0:a][1:a][2:a]concat=n=3:v=0:a=1" -ac 2 -ar 48000 test_freq.wav

# 在 t 秒处测频段
ffmpeg -ss 0.4 -t 0.08 -i 成片.mp4 -af "lowpass=f=600,volumedetect" -f null -
ffmpeg -ss 0.4 -t 0.08 -i 成片.mp4 -af "highpass=f=1000,volumedetect" -f null -
```

低频档 dB 高 → 该处是低频音。实测 t=0.4s 是 440Hz、t=1.6s 已是 1320Hz，证明 4 倍速段真的压缩了。

---

## 十、打包发布流程

```powershell
$ws   = "<工作区>"
$src  = "$env:APPDATA\Blender Foundation\Blender\5.2\extensions\user_default\seg_speed_render"
$dist = "$ws\dist"
$stage = "$ws\build\seg_speed_render"

# 1. 改版本号（两处都要改）
#    src\__init__.py:  VERSION = "1.8.0"
#    blender_manifest.toml: version = "1.8.0"

# 2. 组 stage
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item "$src\__init__.py","$src\blender_manifest.toml" -Destination $stage

# 3. 构建
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --command extension build --source-dir $stage --output-dir $dist

# 4. 干净环境验证
$tmp = "$ws\tmp_br"; New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$env:BLENDER_USER_RESOURCES = $tmp
& "...blender.exe" --command extension install-file -r user_default --enable "$dist\seg_speed_render-1.8.0.zip"
& "...blender.exe" -b --python-expr "import bpy; print('PANEL', bpy.types.SSR_PT_main.bl_label)"
Remove-Item Env:BLENDER_USER_RESOURCES; Remove-Item -Recurse -Force $tmp
```

期望输出：

```
STATUS Installed "seg_speed_render"
PANEL 分段倍速渲染 v1.8.0
```

### 交付三件套

| 文件 | 大小 | 给谁 |
|---|---|---|
| `seg_speed_render-1.8.0.zip` | ~26 KB | 本机已有 ffmpeg |
| `seg_speed_render-1.4.4-with-ffmpeg.zip` | ~30 MB | 换电脑 / 给别人（可选，本机不需要） |
| `INSTALL.txt` | ~5 KB | 中文安装说明（UTF-8 **带 BOM**，否则记事本乱码） |

`INSTALL.txt` 写入要用：

```powershell
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($true)))
```

---

## 十一、下一步

### 优先级 1：长区间闭环

装 1.8.0，先跑用户真正需要的那条长段（例如 0–40640 全片，约 15 小时；
建议先挑 0–900 帧 ≈ 22 分钟试一次）。核对三样东西：

1. 面板最终提示文本（成功是 `完成：xxx.mp4 ＋音轨 ｜ 时长 … ｜ 音轨 ✓ mean …`）
2. 成片旁边的 `seg_speed_audio.log`
3. 如果失败，提示里会带「当前输出格式 / 渲染路径 / 本段新增文件」

长段先决条件：`_prepare_subproc()` 会把整个 .blend **复制**一份到
`rending\_segments_tmp\_bg_*.blend`，用户工程有外部贴图/缓存时注意磁盘与路径；
若复制失败会自动退回本进程渲染（日志有「独立进程准备失败」）。

### 优先级 2：可疑点

- **收尾合成仍是同步 ffmpeg**：拼接 + 加音轨在 `_finish()` 里跑，长片最后可能卡
  十几秒到几十秒（1.5.0 那次外部探针抓到的 8 次 HUNG 里就有一部分是它）。想彻底解决就把
  `_compose_video` 也挪进子进程或线程，但 ffmpeg 本身已经在独立进程里，只是主线程在 `wait()`。
- 用户 VSE 里两条 SOUND 都是 `0-40640`，**并行叠着**而不是串行 → 叠加导致 `peak=0.0 dB` 削顶。建议 `audio_volume` 调到 0.8，或让用户在 VSE 里把它们排成前后相接
- 用户的音频实际是「两段视频去掉画面」，可以建议直接用 ffmpeg 合成一条 wav 走 FILE 模式，绕开 VSE 的复杂度：
  ```powershell
  ffmpeg -i A.mp4 -i B.mp4 -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1" -ac 2 -ar 48000 full.wav
  ```

### 优先级 3：可以加的功能

- 断点续渲（目前中断就从头来；独立进程模式下段文件已落盘，可复用 `seg_0N_xS.mp4` 跳过已完成段）
- 每段单独指定分辨率（低分辨率段省更多时间）
- 成片加背景音乐（现在是替换而非混合）
- 段列表导入/导出预设
- 「锁定界面」再进一步：渲染时把 3D 视口整个换成一张静态缩略图（要小心 context 里的 area 引用）
- 看门狗目前只盯 PID，可加一条「父进程 win32 事件句柄」用 `WaitForSingleObject` 实时等，省掉 0.5 秒轮询

---

## 十二、已知限制（跟用户讲清楚过）

1. **倍速必然缩短成片**，这是原理决定的
2. **视频直出不可断点续渲**
3. **运动模糊快门**要按 1/step 缩小，插件已自动处理（`auto_shutter`）
4. **物理/粒子/流体缓存**必须先在步长 1 下烘焙完，否则跳帧会错位
5. 成片**默认无音轨**（`audio_mode=NONE` 时），要声音就选 AUTO/FILE/SCENE
6. **SCENE 模式**下如果画面来自 3D 场景，要确认「输出属性 → 后期处理 → 序列编辑器」的状态：
   实测 5.2.3 里 VSE **只有声音条带**时，`use_sequencer=True` 仍然正常渲染 3D 画面（用户工程已验证，YAVG≈140 非黑屏）；
   只有 VSE 里放了**视频条带**时才会改成输出 VSE 内容。真遇到黑屏再关这个开关。
7. **独立进程模式**（默认）比本进程多占一份内存/显存：后台 Blender 是完整第二个实例。
   显存吃紧（例如 4K + 大贴图）时切回「本进程」，代价是渲染期间面板每帧顿一下。
8. **收尾合成阶段仍会短时占用主线程**（ffmpeg 拼接/混流），长片末尾可能「未响应」几秒到几十秒；
   渲染阶段本身不卡。
9. **「锁定界面」只省界面开销，不提速**：独立进程模式下父进程 CPU 减半、界面更顺，
   墙上时间不变（活是子进程干的）；本进程模式下没有差别。另外锁定时 3D 视口是线框，
   想边渲边看画面就切「本进程」，看 Blender 自己弹的渲染窗口。
10. **关掉窗口时的孤儿兜底靠外部看门狗**：`_bg_watch.py` 用 Blender 自带 python 每 0.5 秒
    查父进程存活。极端情况（看门狗自己被系统杀掉、或用 `-b` 无界面跑完整个渲染）不覆盖；
    真要确认，用任务管理器看有没有第二个 `blender.exe` 在吃 CPU。
11. **强制断电 / 蓝屏**后 `_segments_tmp` 会留 `_bg_*.blend`、`_bg_driver.py`、`_bg_watch.py`：
    这些只是垃圾文件，下次渲染会重新生成，可以手删；`seg_speed_render.log` 建议留着排障。
12. **每段音轨（v1.8.0）每段多一次 AAC 编码**（192 kbps，画面是 `-c:v copy` 不重编），
    201 帧段大约多 1~2 秒；成片仍然统一贴一条连续音轨，段内音轨在拼接时用 `-an` 丢掉。
    所以「段文件有声音」和「成片有声音」是两条独立链路，任意一条失败不影响另一条。
13. **段文件与成片不是同一份编码**：段是 Blender 直出的 mp4（每段从 IDR 起），
    成片是 `-c copy` 拼接（不行才重编）。单独拿段去剪辑没问题，但别把段和成片混着对比码率。
14. **不要手动删 `_segments_tmp` 里别人正在渲的东西**：这一轮踩过一次 —— 清理临时目录时
    误删了用户正在跑的段文件与 `rending\com`，后台副本 `_bg_*.blend` 也一起没了。
    正确做法是先确认没有 `blender.exe` 在跑，或只删自己进程的 `_raw_<时间戳>_<pid>` 目录。

---

## 十三、文件清单

```
blender-seg-speed-render/
├─ README.md                   项目说明（先看这个）
├─ CHANGELOG.md                版本历史
├─ LICENSE                     GPL-3.0
├─ docs/
│  └─ HANDOFF.md               ← 本文件
├─ src/
│  ├─ __init__.py              插件主文件（2422 行）
│  └─ blender_manifest.toml    manifest（version 一处）
├─ dist/
│  ├─ seg_speed_render-1.8.0.zip
│  └─ INSTALL.txt              中文安装说明
├─ tools/
│  ├─ make_test_tones.py       生成 test_freq.wav / test_tone.wav（频率标记法素材）
│  └─ probes/probe_debug_blend.py   早期 Blender API 探针（存档）
├─ logs/                       运行日志（git 忽略）
├─ tmp/                        渲染样本与测试输出（git 忽略）
├─ build/                      打包 stage（git 忽略）
├─ tests/                      34 个回归脚本（v1.6.0 新增 ssr_real_ui_test /
│                              ssr_stall_probe / ssr_subproc_progress_test /
│                              ssr_subproc_cancel_test / ssr_child_kill_test /
│                              ssr_inproc_timing_test；v1.7.0 新增 ssr_lock_test / ssr_parent_kill_test /
│                              ssr_final_lock_test / ssr_final_accept_test；
│                              v1.8.0 新增 ssr_recover_project.py —— 误删段文件后的补渲/重合成运维脚本）
└─ legacy/
   └─ render_segment_speed.py  最早的纯脚本版（无 UI，兜底用）
```
