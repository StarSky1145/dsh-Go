# reverse request 064 identity checks (temp branch only, never merged). All comparisons in Python; exit code decides.
# Loads no product code (reads bytes and runs git only). Every diff here is explicitly relative to the fixed base commit:
#   git diff --full-index --binary --no-ext-diff <BASE> --
# usage:
#   ident064.py raw <dir>
#   ident064.py pre <tree>
#   ident064.py stage <tree> <A|B> <2608 raw patch> <out diff file> <out status file>
#   ident064.py post <tree> <A|B> <expected-combined patch> <label> <out diff file> <out status file>
import hashlib
import os
import pathlib
import subprocess
import sys

BASE = '3a91fab9e80d2a92be071a74b8b208214d7e6277'
CORE = 'runtime/bridge/dsh-go-bridge/lib/native/core.js'
FEED = 'runtime/tests/native-feed-clock.test.mjs'
INVOKE = 'runtime/tests/native-invoke-clock.test.mjs'
UNIT = 'runtime/tests/native-unit.test.mjs'
GEN = 'runtime/tests/native-invoke-generation.test.mjs'
PINS = 'runtime/patches/pins.json'
RAW = {
    '2608_FULL': ('2608-native-feed-monotonic-LF.patch', 8127, '684c7617f9d935408e89f4a6f98060ce569c2173187457cf8abca3721a90556e'),
    '2609_FULL': ('2609-native-invoke-monotonic-LF.patch', 14806, 'fa4f8f7798b003e254ee3a7e3a8e353f2f26d2969974a82971aeb596e5447309'),
    '2609_TESTONLY': ('2609-TESTONLY-native-invoke-monotonic-LF.patch', 14131, 'e51639ef354e611f6fcc55826d0e7a874439cf9ca07fc2012d5846ddf216eede'),
    'EXPECTED_A': ('2609-expected-combined-A.patch', 22258, 'c745dcc5ce95ba8cd76259866db17bff7d4e806d70c35a2c861724e6a78a8b41'),
    'EXPECTED_B': ('2609-expected-combined-B.patch', 22618, 'bb307c79ebb34a6401d8b2834187b16099c1c6203a6a8b49f97d69ce043ab4fd'),
}
BASE_IDS = {
    CORE: (27603, 'b7b7c1134669942ab66325d1d33054dc2001cdf7184b077b6d1517831a2c0f3b'),
    UNIT: (30892, '1355b3efe9fc39d5ba579fabdd25bd11cedf54be7032d0677cb25c9b83f7a8d4'),
    GEN: (14387, '3a068573c8060d983d923effdea36e68ad1b1c61e666abd362fc5fb5f4a1730b'),
    PINS: (72096, '2a3d04e05708e887f00be0a80338ead13b4ca1e1c72c5bf300be02bd266e53fb'),
}
CORE_2608 = (27724, 'b687b093748af5800e4f28551c71b458439c40637941dbf458a4868e1490b49b')
CORE_B = (27731, 'f368e62a2a29858ed2c890ca40eb4c3cfac5cb8c91b4506dd0313e2fd6ce295a')
FEED_ID, FEED_LINES = (5814, 'e96f680d052929c7fcfc0444feba848fcc52b1102e46332bfa2779d4a0abbd4b'), 150
INVOKE_ID, INVOKE_LINES = (13615, '305cf48ee9ac1fc9542776df17d41559ef0d96114ee2cc8c43aacf3d46acfd86'), 224
STAGE = {CORE: CORE_2608, FEED: FEED_ID, UNIT: BASE_IDS[UNIT], GEN: BASE_IDS[GEN]}
FINAL = {
    'A': {CORE: CORE_2608, FEED: FEED_ID, INVOKE: INVOKE_ID, UNIT: BASE_IDS[UNIT], GEN: BASE_IDS[GEN]},
    'B': {CORE: CORE_B, FEED: FEED_ID, INVOKE: INVOKE_ID, UNIT: BASE_IDS[UNIT], GEN: BASE_IDS[GEN]},
}
LINES = {FEED: FEED_LINES, INVOKE: INVOKE_LINES}
STATUS_STAGE = sorted([' M ' + CORE, ' A ' + FEED])
STATUS_FINAL = sorted([' M ' + CORE, ' A ' + FEED, ' A ' + INVOKE])
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


def seg(x, path):
    i = x.find(b'diff --git a/' + path.encode())
    if i < 0:
        return None
    s = x[i:]
    j = s.find(b'\ndiff --git ', 1)
    return s if j < 0 else s[:j + 1]


