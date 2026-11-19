# -*- coding: utf-8 -*-
"""孤儿进程兜底：父进程（Blender 界面）被强杀时，后台渲染进程必须跟着死。

为什么需要这个测试：
    bpy.ops.render.render(animation=True) 的整个渲染循环握着 Python 的 GIL，
    所以把看门狗写成子进程里的线程没用（实测：父进程被杀 10 秒后子进程还在渲、
    烧了 445 秒 CPU、占 1.5 GB 内存）。真正的看门狗是父进程另起的独立小进程
    `_bg_watch.py`（Blender 自带 python.exe 跑），每 0.5 秒看一次父进程存活。

手动跑法：
    1) 起这个脚本：
       blender.exe "…\\debug.blend" --python tests/ssr_parent_kill_test.py
    2) 看到 `PARENT_PID <n>` 与 `[seg-speed] 看门狗已就位` 后，从外部杀掉该 PID：
       Stop-Process -Id <n> -Force
    3) 1–2 秒内 `Get-Process blender` 应该一个都不剩；
       `_segments_tmp\\seg_speed_render.log` 末尾出现
       `[seg-speed] 父进程 <n> 已消失，后台渲染 <m> 已被看门狗收掉`
"""
import os

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
FRAMES = int(os.environ.get("SSR_FRAMES", "40"))

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)


def setup():
    if bpy.context.window is None:
        return 0.3
    s = bpy.context.scene.ssr
    seg = s.segments[0]
    seg.start = 0
    seg.end = max(1, FRAMES) - 1
    seg.step = 1
    s.render_process = "SUBPROC"
    s.lock_ui = False
    s.keep_segments = False
    s.auto_compose = False          # 不拼接，专心测进程存活
    print("PARENT_PID %d  frames=%d" % (os.getpid(), FRAMES), flush=True)
    bpy.ops.seg_speed.render()
    return None


bpy.app.timers.register(setup, first_interval=0.5)
