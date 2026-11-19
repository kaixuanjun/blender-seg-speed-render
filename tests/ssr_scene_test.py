# -*- coding: utf-8 -*-
"""SCENE 模式端到端：VSE 音轨 + 三段渲染 → 带音轨成片。"""
import os

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
TONE = os.path.join(_TEST_HERE, "test_tone.wav")
OUT = os.path.abspath(os.path.join(_TEST_HERE, "..", "tmp", "ssr_scene_out"))
video = os.path.join(OUT, "scene_final.mp4")

if not hasattr(bpy.types.Scene, "ssr"):
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), {})
    print("ADDON_EXEC_LOADED", flush=True)


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
        os.path.isfile(video), os.path.getsize(video) if os.path.isfile(video) else -1), flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.3)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    scene = bpy.context.scene
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
    scene.render.use_sequencer = False  # 画面来自 3D，音轨来自 VSE

    se = scene.sequence_editor_create()
    strips = getattr(se, "strips", None)
    if strips is None:
        strips = se.sequences
    if not len(strips):
        strips.new_sound("tone", filepath=TONE, channel=1, frame_start=1)
    print("STRIPS %d" % len(strips), flush=True)

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
    s.audio_mode = "SCENE"
    s.audio_offset = 0.0
    s.audio_volume = 1.0
    s.audio_follow_speed = True
    s.segments.clear()
    for start, end, step in [(1, 24, 1), (25, 48, 4), (49, 72, 1)]:
        seg = s.segments.add()
        seg.start, seg.end, seg.step = start, end, step

    print("PLAN total=%d mode=%s audio=%s" % (
        sum(sg.frame_count() for sg in s.segments), s.output_mode, s.audio_mode), flush=True)

    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
