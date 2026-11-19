# -*- coding: utf-8 -*-
"""
render_segment_speed.py —— Blender 分段不同帧步长渲染（局部倍速）

原理：
  Scene.frame_step 是全局标量、不可做动画。想在一整条时间线上让某段用
  步长 1、某段用步长 4，就必须「按段循环渲染」，并在输出文件名上用
  **连续序号**（shot_00000、shot_00001 …）而不是源帧号。
  这样 PNG 序列丢掉时间信息，后期按统一 fps 播放时，步长 4 的那段帧数只有
  1/4，视觉上天然就是 4 倍速，一条 ffmpeg 命令即可合成，无需手动变速。

用法：
  A) Blender 文本编辑器里打开 → Run Script
  B) blender -b your.blend -P render_segment_speed.py

前置：
  - 有物理/粒子/流体/布料/刚体缓存的，先在完整帧率下烘焙完再跑，
    跳帧渲染会让缓存与帧号错位。
  - 速度段若开运动模糊，把 Cycles/EEVEE 的 shutter 按 1/step 缩小，
    否则快门跨 4 帧会糊成一片。
"""

import bpy
import os
import time

# ==================== 配置区 ====================
# (起始帧, 结束帧(含), 帧步长)
SEGMENTS = [
    (1,   120, 1),   # 正常速度
    (121, 600, 4),   # 4 倍速快放（帧数降到 1/4，渲染时间近似 1/4）
    (601, 720, 1),   # 正常速度
]

OUT_DIR = "//render_seq"     # // 表示相对 .blend 文件目录
FPS_OUT = 24                 # 成片播放帧率（所有段共用）
RES_X, RES_Y = None, None    # None = 沿用场景原分辨率；需要统一尺寸再填数字
FILE_PREFIX = "shot"
# ===============================================

scene = bpy.context.scene
out_dir = bpy.path.abspath(OUT_DIR)
os.makedirs(out_dir, exist_ok=True)

r = scene.render
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGB'
r.image_settings.color_depth = '8'
r.use_file_extension = True
r.fps = FPS_OUT
if RES_X:
    r.resolution_x = RES_X
if RES_Y:
    r.resolution_y = RES_Y

# 分段清单校验
for s, e, st in SEGMENTS:
    if st < 1:
        raise ValueError(f"帧步长必须 >= 1，收到 {st}")

total = sum(len(range(s, e + 1, st)) for s, e, st in SEGMENTS)
print(f"[seg-speed] 输出目录: {out_dir}")
print(f"[seg-speed] 预计渲染 {total} 帧，成片时长约 {total / FPS_OUT:.2f}s @ {FPS_OUT}fps")

idx = 0
done = 0
t0 = time.time()

for si, (start, end, step) in enumerate(SEGMENTS, 1):
    frames = list(range(start, end + 1, step))
    print(f"[seg-speed] 段 {si}/{len(SEGMENTS)}: {start}-{end} step={step} → {len(frames)} 帧")
    for f in frames:
        scene.frame_set(f)
        r.filepath = os.path.join(out_dir, f"{FILE_PREFIX}_{idx:05d}")
        bpy.ops.render.render(write_still=True)
        idx += 1
        done += 1
        el = time.time() - t0
        eta = el / done * (total - done)
        print(f"[seg-speed] {done}/{total} src={f} -> {FILE_PREFIX}_{idx - 1:05d}.png "
              f"已用 {el / 60:.1f}min ETA {eta / 60:.1f}min", flush=True)

print(f"[seg-speed] 完成：{idx} 帧，用时 {(time.time() - t0) / 60:.1f} 分钟")
print(f"[seg-speed] 合成: ffmpeg -framerate {FPS_OUT} -start_number 0 "
      f"-i \"{FILE_PREFIX}_%05d.png\" -c:v libx264 -crf 15 -pix_fmt yuv420p out.mp4")
