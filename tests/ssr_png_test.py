# -*- coding: utf-8 -*-
"""GUI 回归测试：PNG 序列模式（连续编号 + 合成）。"""
import glob
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
OUT = os.path.join(_WS, "tmp", "ssr_png_out")
video = os.path.join(OUT, "png_final.mp4")

ns = {"__name__": "__main__", "__file__": ADDON}
if not hasattr(bpy.types.Scene, "ssr"):
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)
else:
    print("ADDON_ALREADY_ENABLED", flush=True)


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    pngs = sorted(glob.glob(os.path.join(OUT, "shot_*.png")))
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("PNG_COUNT %d" % len(pngs), flush=True)
    print("PNG_NAMES %s" % [os.path.basename(p) for p in pngs], flush=True)
    print("VIDEO_EXISTS %s size=%d" % (
        os.path.isfile(video),
        os.path.getsize(video) if os.path.isfile(video) else -1), flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.3)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    scene = bpy.context.scene
    if scene.camera is None:
        cam_data = bpy.data.cameras.new("TestCam")
        cam = bpy.data.objects.new("TestCam", cam_data)
        scene.collection.objects.link(cam)
        cam.location = (7.0, -7.0, 5.0)
        cam.rotation_euler = (1.1, 0.0, 0.785)
        scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 12

    if os.path.isdir(OUT):
        for root, dirs, files in os.walk(OUT, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except Exception:
                    pass
    os.makedirs(OUT, exist_ok=True)

    s = scene.ssr
    s.output_mode = "PNG"
    s.out_dir = OUT
    s.prefix = "shot"
    s.fps = 24
    s.auto_compose = True
    s.audio_mode = "FILE"
    s.audio_file = os.path.join(_TEST_HERE, "test_freq.wav")
    s.audio_follow_speed = True
    s.video_path = video
    s.segments.clear()
    a = s.segments.add()
    a.start, a.end, a.step = 1, 6, 1
    b = s.segments.add()
    b.start, b.end, b.step = 7, 12, 4
    print("PLAN total=%d mode=%s" % (sum(sg.frame_count() for sg in s.segments), s.output_mode), flush=True)

    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
