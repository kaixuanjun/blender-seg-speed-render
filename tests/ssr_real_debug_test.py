# -*- coding: utf-8 -*-
"""真机回归：直接用用户的 debug.blend + C0646.aac 跑完整流程，并记录状态。"""
import json
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "real_debug_state.json")

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)
else:
    print("ADDON_ALREADY_ENABLED version=" + getattr(bpy.types, "SSR_PT_main", None).bl_label, flush=True)

state = {"events": []}


def snap(tag):
    sc = bpy.context.scene
    s = sc.ssr
    d = {
        "tag": tag,
        "t": time.time(),
        "blend": bpy.data.filepath,
        "fps": sc.render.fps,
        "fps_base": sc.render.fps_base,
        "frame_start": sc.frame_start,
        "frame_end": sc.frame_end,
        "filepath": sc.render.filepath,
        "media_type": getattr(sc.render.image_settings, "media_type", None),
        "file_format": sc.render.image_settings.file_format,
        "use_sequencer": sc.render.use_sequencer,
        "segments": [(sg.start, sg.end, sg.step) for sg in s.segments],
        "out_dir": s.out_dir,
        "video_path": s.video_path,
        "audio_mode": s.audio_mode,
        "audio_file": s.audio_file,
        "progress_text": s.progress_text,
        "running": s.running,
    }
    state["events"].append(d)
    print("SNAP %s %s" % (tag, json.dumps(d, ensure_ascii=False)), flush=True)
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        print("RUNNING %.1f%% %s" % (s.progress * 100.0, s.progress_text), flush=True)
        return 1.0
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    snap("after")
    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    snap("before")
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
