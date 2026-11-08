# reverse request 063 identity checks (temp branch only, never merged). All comparisons in Python; exit code decides.
# Loads no product code (reads bytes and runs git only).
# usage:
#   ident063.py raw <dir>
#   ident063.py pre <tree>
#   ident063.py post <tree> <A|B> <raw patch> <stage> <out diff file> <out status file>
import hashlib
import os
import pathlib
import subprocess
import sys

BASE = '3a91fab9e80d2a92be071a74b8b208214d7e6277'
CORE = 'runtime/bridge/dsh-go-bridge/lib/native/core.js'
FEED = 'runtime/tests/native-feed-clock.test.mjs'
IDLE = 'runtime/tests/native-feed-idle-cost.test.mjs'
FIXT = 'runtime/tests/support/native-feed-fixture.mjs'
PINS = 'runtime/patches/pins.json'
RAW = {
    'FULL': ('2608-native-feed-monotonic-LF.patch', 8127, '684c7617f9d935408e89f4a6f98060ce569c2173187457cf8abca3721a90556e'),
    'TESTONLY': ('2608-TESTONLY-native-feed-monotonic-LF.patch', 6250, 'de188cc0fe262e3be0fab7dc38c178db1541137dcd841c28593206c00d8eded4'),
}
BASE_IDS = {
    CORE: (27603, 'b7b7c1134669942ab66325d1d33054dc2001cdf7184b077b6d1517831a2c0f3b'),
    IDLE: (3839, '180f5f097aa767d85d3339bab716863590caaebc812e5185111a40187570563e'),
    FIXT: (1764, '53cade75d9e011e497a019c2116630ff62a8e5a2e36ea6f0d021b35d75e24679'),
    PINS: (72096, '2a3d04e05708e887f00be0a80338ead13b4ca1e1c72c5bf300be02bd266e53fb'),
}
FEED_ID = (5814, 'e96f680d052929c7fcfc0444feba848fcc52b1102e46332bfa2779d4a0abbd4b')
FEED_LINES = 150
FINAL = {
    'A': {CORE: BASE_IDS[CORE], FEED: FEED_ID, IDLE: BASE_IDS[IDLE], FIXT: BASE_IDS[FIXT]},
    'B': {CORE: (27724, 'b687b093748af5800e4f28551c71b458439c40637941dbf458a4868e1490b49b'), FEED: FEED_ID,
          IDLE: BASE_IDS[IDLE], FIXT: BASE_IDS[FIXT]},
}
STATUS = {
    'A': sorted([' A ' + FEED]),
    'B': sorted([' M ' + CORE, ' A ' + FEED]),
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
        i = full.find(b'diff --git a/' + FEED.encode())
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
    absent = not (pathlib.Path(tree) / FEED).exists()
    print('BASE_FEED_TEST_ABSENT=%s %s' % (absent, FEED))
    if not absent:
        bad.append('feed-test-present')
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
        ok = m[1] == '100644' and ((path == FEED and m[0] == ':000000' and m[4] == 'A') or
                                   (path == CORE and which == 'B' and m[0] == ':100644' and m[4] == 'M'))
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
              lines=FEED_LINES if p == FEED else None)
    check('PINS_%s_%s' % (which, stage), pathlib.Path(tree) / PINS, BASE_IDS[PINS])
    node_modules(tree)
    dsh_prefix()
else:
    print('unknown mode'); sys.exit(2)

print('IDENT_%s=%s %s' % (mode.upper(), 'PASS' if not bad else 'FAIL', bad))
sys.exit(0 if not bad else 1)
