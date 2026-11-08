# reverse request 062 identity checks (temp branch only, never merged). All comparisons in Python; exit code decides.
# Loads no product code (reads bytes and runs git only).
# usage:
#   ident062.py raw <dir>
#   ident062.py pre <tree>
#   ident062.py post <tree> <A|B> <raw patch> <stage> <out diff file> <out status file>
import hashlib
import os
import pathlib
import subprocess
import sys

BASE = '3a91fab9e80d2a92be071a74b8b208214d7e6277'
ROUTES = 'runtime/bridge/dsh-go-bridge/lib/native/routes.js'
STREAM = 'runtime/tests/native-stream-clock.test.mjs'
WSCLOSE = 'runtime/tests/native-ws-close-timer.test.mjs'
CAPS = 'runtime/tests/native-capabilities.test.mjs'
PINS = 'runtime/patches/pins.json'
RAW = {
    'FULL': ('2607-native-stream-monotonic-LF.patch', 16766, '92e008812380b1f01e710b0d257cc37ba535a4fccdec73a98ff792aab6b48e26'),
    'TESTONLY': ('2607-TESTONLY-native-stream-monotonic-LF.patch', 14540, '5b01076834d2910bd6e09e221cfc510b9acf6b48d555856bc2c216ffd75cbc88'),
}
BASE_IDS = {
    ROUTES: (32406, '6a5f89fa2dfcc47ef50c0de7db0d14d2d3e0050cabad1b3f763a84ce947b986d'),
    WSCLOSE: (2584, '5ad74b1063a261c3799b7bf4dc9e7ed4ab1c26751e9c89ea4e27229d651fc29a'),
    CAPS: (31637, 'cdab252474d0c2f1d3e58a6182882ddf5f4ddb4f1428c8e5e46f929c3782224f'),
    PINS: (72096, '2a3d04e05708e887f00be0a80338ead13b4ca1e1c72c5bf300be02bd266e53fb'),
}
STREAM_ID = (13958, '8e67cdfe9643358c0fa21dee09499fc4a05db5d0aaefcd666b2d9b3f7dbe3f60')
STREAM_LINES = 290
FINAL = {
    'A': {ROUTES: BASE_IDS[ROUTES], STREAM: STREAM_ID, WSCLOSE: BASE_IDS[WSCLOSE], CAPS: BASE_IDS[CAPS]},
    'B': {ROUTES: (32493, 'a2e44c23c161d975df2b8ba25bf9b82995ba22433f53f9fd73e0aa31614a24b4'), STREAM: STREAM_ID,
          WSCLOSE: BASE_IDS[WSCLOSE], CAPS: BASE_IDS[CAPS]},
}
STATUS = {
    'A': sorted([' A ' + STREAM]),
    'B': sorted([' M ' + ROUTES, ' A ' + STREAM]),
}
bad = []


def check(label, path, want, text=False, lines=None):
    p = pathlib.Path(path)
    if not p.is_file():
        print('MISSING %s %s' % (label, path)); bad.append(label); return
    b = p.read_bytes(); n, h = len(b), hashlib.sha256(b).hexdigest()
    ok = (n, h) == want
    extra = ''
    if text:
        extra = ' cr=%d tail_lf=%s' % (b.count(b'\r'), b.endswith(b'\n'))
        ok = ok and b.count(b'\r') == 0 and b.endswith(b'\n')
    if lines is not None:
        extra += ' lines=%d (want %d)' % (b.count(b'\n'), lines)
        ok = ok and b.count(b'\n') == lines
    print('%s %s bytes=%d sha256=%s%s %s' % ('MATCH' if ok else 'MISMATCH', label, n, h, extra, path))
    if not ok:
        bad.append(label)


def git(tree, *args, raw=False):
    r = subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', tree, *args], capture_output=True)
    print('GIT %s exit=%d' % (' '.join(args), r.returncode))
    if r.returncode != 0:
        bad.append('git ' + ' '.join(args)); sys.stdout.write(r.stderr.decode('utf-8', 'replace'))
    return r.stdout if raw else r.stdout.decode('utf-8')


def node_modules(tree):
    found = []
    for root, dirs, files in os.walk(tree):
        if '.git' in dirs:
            dirs.remove('.git')
        for d in list(dirs) + [f for f in files if f == 'node_modules']:
            if d == 'node_modules':
                found.append(os.path.relpath(os.path.join(root, d), tree))
        dirs[:] = [d for d in dirs if d != 'node_modules']
    print('NODE_MODULES_IN_TREE=%d %s (gate: must be 0, ignored and untracked included; product tree only)' % (len(found), found))
    if found:
        bad.append('node_modules present')


def dsh_prefix():
    print('ENV DSH_PREFIX=%s (must be unset)' % os.environ.get('DSH_PREFIX', '<unset>'))
    if 'DSH_PREFIX' in os.environ:
        bad.append('DSH_PREFIX set')


