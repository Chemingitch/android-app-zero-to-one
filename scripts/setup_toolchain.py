#!/usr/bin/env python3
"""Bootstrap a Gradle-free Android build toolchain on a machine that has nothing installed.

Downloads a JDK 17 and the Android command-line tools, then installs
platform-tools / build-tools / platform through sdkmanager, and writes
<root>/toolchain.json so build_apk.py picks everything up with no flags.

Usage:
    python setup_toolchain.py [--dir <install-root>] [--proxy http://host:port]
                              [--mirror cn|global] [--jdk <existing-jdk>]
                              [--dry-run]

No Android Studio, no Gradle, no admin rights required.
"""

import argparse
import json
import os
import platform as pyplatform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

CMDLINE_REVS = ["13114758", "11076708", "10406996", "9477386"]
GOOGLE_DL = "https://dl.google.com/android/repository/commandlinetools-%s-%s_latest.zip"
ADOPTIUM_API = ("https://api.adoptium.net/v3/binary/latest/17/ga/%s/%s/jdk/hotspot/normal/eclipse")
TUNA_LISTING = "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/%s/%s/"
SDK_PACKAGES = ["platform-tools", "build-tools;34.0.0", "platforms;android-34"]


def log(msg):
    print(msg, flush=True)


def fail(msg):
    print("\n[SETUP FAILED] %s" % msg, file=sys.stderr)
    sys.exit(1)


def host():
    """Map this machine onto Google/Adoptium naming."""
    s = pyplatform.system().lower()
    m = pyplatform.machine().lower()
    arch = "x64" if m in ("amd64", "x86_64", "x64") else ("aarch64" if "aarch64" in m or "arm64" in m else "x64")
    if "windows" in s:
        return "windows", arch, "win"
    if "darwin" in s:
        return "mac", arch, "mac"
    return "linux", arch, "linux"


