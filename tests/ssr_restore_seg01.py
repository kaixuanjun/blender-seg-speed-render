"""同一条命令里做两件事，避免二次开进程：

1) 把用户工程（磁盘版）另存为 ``_bg_<stamp>_<pid>.blend`` —— 原后台副本被误删，
   用户 11 段工程后续每次 `-b <bgblend>` 启动都需要它；
2) 重渲第 1 段（帧 0–200）到 rawdir，用于补回被误删的 ``seg_01_x1.mp4``。

用法：
  blender -b "未命名.blend" --python tests/ssr_restore_seg01.py -- <bgblend> <rawdir>
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
bgblend = argv[0]
rawdir = argv[1]
os.makedirs(os.path.dirname(bgblend), exist_ok=True)
os.makedirs(rawdir, exist_ok=True)

# 1) 补回后台副本（内容取自磁盘上的工程，渲染驱动会覆盖帧范围/快门/输出路径）
bpy.ops.wm.save_as_mainfile(filepath=bgblend, copy=True, relative_remap=True)
print("RESTORE_BG", bgblend, os.path.getsize(bgblend))

# 2) 重渲第 1 段
scene = bpy.context.scene
r = scene.render
scene.frame_start = 0
scene.frame_end = 200
scene.frame_step = 1
r.filepath = os.path.join(rawdir, "seg_00")
r.use_file_extension = True
r.image_settings.media_type = "VIDEO"

print("RESTORE_OUT", r.filepath)
print("RESTORE_FMT", r.image_settings.file_format, r.ffmpeg.format, r.ffmpeg.codec,
      r.ffmpeg.constant_rate_factor)
print("RESTORE_FPS", r.fps, r.fps_base, "RES", r.resolution_x, r.resolution_y,
      r.resolution_percentage, "SHUTTER", r.motion_blur_shutter)

with bpy.context.temp_override(scene=scene):
    bpy.ops.render.render(animation=True)

print("RESTORE_DONE", rawdir)
