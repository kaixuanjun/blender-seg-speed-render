# 分段倍速渲染 · Segment Speed Render

Blender 扩展：让**同一条时间线**里的不同帧区间用不同帧步长渲染 —— 局部倍速，顺带把渲染时间省下来。

```
1 – 1000 帧   ×1   →  正常速度
1001 – 3200 帧 ×4   →  4 倍速，只渲 1/4 的帧
3201 – 3500 帧 ×1   →  恢复正常
```

每段渲完自动用 ffmpeg 拼成一条成片，音频同步变速。

| | |
|---|---|
| 当前版本 | **v1.8.0** |
| Blender | **4.2+**（开发与验收在 5.2） |
| 依赖 | ffmpeg（PATH / `~/bin` / `C:\ffmpeg\bin` 任一） |
| 许可 | GPL-3.0-or-later |

---

## 它解决什么问题

`scene.frame_step` 是**全局标量、不能打关键帧**，所以「第 1001 帧开始 4 倍速」这种需求在原生 Blender 里做不到。本扩展的做法是：

```
按段分别渲染（每段独立 frame_step） → ffmpeg 拼接 → 成片
```

倍速是「免费」的：每段都用同一个 fps 编码，2200 帧按步长 4 采样只剩 550 帧，按 24fps 播就是 22.9 秒，而原本该是 91.7 秒 —— 天然 4 倍速，不需要任何变速滤镜。音频则按段截取后用 `atempo` 链同步压缩。

## 功能

| 能力 | 说明 |
|---|---|
| 分段渲染 + 拼接 | 每段独立 `frame_step`，段文件 `seg_0N_xS.mp4`，拼完自动清理 |
| 视频直出 | Blender 直接出 mp4，不落 PNG 序列；也可切 PNG 序列模式（连续编号 `shot_00000…` + 自动合成） |
| **独立进程渲染**（默认） | 后台另起一个 `blender.exe -b` 渲，父进程只读 stdout 报进度 → **渲染期间界面不假死** |
| 本进程渲染 | 备用模式，省一份内存/显存，代价是渲染期间面板每帧顿一下 |
| **锁定界面** | 渲染时视口切线框、关叠加层/gizmo、只刷侧栏，父进程 CPU/帧 0.943→0.373 s |
| 随时停止 | 点停止 0.45 秒内杀掉后台进程，无残留进程、无半截文件 |
| 孤儿进程兜底 | 关掉 Blender 窗口时，外部看门狗 1 秒内收掉后台渲染，不留偷跑进程 |
| **每段自带音轨** | v1.8.0：每段渲完立刻把本段音频 mux 回段文件（画面 `-c:v copy`），段文件单独拿出去也有声音 |
| 音频四模式 | 自动 / 无音频 / 音频文件 / 场景混音（VSE），支持跨场景取音轨、`atempo` 跟随变速 |
| 成片复检 | mux 后回头测 dB，静音就报失败，而不是假装成功 |
| 实时进度 | 段内百分比、当前帧、已用、剩余（EMA 收敛，不来回跳） |
| 画质档位 | 5 档 CRF 17/20/23/26/29，`gopsize = fps × 4` |

真机验收数据（用户工程 `debug.blend` 0–200，201 帧，EEVEE）：367.5 s 出片 6.700 s / `h264 1920×1080 + aac 48 kHz 2ch`、`音轨 ✓ mean -18.8 dB`、主循环心跳 `max_gap 0.24`（`gaps_over_1s` 为空）、`VP_RESTORED True`。细节全在 [`docs/HANDOFF.md`](docs/HANDOFF.md)。

## 安装

1. 下载 `dist/seg_speed_render-1.8.0.zip`
2. 编辑 → 偏好设置 → 获取扩展 → 右上角下拉「**从磁盘安装**」→ 选这个 zip
3. 3D 视图按 **N** → 侧栏标签「**分段倍速**」

有 ffmpeg 就行；更多安装/排障步骤（含「没声音」四步排查）见 [`dist/INSTALL.txt`](dist/INSTALL.txt)。

## 用法

1. 面板里加段，填 **起始 / 结束 / 步长**
2. 选输出目录（默认工程所在目录），设 fps、画质档位
3. 选音频来源（默认「自动」：有 VSE 音轨用它，没有退回音频文件，都没有就不加音轨）
4. 点「**开始分段渲染**」

想边渲边看画面 → 切「本进程」模式（会弹出 Blender 自己的渲染窗口）；想界面最顺、最省 CPU → 保持「独立进程」+「锁定界面」。

