#!/usr/bin/env python3
"""Real Chrome launch + CDP connect + cleanup.

Cloudflare bot-detection se bachne ke liye Playwright ka
chromium nahi, tumhara ASLI installed Chrome use hota hai.
"""
import time
import subprocess
from playwright.sync_api import sync_playwright

from modules.config import CHROME_PATH, CDP_URL, PROFILE_DIR


def launch_real_chrome():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(
            [CHROME_PATH, "--remote-debugging-port=9222",
             "--user-data-dir=%s" % str(PROFILE_DIR)]
        )
        print("[*] Asli Chrome launch kiya... (CDP mode for Cloudflare Bypass)")
        time.sleep(3)
        return proc
    except Exception as e:
        print("[!] Chrome launch error:", e)
        return None


def connect_cdp(pw):
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        return browser, context, page
    except Exception as e:
        print("[!] CDP Connect error:", e)
        print("Pehle se khule hue saare Chrome band karke dobara try karein.")
        return None, None, None


def close_all(context, proc):
    try:
        if context is not None:
            context.close()
    except Exception:
        pass
    try:
        if proc is not None:
            proc.terminate()
    except Exception:
        pass