def whole_tree(tree, label, wantp, outp, outs, status_want, files_want, mode_want):
    diff = git(tree, 'diff', '--full-index', '--binary', '--no-ext-diff', BASE, '--', raw=True)
    pathlib.Path(outp).write_bytes(diff)
    wb = pathlib.Path(wantp).read_bytes()
    same = diff == wb
    print('DIFF_VS_BASE_%s bytes=%d sha256=%s want_bytes=%d want_sha256=%s %s (%s)' % (
        label, len(diff), hashlib.sha256(diff).hexdigest(), len(wb), hashlib.sha256(wb).hexdigest(),
        'BYTE_EQUAL' if same else 'DIFFERS', os.path.basename(wantp)))
    if not same:
        bad.append('diff vs base != ' + os.path.basename(wantp))
    idx = git(tree, 'diff', '--full-index', '--binary', '--no-ext-diff', raw=True)
    print('INFO_DIFF_INDEX_TO_WORKTREE_%s bytes=%d sha256=%s %s (information only; the gate is the base-relative diff)' % (
        label, len(idx), hashlib.sha256(idx).hexdigest(), 'BYTE_EQUAL_TO_BASE_RELATIVE' if idx == diff else 'DIFFERS'))
    names = sorted(git(tree, 'diff', '--name-only', BASE, '--').split())
    want_names = sorted(p[3:] for p in status_want)
    print('CHANGED_PATHS_VS_BASE=%s %s' % (names, 'MATCH' if names == want_names else 'MISMATCH'))
    if names != want_names:
        bad.append('paths')
    seen = []
    for line in git(tree, 'diff', '--raw', '--no-abbrev', BASE, '--').splitlines():
        meta, path = line.split('\t', 1)
        m = meta.split()
        ok = path in mode_want and (m[0], m[1], m[4]) == mode_want[path]
        seen.append(path)
        print('RAWDIFF %s %s <TAB> %s' % ('MODE_OK' if ok else 'MODE_OR_STATUS_UNEXPECTED', meta, path))
        if not ok:
            bad.append('mode ' + path)
    if sorted(seen) != sorted(mode_want):
        print('RAWDIFF_PATHS=%s MISMATCH (want %s)' % (sorted(seen), sorted(mode_want))); bad.append('raw paths')
    stb = git(tree, 'status', '--porcelain=v1', '--untracked-files=all', raw=True)
    pathlib.Path(outs).write_bytes(stb)
    st = stb.decode('utf-8').splitlines()
    print('STATUS_RAW bytes=%d sha256=%s lines=%s' % (len(stb), hashlib.sha256(stb).hexdigest(), st))
    print('STATUS_SORTED=%s %s (record-semantic comparison after sorting, not a raw-byte claim)' % (
        sorted(st), 'MATCH' if sorted(st) == status_want else 'MISMATCH'))
    if sorted(st) != status_want:
        bad.append('status')
    ign = git(tree, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored').splitlines()
    ign = [l for l in ign if l.startswith('!! ')]
    print('INFO_IGNORED_ENTRIES=%d %s (information; node_modules is gated separately)' % (len(ign), ign))
    for p, w in files_want.items():
        check('%s %s' % (label, p), pathlib.Path(tree) / p, w, text=True, lines=LINES.get(p))
    check('PINS_%s' % label, pathlib.Path(tree) / PINS, BASE_IDS[PINS])
    for p in (FEED, INVOKE):
        if p not in files_want:
            absent = not (pathlib.Path(tree) / p).exists()
            print('ABSENT_%s=%s %s' % (label, absent, p))
            if not absent:
                bad.append('present ' + p)
    node_modules(tree)
    dsh_prefix()


mode = sys.argv[1]
if mode == 'raw':
    d = pathlib.Path(sys.argv[2])
    for k, (name, n, h) in RAW.items():
        check('RAW_' + k, d / name, (n, h), text=True)
    if not bad:
        full = (d / RAW['2609_FULL'][0]).read_bytes()
        tonly = (d / RAW['2609_TESTONLY'][0]).read_bytes()
        sf, st = seg(full, INVOKE), seg(tonly, INVOKE)
        same = sf is not None and sf == st and st == tonly
        print('2609_FULL_NEW_TEST_SEGMENT bytes=%d sha256=%s TESTONLY_SEGMENT bytes=%d sha256=%s %s' % (
            len(sf or b''), hashlib.sha256(sf or b'').hexdigest(), len(st or b''), hashlib.sha256(st or b'').hexdigest(),
            'BYTE_EQUAL (TESTONLY consists of exactly this segment)' if same else 'DIFFER'))
        if not same:
            bad.append('2609 FULL test segment != TESTONLY')
elif mode == 'pre':
    tree = sys.argv[2]
    head = git(tree, 'rev-parse', 'HEAD').strip()
    print('HEAD=%s expected=%s %s' % (head, BASE, 'MATCH' if head == BASE else 'MISMATCH'))
    if head != BASE:
        bad.append('HEAD')
    st = git(tree, 'status', '--porcelain=v1', '--untracked-files=all')
    print('STATUS_LINES=%d (must be 0: tracked and non-ignored untracked)' % len(st.splitlines()))
    if st.strip():
        print(st); bad.append('clean')
    for p, w in BASE_IDS.items():
        check('BASE ' + p, pathlib.Path(tree) / p, w, text=(p != PINS))
    for p in (FEED, INVOKE):
        absent = not (pathlib.Path(tree) / p).exists()
        print('BASE_NEW_TEST_ABSENT=%s %s' % (absent, p))
        if not absent:
            bad.append('present ' + p)
    node_modules(tree)
    dsh_prefix()
elif mode == 'stage':
    tree, which, rawp, outp, outs = sys.argv[2:7]
    whole_tree(tree, '%s_STAGE_2608' % which, rawp, outp, outs, STATUS_STAGE, STAGE,
               {CORE: (':100644', '100644', 'M'), FEED: (':000000', '100644', 'A')})
elif mode == 'post':
    tree, which, expp, label, outp, outs = sys.argv[2:8]
    whole_tree(tree, '%s_%s' % (which, label), expp, outp, outs, STATUS_FINAL, FINAL[which],
               {CORE: (':100644', '100644', 'M'), FEED: (':000000', '100644', 'A'), INVOKE: (':000000', '100644', 'A')})
else:
    print('unknown mode'); sys.exit(2)

print('IDENT_%s=%s %s' % (mode.upper(), 'PASS' if not bad else 'FAIL', bad))
sys.exit(0 if not bad else 1)
