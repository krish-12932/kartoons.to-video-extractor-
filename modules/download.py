#!/usr/bin/env python3
"""Download: valid segments -> parts -> ffmpeg concat -> single .mp4."""
import time
import pathlib
import subprocess
import urllib.request

from modules.capture import is_ok_url


def download_segments(urls, headers, folder, video):
    clean = [u for u in urls if is_ok_url(u)]
    removed = len(urls) - len(clean)
    print("[5] download: %d valid parts (%d gande hataye)" % (len(clean), removed))
    print("[5] Output: %s" % video)
    if len(clean) < 3:
        raise RuntimeError("Valid segments bahut kam (%d). Video poori chali thi?" % len(clean))
    tmp = pathlib.Path(folder) / "_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    base_h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "Referer": "https://kartoons.to/", "Origin": "https://kartoons.to"}
    base_h.update(headers or {})
    for i, u in enumerate(clean):
        out = tmp / ("part%04d.ts" % i)
        if out.exists() and out.stat().st_size > 0:
            continue
        for _ in range(3):
            try:
                req = urllib.request.Request(u, headers=base_h)
                with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                break
            except Exception as e:
                if i < 3:
                    print("    [fail] part %d: %s" % (i, str(e)[:120]))
                time.sleep(2)
        if i % 25 == 0:
            print("    ... %d/%d" % (i, len(clean)))
    with open(tmp / "list.txt", "w", encoding="utf-8") as lf:
        for i in range(len(clean)):
            lf.write("file 'part%04d.ts'\n" % i)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(tmp / "list.txt"), "-c", "copy", str(video)]
    print("[6] ffmpeg join...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp))
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise RuntimeError("ffmpeg join fail")
    print("[SUCCESS] database me saved: %s" % video)
