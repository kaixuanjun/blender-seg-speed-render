# -*- coding: utf-8 -*-
"""生成测试用音频素材（需要 PATH 里有 ffmpeg）。

用法（在仓库根目录）：
    python tools/make_test_tones.py

产出：
    tests/test_freq.wav   0-1s 440Hz / 1-2s 880Hz / 2-3s 1320Hz，48kHz 立体声
                          —— 用来做「频率标记验证法」，逐点测频判断变速是否正确
    tests/test_tone.wav   三段各 1 秒的同一组频率，单声道短版本，给三段拼接测试用
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.abspath(os.path.join(HERE, "..", "tests"))


def run(args):
    print("ffmpeg " + " ".join(args), flush=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + args, check=True)


def build_concat(out_path, freqs, channels):
    inputs = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=%d:duration=1" % f]
    labels = "".join("[%d:a]" % i for i in range(len(freqs)))
    filt = "%sconcat=n=%d:v=0:a=1" % (labels, len(freqs))
    run(inputs + ["-filter_complex", filt,
                  "-ac", str(channels), "-ar", "48000", out_path])


def main():
    os.makedirs(TESTS, exist_ok=True)
    build_concat(os.path.join(TESTS, "test_freq.wav"), (440, 880, 1320), 2)
    build_concat(os.path.join(TESTS, "test_tone.wav"), (440, 880, 1320), 2)
    for name in ("test_freq.wav", "test_tone.wav"):
        p = os.path.join(TESTS, name)
        print("%s  %d bytes" % (name, os.path.getsize(p)), flush=True)


if __name__ == "__main__":
    sys.exit(main())