def download(url, dest, proxy=None, label=""):
    log("  downloading %s" % (label or url))
    if proxy:
        os.environ["https_proxy"] = proxy
        os.environ["http_proxy"] = proxy
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("\r    %d / %d KB" % (done // 1024, total // 1024))
                    sys.stdout.flush()
            sys.stdout.write("\n")
    except Exception as e:
        return False, str(e)
    return True, ""


def unzip(path, dest):
    with zipfile.ZipFile(path) as z:
        z.extractall(dest)


def find_file(root, name):
    for base, _dirs, files in os.walk(root):
        if name in files:
            return os.path.join(base, name)
    return None


def javac_home(base, system):
    """Return the real JAVA_HOME under base.

    Temurin archives extract into a nested jdk-<version>/ folder, so the
    requested dir itself is often not a valid JAVA_HOME. Locate bin/javac
    and walk back up instead of trusting the directory we unpacked into.
    """
    exe = "javac.exe" if system == "windows" else "javac"
    if base and os.path.isfile(os.path.join(base, "bin", exe)):
        return base
    if base and os.path.isdir(base):
        hit = find_file(base, exe)
        if hit:
            return os.path.dirname(os.path.dirname(hit))
    return base


def main():
    ap = argparse.ArgumentParser(description="Bootstrap the Gradle-free Android toolchain.")
    ap.add_argument("--dir", default=None, help="install root (default ~/.android-zero-to-one)")
    ap.add_argument("--proxy", default=None, help="http proxy, e.g. http://127.0.0.1:7890")
    ap.add_argument("--mirror", choices=["cn", "global"], default=None,
                    help="JDK source; 'cn' uses the Tsinghua mirror")
    ap.add_argument("--jdk", default=None, help="reuse an existing JDK instead of downloading")
    ap.add_argument("--sdk", default=None,
                    help="reuse an existing Android SDK (e.g. the one Android Studio installed)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan without downloading")
    args = ap.parse_args()

    system, arch, gslug = host()
    mirror = args.mirror or ("cn" if os.environ.get("SETUP_MIRROR_CN") else "global")
    root = os.path.abspath(args.dir or os.environ.get("ANDROID_TOOLS_ROOT")
                           or os.path.join(os.path.expanduser("~"), ".android-zero-to-one"))

    log("=" * 58)
    log(" Android toolchain bootstrap")
    log("  host   = %s %s" % (system, arch))
    log("  root   = %s" % root)
    log("  mirror = %s" % mirror)
    log("=" * 58)

    javac_exe = "javac.exe" if system == "windows" else "javac"
    jdk = None
    for cand in (args.jdk, os.environ.get("JAVA_HOME"), os.path.join(root, "jdk-17")):
        if not cand:
            continue
        real = javac_home(cand, system)
        if real and os.path.isfile(os.path.join(real, "bin", javac_exe)):
            jdk = real
            log("[1/4] reusing JDK at %s" % jdk)
            break

    if jdk is None:
        jdk_dir = os.path.join(root, "jdk-17")
        log("[1/4] JDK 17 -> %s" % jdk_dir)
        jdk = jdk_dir
        if not args.dry_run:
            if os.path.isdir(jdk_dir):
                log("  already present, skipping")
            else:
                os.makedirs(root, exist_ok=True)
                tmp = os.path.join(tempfile.mkdtemp(), "jdk.zip")
                if mirror == "cn":
                    ok = False
                    try:
                        listing = TUNA_LISTING % (arch, system)
                        with urllib.request.urlopen(urllib.request.Request(
                                listing, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                            html = r.read().decode("utf-8", "replace")
                        names = re.findall(r'OpenJDK17U-jdk_%s_%s_hotspot[^"\'<> ]+\.(?:zip|tar\.gz)'
                                           % (arch, system), html)
                        if names:
                            ok, err = download(listing + sorted(names)[-1], tmp, args.proxy, "Temurin 17 (mirror)")
                    except Exception as e:
                        log("  mirror lookup failed: %s" % e)
                    if not ok:
                        ok, err = download(ADOPTIUM_API % (system, arch), tmp, args.proxy, "Temurin 17")
                else:
                    ok, err = download(ADOPTIUM_API % (system, arch), tmp, args.proxy, "Temurin 17")
                if not ok:
                    fail("JDK download failed: %s\n  Pass --jdk <path> to reuse an existing JDK." % err)
                if tmp.endswith(".zip") or open(tmp, "rb").read(2) == b"PK":
                    unzip(tmp, jdk)
                else:
                    os.makedirs(jdk, exist_ok=True)
                    subprocess.run(["tar", "-xzf", tmp, "-C", jdk, "--strip-components=1"], check=True)
                shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
                jdk = javac_home(jdk_dir, system)
    if not args.dry_run and not os.path.isfile(os.path.join(jdk, "bin", javac_exe)):
        fail("javac not found under %s (pass --jdk <path> to reuse an existing JDK)" % jdk)

    sdk = args.sdk or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    reusing_sdk = bool(sdk and os.path.isdir(sdk))
    if reusing_sdk:
        log("[2/4] reusing Android SDK at %s" % sdk)
    else:
        sdk = os.path.join(root, "android-sdk")
        log("[2/4] Android command-line tools -> %s" % sdk)
    if not args.dry_run:
        tools_dir = os.path.join(sdk, "cmdline-tools", "latest", "bin")
        if os.path.isdir(tools_dir):
            log("  already present, skipping")
        elif reusing_sdk:
            log("  no cmdline-tools here; will use packages already installed")
        else:
            os.makedirs(sdk, exist_ok=True)
            tmp = os.path.join(tempfile.mkdtemp(), "cmdline.zip")
            last_err = ""
            for rev in CMDLINE_REVS:
                ok, last_err = download(GOOGLE_DL % (gslug, rev), tmp, args.proxy,
                                        "commandlinetools-%s (%s)" % (gslug, rev))
                if ok:
                    break
            if not ok:
                fail("could not download command-line tools: %s" % last_err)
            unzip(tmp, os.path.join(sdk, "cmdline-tools"))
            # the zip extracts to cmdline-tools/; rename that to cmdline-tools/latest
            inner = os.path.join(sdk, "cmdline-tools", "cmdline-tools")
            latest = os.path.join(sdk, "cmdline-tools", "latest")
            if os.path.isdir(inner) and not os.path.isdir(latest):
                os.rename(inner, latest)
            shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)

    sm = os.path.join(sdk, "cmdline-tools", "latest", "bin",
                      "sdkmanager.bat" if system == "windows" else "sdkmanager")

    def populated(*parts):
        p = os.path.join(sdk, *parts)
        return os.path.isdir(p) and bool(os.listdir(p))

    if not os.path.isfile(sm):
        if populated("build-tools") and populated("platforms"):
            sm = None
        else:
            fail("no sdkmanager at %s and this SDK has no build-tools/platforms.\n"
                 "  Drop --sdk to download a self-contained SDK instead." % sm)

    log("[3/4] accept licenses")
    if not args.dry_run and sm:
        env = dict(os.environ, JAVA_HOME=jdk, ANDROID_SDK_ROOT=sdk, ANDROID_HOME=sdk)
        if args.proxy:
            env["https_proxy"] = env["http_proxy"] = args.proxy
            env["JAVA_TOOL_OPTIONS"] = "-Dhttps.proxyHost=%s" % args.proxy.split("//")[-1].split(":")[0]
        subprocess.run([sm, "--sdk_root=%s" % sdk, "--licenses"],
                       input=b"y\n" * 40, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

    if not sm:
        log("[4/4] nothing to install")
    else:
        log("[4/4] install %s" % ", ".join(SDK_PACKAGES))
    if not args.dry_run and sm:
        env = dict(os.environ, JAVA_HOME=jdk, ANDROID_SDK_ROOT=sdk, ANDROID_HOME=sdk)
        proc = subprocess.run([sm, "--sdk_root=%s" % sdk] + SDK_PACKAGES,
                              input=b"y\n" * 40, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            print(out)
            fail("sdkmanager failed")
        if not os.path.isdir(os.path.join(sdk, "build-tools")):
            fail("build-tools missing after install:\n%s" % out)

    cfg = {"jdk": os.path.abspath(jdk), "sdk": os.path.abspath(sdk)}
    if not args.dry_run:
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "toolchain.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.environ.setdefault("ANDROID_TOOLS_ROOT", root)

    log("")
    log("=" * 58)
    log(" READY  jdk=%s" % jdk)
    log("        sdk=%s" % sdk)
    log(" config written to %s" % os.path.join(root, "toolchain.json"))
    log("")
    log(" Next:  python build_apk.py --src <project> --min-sdk 21 --out app.apk")
    log("        (build_apk.py reads toolchain.json automatically)")
    log("=" * 58)


if __name__ == "__main__":
    main()
