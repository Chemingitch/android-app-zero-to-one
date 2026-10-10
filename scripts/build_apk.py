#!/usr/bin/env python3
"""Build an Android APK from raw sources without Gradle or Android Studio.

Chain: aapt2 compile -> aapt2 link -> javac -> d8 -> inject dex -> zipalign -> apksigner.

Usage:
    python build_apk.py --src <project-dir> [--tools-root <dir>] [--min-sdk 21]
                        [--target-sdk 34] [--out <file.apk>] [--ks <keystore>]
                        [--alias <name>] [--storepass <pw>] [--keypass <pw>]
                        [--no-sign] [--clean]

Toolchain is resolved in this order (first hit wins):
    1. explicit --jdk / --sdk flags
    2. --tools-root <dir>   (either <dir>/toolchain.json, or the
                             <dir>/jdk17 + <dir>/android-sdk layout)
    3. toolchain.json written by setup_toolchain.py
       (searched in $ANDROID_TOOLS_ROOT, then ~/.android-zero-to-one)
    4. environment: JAVA_HOME, ANDROID_SDK_ROOT / ANDROID_HOME
    5. well-known install locations

So on a machine prepared by `python setup_toolchain.py`, a bare
`python build_apk.py --src myapp` works with no extra arguments.
"""

import argparse
import glob
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile

IS_WIN = os.name == "nt"


def fail(msg):
    print("\n[BUILD FAILED] %s" % msg, file=sys.stderr)
    sys.exit(1)


def sh(args, cwd=None, env=None, what=""):
    """Run one build step. .bat helpers must go through cmd /c or control never returns."""
    label = what or " ".join(args[:2])
    print("  -> %s" % label)
    if IS_WIN and isinstance(args[0], str) and args[0].lower().endswith(".bat"):
        args = ["cmd", "/c"] + list(args)
    proc = subprocess.run(args, cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        print(out)
        fail("step failed (%d): %s" % (proc.returncode, label))
    return out


def newest_subdir(parent):
    """Pick the highest-sorting (newest) version directory under parent."""
    if not os.path.isdir(parent):
        return None
    subs = [d for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))]
    return os.path.join(parent, sorted(subs)[-1]) if subs else None


