#!/usr/bin/env python3
"""Create YOUR OWN signing identity, stored on your machine only.

There is deliberately no shared/bundled certificate in this skill. Every
developer must generate a personal keystore once; every APK you build is then
signed with it, which is what lets Android treat new builds as upgrades of
your earlier builds.

If you lose this file you can still sign new apps, but you can never again
update an app that was signed with it - Android refuses an upgrade whose
signature changed. Back it up.

Usage:
    python setup_keystore.py [--dir <root>] [--name "Your Name"] [--org "Your Org"]
                             [--country CN] [--alias apkkey] [--validity 10950]
                             [--force] [--jdk <path>]

Writes:
    <root>/certs/personal.jks          the keystore (your identity)
    <root>/certs/keystore.properties   alias + passwords, local only

Default root: ~/.android-zero-to-one (the same root setup_toolchain.py uses).
"""

import argparse
import json
import os
import secrets
import stat
import subprocess
import sys

PROPS_NAME = "keystore.properties"


def log(msg):
    print(msg, flush=True)


def fail(msg):
    print("\n[SETUP FAILED] %s" % msg, file=sys.stderr)
    sys.exit(1)


def toolchain_root(explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    v = os.environ.get("ANDROID_TOOLS_ROOT")
    if v:
        return os.path.abspath(v)
    return os.path.join(os.path.expanduser("~"), ".android-zero-to-one")


def find_jdk(root):
    """JDK from toolchain.json, then JAVA_HOME, then the usual spots."""
    cfg = os.path.join(root, "toolchain.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                jdk = json.load(f).get("jdk")
            if jdk and os.path.isdir(jdk):
                return jdk
        except Exception:
            pass
    v = os.environ.get("JAVA_HOME")
    if v and os.path.isdir(v):
        return v
    home = os.path.expanduser("~")
    for g in (os.path.join(root, "jdk-17"), os.path.join(home, "jdk17")):
        if os.path.isdir(g):
            inner = [d for d in os.listdir(g)
                     if d.startswith("jdk-") and os.path.isdir(os.path.join(g, d))]
            if inner:
                return os.path.join(g, sorted(inner)[-1])
            return g
    return None


def lock_down(path):
    """Best-effort: make the password file readable only by this user."""
    try:
        if os.name == "nt":
            subprocess.run(["icacls", path, "/inheritance:r", "/grant:r",
                            "%USERNAME%:(R,W)"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        else:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Create a personal APK signing identity.")
    ap.add_argument("--dir", default=None, help="root (default ~/.android-zero-to-one)")
    ap.add_argument("--name", default=None, help="your name, goes into the certificate CN")
    ap.add_argument("--org", default=None, help="organisation (default: same as --name)")
    ap.add_argument("--country", default="CN", help="two-letter country code")
    ap.add_argument("--alias", default="apkkey")
    ap.add_argument("--validity", type=int, default=10950, help="days (default 10950 = 30y)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing keystore")
    ap.add_argument("--jdk", default=None, help="JDK home (default: toolchain.json / JAVA_HOME)")
    args = ap.parse_args()

    root = toolchain_root(args.dir)
    certs = os.path.join(root, "certs")
    ks = os.path.join(certs, "personal.jks")
    props = os.path.join(certs, PROPS_NAME)

    name = args.name or os.environ.get("USERNAME") or os.environ.get("USER") or "apk-builder"
    org = args.org or name

    if os.path.isfile(ks) and not args.force:
        log("=" * 58)
        log(" Personal keystore already exists")
        log("   %s" % ks)
        log("=" * 58)
        log(" Reusing it. --force only if you really want a new identity")
        log(" (a new identity cannot update apps signed with the old one).")
        log("=" * 58)
        return

    jdk = args.jdk or find_jdk(root)
    if not jdk:
        fail("no JDK found. Run setup_toolchain.py first, or pass --jdk <path>.")
    keytool = os.path.join(jdk, "bin", "keytool.exe" if os.name == "nt" else "keytool")
    if not os.path.isfile(keytool):
        fail("keytool not found at %s" % keytool)

    if args.force and os.path.isfile(ks):
        log("  --force: replacing the existing keystore")
        os.remove(ks)

    os.makedirs(certs, exist_ok=True)
    # PKCS12 (keytool's default store type since JDK 9) cannot decrypt a key
    # whose password differs from the store password - it fails with
    # "Given final block not properly padded". So: one secret for both.
    storepass = secrets.token_urlsafe(24)
    keypass = storepass
    dname = "CN=%s, OU=Android App, O=%s, L=Unknown, ST=Unknown, C=%s" % (name, org, args.country)

    log("=" * 58)
    log(" Creating your personal signing identity")
    log("  keystore = %s" % ks)
    log("  subject  = %s" % dname)
    log("  validity = %d days" % args.validity)
    log("=" * 58)

    proc = subprocess.run(
        [keytool, "-genkeypair", "-v", "-keystore", ks, "-keyalg", "RSA", "-keysize", "2048",
         "-validity", str(args.validity), "-alias", args.alias,
         "-storepass", storepass, "-keypass", keypass, "-dname", dname],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0 or not os.path.isfile(ks):
        print(out)
        fail("keytool failed")

    with open(props, "w", encoding="utf-8") as f:
        f.write("# Local only - never commit this file.\n")
        f.write("ks=%s\n" % ks.replace("\\", "\\\\"))
        f.write("alias=%s\n" % args.alias)
        f.write("storepass=%s\n" % storepass)
        f.write("keypass=%s\n" % keypass)
    lock_down(props)

    log("")
    log("=" * 58)
    log(" READY  your identity: %s" % dname)
    log("   keystore  %s" % ks)
    log("   passwords %s (owner-only)" % props)
    log("=" * 58)
    log(" build_apk.py now signs with this automatically - no flags needed.")
    log("")
    log(" IMPORTANT")
    log("  * Back up personal.jks + keystore.properties together.")
    log("  * Lose them and you cannot update apps already signed with them.")
    log("  * Never share them: anyone holding them can publish as you.")
    log("=" * 58)


if __name__ == "__main__":
    main()
