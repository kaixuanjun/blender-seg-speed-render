# -*- coding: utf-8 -*-
"""后台进程被外力杀掉时的兜底：应当自动改回本进程渲染并完成，而不是整单失败。

外部 PowerShell 在第二阶段杀掉子进程；脚本只负责起渲染、等结果。
"""
import glob
import json
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "child_kill_state.json")


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    tmp = os.path.join(s.out_dir, "_segments_tmp")
    print("TMP_LEFT %s" % sorted(os.path.basename(p) for p in glob.glob(os.path.join(tmp, "*"))), flush=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"final": s.progress_text}, fh, ensure_ascii=False, indent=2)
    bpy.app.timers.register(lambda: (print("QUIT", flush=True), bpy.ops.wm.quit_blender(), None)[-1], first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    s = bpy.context.scene.ssr
    seg = s.segments[0]
    seg.start, seg.end, seg.step = 0, 40, 1
    s.render_process = "SUBPROC"
    s.auto_compose = False
    print("CONFIG proc=%s seg=%s" % (s.render_process, (seg.start, seg.end, seg.step)), flush=True)
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
