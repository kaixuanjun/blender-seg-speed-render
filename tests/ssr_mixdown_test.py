# -*- coding: utf-8 -*-
"""测试 SCENE 模式：从 VSE 混出音频（含异步写盘等待）。"""
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
TONE = os.path.join(_TEST_HERE, "test_tone.wav")
OUT = os.path.abspath(os.path.join(_TEST_HERE, "..", "tmp", "mix_test"))
MIX = os.path.join(OUT, "mix.wav")

if not hasattr(bpy.types.Scene, "ssr"):
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), {})
    print("ADDON_EXEC_LOADED", flush=True)

_state = {"t0": 0.0, "last": -1, "kind": ""}


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def probe():
    if not os.path.isfile(MIX):
        if time.time() - _state["t0"] > 30:
            print("RESULT timeout no file", flush=True)
            bpy.app.timers.register(quit_now, first_interval=0.2)
            return None
        return 0.2
    sz = os.path.getsize(MIX)
    if sz > 1024 and sz == _state["last"]:
        with open(MIX, "rb") as f:
            head = f.read(4)
        print("RESULT ok size=%d head=%s waited=%.1fs" % (
            sz, head, time.time() - _state["t0"]), flush=True)
        bpy.app.timers.register(quit_now, first_interval=0.2)
        return None
    _state["last"] = sz
    if time.time() - _state["t0"] > 30:
        print("RESULT timeout size=%d" % sz, flush=True)
        bpy.app.timers.register(quit_now, first_interval=0.2)
        return None
    return 0.2


def setup():
    if bpy.context.window is None:
        return 0.3
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 72
    scene.render.fps = 24

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        try:
            os.remove(os.path.join(OUT, f))
        except Exception:
            pass

    se = scene.sequence_editor_create()
    strips = getattr(se, "strips", None)
    if strips is None:
        strips = se.sequences
    strips.new_sound("tone", filepath=TONE, channel=1, frame_start=1)

    _state["t0"] = time.time()
    _state["last"] = -1
    try:
        bpy.ops.sound.mixdown(filepath=MIX, check_existing=False,
                              container="WAV", codec="PCM", format="S16",
                              mixrate=48000)
        print("MIXDOWN invoked", flush=True)
    except Exception as exc:
        print("MIXDOWN_FAIL %s" % exc, flush=True)
        bpy.app.timers.register(quit_now, first_interval=0.2)
        return None

    bpy.app.timers.register(probe, first_interval=0.3)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
