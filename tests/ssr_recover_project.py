"""用户 11 段工程的补救脚本（误删 seg_01 后恢复 + 手动合成）。

用法（GPU 空闲时执行）：
  blender -b "未命名.blend" --python tests/ssr_recover_project.py -- all

分步：
  -- seg01    只重渲第 1 段（帧 0–200）→ _segments_tmp\\seg_01_x1.mp4
  -- compose  只拼接 + 贴音轨 → 成片
  -- all      先 seg01 再 compose

为什么单独写：正常流程里第 1 段渲完就该躺在 _segments_tmp 里，被误删后
后端进程仍然会照常渲完其余 10 段，只是最后拼接时找不到第 1 段。这里用插件
自己的 `_configure_video` / `_concat_videos` / `attach_audio_standalone`，
参数与正常流程完全一致，不另发明一套编码参数。
"""
import glob
import os
import sys

import bpy

import bl_ext.user_default.seg_speed_render as ssr

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
what = (argv[0] if argv else "all").lower()

scene = bpy.context.scene
s = scene.ssr
outdir = ssr._abs_dir(s.out_dir)
tmpdir = os.path.join(outdir, "_segments_tmp")
video = ssr._abs_file(s.video_path)
ffmpeg = ssr._find_exe("ffmpeg", s.ffmpeg_path)

print("RECOVER_OUT", outdir)
print("RECOVER_TMP", tmpdir)
print("RECOVER_VIDEO", video)
print("RECOVER_FFMPEG", ffmpeg)
print("RECOVER_SEGS", [(x.start, x.end, x.step) for x in s.segments])


def render_seg01():
    seg = s.segments[0]
    start, end, step = seg.start, seg.end, seg.step
    raw = os.path.join(tmpdir, "_restore_raw")
    os.makedirs(raw, exist_ok=True)
    for old in glob.glob(os.path.join(raw, "*")):
        os.remove(old)

    ssr._configure_video(scene, s.quality, fps=s.fps)
    scene.frame_start = start
    scene.frame_end = end
    scene.frame_step = step
    scene.render.filepath = os.path.join(raw, "seg_%02d" % 1)
    print("RECOVER_RENDER", start, end, step, scene.render.filepath)

    with bpy.context.temp_override(scene=scene):
        bpy.ops.render.render(animation=True)

    made = sorted(glob.glob(os.path.join(raw, "*.*")))
    print("RECOVER_RAW", [(os.path.basename(p), os.path.getsize(p)) for p in made])
    if not made:
        raise SystemExit("第 1 段没有产出文件")

    target = os.path.join(tmpdir, "seg_01_x%d.mp4" % step)
    if os.path.exists(target):
        os.remove(target)
    os.replace(made[0], target)
    print("RECOVER_SEG01", target, os.path.getsize(target))
    return target


def compose():
    files = sorted(glob.glob(os.path.join(tmpdir, "seg_*_x*.mp4")))
    print("RECOVER_JOIN", [os.path.basename(p) for p in files])
    if len(files) < 2:
        raise SystemExit("段文件不足，先跑 seg01")
    os.makedirs(os.path.dirname(video), exist_ok=True)
    ok = ssr._concat_videos(ffmpeg, files, video, s.quality, False)
    print("RECOVER_CONCAT", ok)
    if not ok:
        raise SystemExit("拼接失败")

    aok, amsg = ssr._RenderSession.attach_audio_standalone(
        ffmpeg, video, s, outdir, scene.frame_start)
    print("RECOVER_AUDIO", aok, amsg)
    print("RECOVER_FINAL", video, os.path.getsize(video))


if what in ("seg01", "all"):
    render_seg01()
if what in ("compose", "all"):
    compose()
print("RECOVER_DONE")