## 参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `segments` | `start` / `end` / `step` | 段列表，可增删、上下移 |
| `output_mode` | `VIDEO` / `PNG` | 视频直出，或 PNG 序列 + 手动合成 |
| `render_process` | `SUBPROC` / `INPROC` | 独立进程（默认）/ 本进程 |
| `lock_ui` | `False` / `True` | 锁定界面，只省界面开销、不提速 |
| `quality` | `PERC_LOSSLESS`~`VERYLOW` | CRF 17 / 20 / 23 / 26 / 29 |
| `audio_mode` | `AUTO` / `NONE` / `FILE` / `SCENE` | 音频来源 |
| `audio_scene` | 场景名 | `SCENE` 模式下取哪个场景的 VSE（默认当前场景） |
| `audio_offset` / `audio_volume` | 秒 / 倍 | 音轨起点与增益 |
| `audio_follow_speed` | `True` / `False` | 音频是否跟随倍速压缩（`atempo` 链） |
| `auto_shutter` | `True` | 运动模糊快门按 `1/step` 缩小，跳帧段不糊 |
| `keep_segments` | `False` / `True` | 保留 `_segments_tmp` 里的段文件 |
| `ffmpeg_path` | 路径 | 留空则自动查找 |

## 目录

```
.
├─ src/                     插件源码（就是扩展打包内容）
│  ├─ __init__.py           主文件，~2400 行
│  └─ blender_manifest.toml manifest（version 一处）
├─ dist/                    可安装产物
│  ├─ seg_speed_render-1.8.0.zip
│  └─ INSTALL.txt           中文安装说明（UTF-8 BOM）
├─ tests/                   34 个回归脚本 + 测试素材
│  └─ artifacts/            测试写出的 state json（不入库）
├─ tools/
│  ├─ make_test_tones.py    生成 test_freq.wav / test_tone.wav（频率标记法）
│  └─ probes/               早期 Blender API 探针（存档）
├─ legacy/                  最早的纯脚本版（无 UI，兜底）
├─ docs/HANDOFF.md          交接文档：踩坑清单、代码地图、验收数据
├─ build/                   打包 stage（不入库）
├─ logs/                    运行日志（不入库）
└─ tmp/                     渲染样本与测试输出（不入库）
```

## 开发

```powershell
# 1. 改 src/__init__.py（改类列表时别忘了 CLASSES 元组要列全）
# 2. 语法检查（必做，Blender 的报错很难读）
python -m py_compile src\__init__.py; if ($LASTEXITCODE -eq 0) { "SYNTAX_OK" }

# 3. 同步到扩展目录
Copy-Item src\__init__.py,src\blender_manifest.toml `
  "$env:APPDATA\Blender Foundation\Blender\5.2\extensions\user_default\seg_speed_render\" -Force

# 4. 跑回归
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python tests\ssr_video_test.py
```

Blender 5.2 的 API 坑（`media_type` 必须先设、没有 `render_progress` 回调、`se.strips`、mixdown 异步写盘…）集中在 [`docs/HANDOFF.md`](docs/HANDOFF.md) 第五节，**动手前先读那一节**，别凭 4.x 记忆写。

## 测试

测试脚本以 `-b --python` 跑，每个脚本自建带相机的场景、结束时 `quit_blender`，靠 stdout 里的标记判断通过与否（`FINAL_TEXT` / `RECOVER_*` / `max_gap`）。

```powershell
# 生成音频素材（第一次跑音频相关测试前）
python tools\make_test_tones.py

# 跑一个
$p = Start-Process "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  -ArgumentList '--python', "tests\ssr_video_test.py" `
  -RedirectStandardOutput "logs\out.txt" -RedirectStandardError "logs\err.txt" -PassThru
$p | Wait-Process -Timeout 280 -ErrorAction SilentlyContinue
if (-not $p.HasExited) { $p.Kill() }
Select-String -Path logs\out.txt -Pattern 'FINAL_TEXT|Traceback'
```

脚本清单与各自的通过标志见 [`docs/HANDOFF.md`](docs/HANDOFF.md) 第九节。`tests/ssr_recover_project.py` 不是回归，是运维脚本（段文件被误删后补渲首段 / 重拼 / 重贴音轨）。

## 打包

```powershell
$stage = "build\seg_speed_render"
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item src\__init__.py,src\blender_manifest.toml -Destination $stage -Force

& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --command extension build --source-dir $stage --output-dir dist
```

版本号要改**两处**：`src/__init__.py` 的 `VERSION`、`src/blender_manifest.toml` 的 `version`。发版后按 [`docs/HANDOFF.md`](docs/HANDOFF.md) 第十节做一次干净环境安装验证（临时 `BLENDER_USER_RESOURCES` → `STATUS Installed`）。

## 已知限制

1. **倍速必然缩短成片**，这是原理决定的
2. 视频直出**不可断点续渲**（中断就从头来）
3. 物理/粒子/流体缓存必须先按步长 1 烘焙完，否则跳帧会错位
4. 独立进程模式多占一份内存/显存；显存吃紧就切「本进程」
5. 收尾合成（ffmpeg 拼接/混流）仍占主线程，长片末尾可能「未响应」几秒到几十秒
6. 「锁定界面」只省界面开销，**不提速**；本进程模式下没有差别
7. 段文件与成片不是同一份编码（段是 Blender 直出、成片 `-c copy` 拼接），别混着比码率

完整 14 条见 [`docs/HANDOFF.md`](docs/HANDOFF.md) 第十二节。

## 许可

GPL-3.0-or-later，见 [`LICENSE`](LICENSE)。
