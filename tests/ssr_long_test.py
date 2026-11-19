# -*- coding: utf-8 -*-
"""验证：音频放在另一个场景的 VSE 里，渲染场景也能取到。"""
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
WS = _WS
OUT = os.path.join(WS, "ssr_long_out")
WAV = os.path.join(WS, "long_tone.wav")
video = os.path.join(OUT, "long_final.mp4")

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
    print('ELAPSED_TEXT %s' % s.progress_text, flush=True)
    print("VIDEO_EXISTS %s" % os.path.isfile(video), flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.3)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    scene = bpy.context.scene
    print("WINDOW_OK %s" % (bpy.context.window is not None), flush=True)

    cam_data = bpy.data.cameras.new("C")
    cam = bpy.data.objects.new("C", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (7.0, -7.0, 5.0)
    cam.rotation_euler = (1.1, 0.0, 0.785)
    scene.camera = cam

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 48
    scene.name = "MAIN"

    # 音频放在另一个场景
    audio_sc = bpy.data.scenes.get("AUDIO") or bpy.data.scenes.new("AUDIO")
    se = audio_sc.sequence_editor_create()
    if not len(se.strips):
        se.strips.new_sound("tone", WAV, 1, 0)
    print("AUDIO_SCENE_STRIPS %d" % len(se.strips), flush=True)
    print("MAIN_SCENE_SE %s" % getattr(scene, "sequence_editor", None), flush=True)

    if os.path.isdir(OUT):
        for f in os.listdir(OUT):
            try:
                os.remove(os.path.join(OUT, f))
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
    s.audio_mode = "AUTO"
    s.audio_scene = "AUDIO"
    s.audio_offset = 0.0
    s.audio_volume = 1.0
    s.segments.clear()
    for start, end, step in [(1, 24, 1), (25, 48, 4)]:
        seg = s.segments.add()
        seg.start, seg.end, seg.step = start, end, step

    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
