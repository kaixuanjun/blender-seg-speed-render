# -*- coding: utf-8 -*-
"""GUI 端到端测试：视频直出模式，三段结构（step1 / step4 / step1）。"""
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
OUT = os.path.join(_WS, "tmp", "ssr_video_out")
video = os.path.join(OUT, "final.mp4")

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
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("GOP %d QUALITY %s" % (bpy.context.scene.render.ffmpeg.gopsize, s.quality), flush=True)
    print("VIDEO_EXISTS %s size=%d" % (
        os.path.isfile(video),
        os.path.getsize(video) if os.path.isfile(video) else -1), flush=True)
    tmp = os.path.join(OUT, "_segments_tmp")
    print("TMP_LEFT %s" % (sorted(os.listdir(tmp)) if os.path.isdir(tmp) else "GONE"), flush=True)
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
    scene.frame_end = 72

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
    s.output_mode = "VIDEO"
    s.out_dir = OUT
    s.fps = 24
    s.auto_compose = True
    s.keep_segments = False
    s.video_path = video
    s.audio_mode = "FILE"
    s.audio_file = os.path.join(_TEST_HERE, "test_freq.wav")
    s.audio_offset = 0.0
    s.audio_volume = 1.0
    s.audio_follow_speed = True
    s.segments.clear()

    for start, end, step in [(1, 24, 1), (25, 48, 4), (49, 72, 1)]:
        seg = s.segments.add()
        seg.start, seg.end, seg.step = start, end, step

    total = sum(sg.frame_count() for sg in s.segments)
    print("PLAN total=%d expect_sec=%.2f mode=%s" % (total, total / 24.0, s.output_mode), flush=True)

    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)