mode = sys.argv[1]
if mode == 'raw':
    d = pathlib.Path(sys.argv[2])
    for k, (name, n, h) in RAW.items():
        check('RAW_' + k, d / name, (n, h), text=True)
    if not bad:
        full = (d / RAW['FULL'][0]).read_bytes()
        tonly = (d / RAW['TESTONLY'][0]).read_bytes()
        i = full.find(b'diff --git a/' + STREAM.encode())
        seg = full[i:] if i >= 0 else b''
        j = seg.find(b'\ndiff --git ', 1)
        seg = seg if j < 0 else seg[:j + 1]
        same = i >= 0 and seg == tonly
        print('FULL_NEW_TEST_SEGMENT bytes=%d sha256=%s %s' % (len(seg), hashlib.sha256(seg).hexdigest(),
              'BYTE_EQUAL_TESTONLY' if same else 'DIFFERS_FROM_TESTONLY'))
        if not same:
            bad.append('FULL test segment != TESTONLY')
elif mode == 'pre':
    tree = sys.argv[2]
    head = git(tree, 'rev-parse', 'HEAD').strip()
    print('HEAD=%s expected=%s %s' % (head, BASE, 'MATCH' if head == BASE else 'MISMATCH'))
    if head != BASE:
        bad.append('HEAD')
    st = git(tree, 'status', '--porcelain=v1', '--untracked-files=all')
    print('STATUS_LINES=%d (must be 0)' % len(st.splitlines()))
    if st.strip():
        print(st); bad.append('clean')
    for p, w in BASE_IDS.items():
        check('BASE ' + p, pathlib.Path(tree) / p, w, text=(p != PINS))
    absent = not (pathlib.Path(tree) / STREAM).exists()
    print('BASE_STREAM_TEST_ABSENT=%s %s' % (absent, STREAM))
    if not absent:
        bad.append('stream-test-present')
    node_modules(tree)
    dsh_prefix()
elif mode == 'post':
    tree, which, rawp, stage, outp, outs = sys.argv[2:8]
    diff = git(tree, 'diff', '--full-index', '--binary', '--no-ext-diff', raw=True)
    pathlib.Path(outp).write_bytes(diff)
    rawb = pathlib.Path(rawp).read_bytes()
    same = diff == rawb
    print('DIFF_%s bytes=%d sha256=%s raw_bytes=%d raw_sha256=%s %s' % (stage, len(diff), hashlib.sha256(diff).hexdigest(),
          len(rawb), hashlib.sha256(rawb).hexdigest(), 'BYTE_EQUAL_RAW' if same else 'DIFFERS_FROM_RAW'))
    if not same:
        bad.append('diff!=raw')
    names = sorted(git(tree, 'diff', '--name-only').split())
    want_names = sorted(p[3:] for p in STATUS[which])
    print('CHANGED_PATHS=%s %s' % (names, 'MATCH' if names == want_names else 'MISMATCH'))
    if names != want_names:
        bad.append('paths')
    for line in git(tree, 'diff', '--raw', '--no-abbrev').splitlines():
        meta, path = line.split('\t', 1)
        m = meta.split()
        ok = m[1] == '100644' and ((path == STREAM and m[0] == ':000000' and m[4] == 'A') or
                                   (path == ROUTES and which == 'B' and m[0] == ':100644' and m[4] == 'M'))
        print('RAWDIFF %s %s <TAB> %s' % ('MODE_OK' if ok else 'MODE_OR_STATUS_UNEXPECTED', meta, path))
        if not ok:
            bad.append('mode ' + path)
    stb = git(tree, 'status', '--porcelain=v1', '--untracked-files=all', raw=True)
    pathlib.Path(outs).write_bytes(stb)
    st = stb.decode('utf-8').splitlines()
    print('STATUS_RAW bytes=%d sha256=%s lines=%s' % (len(stb), hashlib.sha256(stb).hexdigest(), st))
    print('STATUS_SORTED=%s %s (record-semantic comparison after sorting, not a raw-byte claim)' % (
        sorted(st), 'MATCH' if sorted(st) == STATUS[which] else 'MISMATCH'))
    if sorted(st) != STATUS[which]:
        bad.append('status')
    for p, w in FINAL[which].items():
        check('FINAL_%s_%s %s' % (which, stage, p), pathlib.Path(tree) / p, w, text=True,
              lines=STREAM_LINES if p == STREAM else None)
    check('PINS_%s_%s' % (which, stage), pathlib.Path(tree) / PINS, BASE_IDS[PINS])
    node_modules(tree)
    dsh_prefix()
else:
    print('unknown mode'); sys.exit(2)

print('IDENT_%s=%s %s' % (mode.upper(), 'PASS' if not bad else 'FAIL', bad))
sys.exit(0 if not bad else 1)