def load_toolchain_json(extra_roots=None):
    """Read the config written by setup_toolchain.py, if any."""
    roots = list(extra_roots or [])
    v = os.environ.get("ANDROID_TOOLS_ROOT")
    if v:
        roots.append(v)
    roots.append(os.path.join(os.path.expanduser("~"), ".android-zero-to-one"))
    for r in roots:
        p = os.path.join(r, "toolchain.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def detect_sdk():
    """Locate the Android SDK: env vars first, then the usual install locations."""
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            return v
    home = os.path.expanduser("~")
    guesses = [
        os.path.join(home, "Android", "Sdk"),
        os.path.join(home, "AppData", "Local", "Android", "Sdk"),
        os.path.join(home, "Library", "Android", "sdk"),
        "/usr/lib/android-sdk",
        "/opt/android-sdk",
    ]
    for g in guesses:
        if os.path.isdir(g):
            return g
    return None


def detect_jdk():
    """Locate a JDK 17+: JAVA_HOME first, then a bundled jdk17 next to the SDK."""
    v = os.environ.get("JAVA_HOME")
    if v and os.path.isdir(v):
        return v
    home = os.path.expanduser("~")
    for g in (os.path.join(home, "jdk17"), "/usr/lib/jvm/java-17-openjdk"):
        if os.path.isdir(g):
            return g
    return None


def load_props(path):
    """Parse a java-style key=value properties file."""
    d = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().replace("\\\\", "\\")
    return d


def keystore_roots(cfg):
    """Places where setup_keystore.py may have put certs/."""
    roots = []
    v = os.environ.get("ANDROID_TOOLS_ROOT")
    if v:
        roots.append(v)
    if cfg.get("sdk"):
        roots.append(os.path.dirname(cfg["sdk"]))
    roots.append(os.path.join(os.path.expanduser("~"), ".android-zero-to-one"))
    seen, out = set(), []
    for r in roots:
        r = os.path.abspath(r)
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def find_personal_keystore(cfg):
    """Return (ks, alias, storepass, keypass, props_file) or (None, ...)."""
    for r in keystore_roots(cfg):
        p = os.path.join(r, "certs", "keystore.properties")
        if not os.path.isfile(p):
            continue
        try:
            props = load_props(p)
        except Exception:
            continue
        ks = props.get("ks")
        if ks and os.path.isfile(ks):
            return ks, props.get("alias", "apkkey"), props.get("storepass"), \
                props.get("keypass"), p
    return None, None, None, None, None


def find_sources(root, suffix):
    hits = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(suffix):
                hits.append(os.path.join(base, name))
    return sorted(hits)


def main():
    ap = argparse.ArgumentParser(description="Build an APK without Gradle.")
    ap.add_argument("--src", required=True, help="project dir with AndroidManifest.xml, java/, res/")
    ap.add_argument("--tools-root", default=None,
                    help="combined root containing jdk17/ and android-sdk/ (optional)")
    ap.add_argument("--jdk", default=None, help="override JDK home (default: JAVA_HOME)")
    ap.add_argument("--sdk", default=None, help="override Android SDK root")
    ap.add_argument("--min-sdk", default="21")
    ap.add_argument("--target-sdk", default="34")
    ap.add_argument("--out", default=None, help="output apk path (default <src>/app.apk)")
    ap.add_argument("--build-tools", default=None, help="override build-tools version dir")
    ap.add_argument("--ks", default=None,
                    help="keystore (default: your personal certs/personal.jks)")
    ap.add_argument("--alias", default=None)
    ap.add_argument("--storepass", default=None)
    ap.add_argument("--keypass", default=None)
    ap.add_argument("--no-keystore-setup", action="store_true",
                    help="do not auto-create a personal keystore if none exists")
    ap.add_argument("--no-sign", action="store_true")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.isfile(os.path.join(src, "AndroidManifest.xml")):
        fail("no AndroidManifest.xml in %s" % src)

    # Resolve JDK / SDK: flag > --tools-root > setup_toolchain.py config > env vars > known paths.
    cfg = load_toolchain_json(extra_roots=[args.tools_root] if args.tools_root else None)
    if args.tools_root:
        tools = os.path.abspath(args.tools_root)
        jdk = args.jdk or cfg.get("jdk") or os.path.join(tools, "jdk17")
        sdk = args.sdk or cfg.get("sdk") or os.path.join(tools, "android-sdk")
    else:
        jdk = args.jdk or cfg.get("jdk") or detect_jdk()
        sdk = args.sdk or cfg.get("sdk") or detect_sdk()
    if not jdk:
        fail("no JDK found; pass --jdk or set JAVA_HOME")
    if not sdk:
        fail("no Android SDK found; pass --sdk or set ANDROID_SDK_ROOT / ANDROID_HOME")
    jdk = os.path.abspath(jdk)
    sdk = os.path.abspath(sdk)
    bt = args.build_tools or newest_subdir(os.path.join(sdk, "build-tools")) \
        or os.path.join(sdk, "build-tools", "34.0.0")
    android_jar = os.path.join(sdk, "platforms", "android-%s" % args.target_sdk, "android.jar")
    for path in (jdk, bt, android_jar):
        if not os.path.exists(path):
            fail("missing toolchain path: %s" % path)
    print("  jdk = %s" % jdk)
    print("  sdk = %s" % sdk)

    build = os.path.join(src, "build-py")
    if args.clean and os.path.isdir(build):
        shutil.rmtree(build)
    for sub in ("res", "gen", "obj", "dex"):
        os.makedirs(os.path.join(build, sub), exist_ok=True)

    env = os.environ.copy()
    env["JAVA_HOME"] = jdk
    env["PATH"] = os.path.join(jdk, "bin") + os.pathsep + bt + os.pathsep + env.get("PATH", "")

    aapt2 = os.path.join(bt, "aapt2.exe" if IS_WIN else "aapt2")
    zipalign = os.path.join(bt, "zipalign.exe" if IS_WIN else "zipalign")
    d8 = os.path.join(bt, "d8.bat" if IS_WIN else "d8")
    apksigner = os.path.join(bt, "apksigner.bat" if IS_WIN else "apksigner")
    javac = os.path.join(jdk, "bin", "javac.exe" if IS_WIN else "javac")
    keytool = os.path.join(jdk, "bin", "keytool.exe" if IS_WIN else "keytool")

    print("=" * 58)
    print(" APK build  src=%s  minSdk=%s  targetSdk=%s" % (src, args.min_sdk, args.target_sdk))
    print("=" * 58)

    print("[1/7] aapt2 compile resources")
    compiled = os.path.join(build, "res", "compiled.zip")
    sh([aapt2, "compile", "--dir", os.path.join(src, "res"), "-o", compiled], cwd=src, env=env)

    print("[2/7] aapt2 link -> unsigned.apk + R.java")
    unsigned = os.path.join(build, "unsigned.apk")
    sh([aapt2, "link", "-o", unsigned, "-I", android_jar,
        "--manifest", os.path.join(src, "AndroidManifest.xml"),
        "--java", os.path.join(build, "gen"),
        "--min-sdk-version", args.min_sdk,
        "--target-sdk-version", args.target_sdk, compiled], cwd=src, env=env)

    print("[3/7] javac compile sources")
    sources = find_sources(os.path.join(src, "java"), ".java") + find_sources(os.path.join(build, "gen"), ".java")
    if not sources:
        fail("no .java sources found")
    sh([javac, "-encoding", "UTF-8", "-nowarn", "-source", "17", "-target", "17",
        "-classpath", android_jar, "-d", os.path.join(build, "obj")] + sources, cwd=src, env=env)

    print("[4/7] d8 -> classes.dex")
    classes = find_sources(os.path.join(build, "obj"), ".class")
    if not classes:
        fail("javac produced no .class files")
    sh([d8, "--lib", android_jar, "--release", "--output", os.path.join(build, "dex")] + classes,
       cwd=src, env=env)

    print("[5/7] inject classes.dex")
    dex = os.path.join(build, "dex", "classes.dex")
    if not os.path.isfile(dex):
        fail("d8 did not produce classes.dex")
    packed = os.path.join(build, "packed.apk")
    shutil.copyfile(unsigned, packed)
    with zipfile.ZipFile(packed, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(dex, "classes.dex")

    print("[6/7] zipalign")
    aligned = os.path.join(build, "aligned.apk")
    sh([zipalign, "-f", "-p", "4", packed, aligned], cwd=src, env=env)

    out = os.path.abspath(args.out or os.path.join(src, "app.apk"))

    if args.no_sign:
        shutil.copyfile(aligned, out)
        print("[7/7] skipped signing (--no-sign)")
    else:
        print("[7/7] sign")
        ks, alias, storepass, keypass = (args.ks, args.alias, args.storepass, args.keypass)

        # No explicit keystore -> use the developer's own personal identity.
        if not ks:
            ks, p_alias, p_store, p_key, p_file = find_personal_keystore(cfg)
            if ks:
                alias = alias or p_alias
                storepass = storepass or p_store
                keypass = keypass or p_key
                print("  -> personal keystore %s" % ks)
            elif not args.no_keystore_setup:
                setup = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "setup_keystore.py")
                if os.path.isfile(setup):
                    target = keystore_roots(cfg)[0]
                    print("  -> no personal keystore yet, creating one in %s" % target)
                    proc = subprocess.run([sys.executable, setup, "--dir", target],
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    if proc.returncode != 0:
                        print(proc.stdout.decode("utf-8", "replace"))
                    ks, p_alias, p_store, p_key, p_file = find_personal_keystore(cfg)
                    alias = alias or p_alias
                    storepass = storepass or p_store
                    keypass = keypass or p_key

        # Last resort: a throwaway per-project key so the build never dies.
        if not ks:
            ks = os.path.abspath(os.path.join(src, "debug.jks"))
            alias = alias or "apkkey"
            if os.path.isfile(ks):
                saved = load_props(os.path.join(src, "debug.keystore.properties")) \
                    if os.path.isfile(os.path.join(src, "debug.keystore.properties")) else {}
                storepass = storepass or saved.get("storepass")
                keypass = keypass or saved.get("keypass")
            if not os.path.isfile(ks):
                # PKCS12: key password must equal store password.
                storepass = storepass or secrets.token_urlsafe(18)
                keypass = storepass
                print("  -> generating throwaway key %s" % ks)
                sh([keytool, "-genkeypair", "-v", "-keystore", ks, "-keyalg", "RSA",
                    "-keysize", "2048", "-validity", "10950", "-alias", alias,
                    "-storepass", storepass, "-keypass", keypass,
                    "-dname", "CN=APK Builder, O=Android App Zero To One, C=CN"],
                   cwd=src, env=env)
                with open(os.path.join(src, "debug.keystore.properties"), "w",
                          encoding="utf-8") as f:
                    f.write("ks=%s\nalias=%s\nstorepass=%s\nkeypass=%s\n"
                            % (ks.replace("\\", "\\\\"), alias, storepass, keypass))
            print("  -> WARNING: throwaway key; this apk cannot be upgraded later."
                  " Run scripts/setup_keystore.py once.")

        if not storepass or not keypass:
            fail("keystore found but no password; pass --storepass/--keypass")

        sh([apksigner, "sign", "--ks", ks, "--ks-key-alias", alias,
            "--ks-pass", "pass:%s" % storepass, "--key-pass", "pass:%s" % keypass,
            "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
            "--out", out, aligned], cwd=src, env=env)
        idsig = out + ".idsig"
        if os.path.isfile(idsig):
            os.remove(idsig)

        verify = subprocess.run([apksigner, "verify", out], cwd=src, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if verify.returncode != 0:
            print(verify.stdout.decode("utf-8", "replace"))
            fail("signature verification failed")
        print("  -> verified: signature is valid")

    print("")
    print("=" * 58)
    print(" BUILD OK -> %s (%d bytes)" % (out, os.path.getsize(out)))
    print("=" * 58)


if __name__ == "__main__":
    main()
