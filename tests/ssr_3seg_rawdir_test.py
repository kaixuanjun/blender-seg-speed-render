# -*- coding: utf-8 -*-
"""三段倍速回归：1-24×1 / 25-48×4 / 49-72×1，带 440/880/1320Hz 频率标记音频。
验证 1.4.4 的「每段独立 rawdir」没有破坏多段拼接与 atempo 音频。"""
import os

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "tmp", "3seg")
OUT = os.path.abspath(OUT)
VIDEO = os.path.join(OUT, "final.mp4")
AUDIO = os.path.join(HERE, "test_tone.wav")

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("VIDEO_EXISTS %s size=%d" % (
        os.path.isfile(VIDEO),
        os.path.getsize(VIDEO) if os.path.isfile(VIDEO) else -1), flush=True)
    tmp = os.path.join(OUT, "_segments_tmp")
    print("TMP_LEFT %s" % (sorted(os.listdir(tmp)) if os.path.isdir(tmp) else "GONE"), flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.4)
    return None


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (7.0, -7.0, 5.0)
    cam.rotation_euler = (1.1, 0.0, 0.785)
    sc.camera = cam
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.view_layer.objects.active
    cube.keyframe_insert("location", frame=1)
    cube.location.x = 3.0
    cube.keyframe_insert("location", frame=72)
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = 320
    sc.render.resolution_y = 180
    sc.render.resolution_percentage = 100
    sc.frame_start = 1
    sc.frame_end = 72
    sc.render.fps = 24

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

    s = sc.ssr
    s.output_mode = "VIDEO"
    s.out_dir = OUT
    s.fps = 24
    s.fps_base = 1.0
    s.quality = "MEDIUM"
    s.auto_compose = True
    s.keep_segments = True  # 顺带验证：留段时不该留 aud_*.wav/_audio_full.wav
    s.video_path = VIDEO
    s.audio_mode = "FILE"
    s.audio_file = AUDIO
    s.audio_offset = 0.0
    s.audio_volume = 1.0
    s.audio_follow_speed = True
    s.segments.clear()
    for a, b, st in [(1, 24, 1), (25, 48, 4), (49, 72, 1)]:
        sg = s.segments.add()
        sg.start, sg.end, sg.step = a, b, st
    print("PLAN frames=%d expect=%.2fs" % (
        sum(sg.frame_count() for sg in s.segments),
        sum(sg.frame_count() for sg in s.segments) / 24.0), flush=True)
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=0.5)


def setup():
    if bpy.context.window is None:
        return 0.3
    build()
    return None


bpy.app.timers.register(setup, first_interval=0.5)
