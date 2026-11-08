# reverse request 059 identity checks (temp branch only, never merged). All comparisons in Python; exit code decides.
# Loads no product code (reads bytes and runs git only).
# usage:
#   ident059.py raw <dir>
#   ident059.py pre <tree>
#   ident059.py post <tree> <A|B> <raw patch> <stage> <out diff file>
import hashlib
import os
import pathlib
import subprocess
import sys

BASE = '3a91fab9e80d2a92be071a74b8b208214d7e6277'
RT = 'runtime/bridge/dsh-go-bridge/lib/native/capability-runtime.js'
CLOCK = 'runtime/tests/native-capability-clock.test.mjs'
GEN = 'runtime/tests/native-micro-generation.test.mjs'
PINS = 'runtime/patches/pins.json'
RAW = {
    'FULL': ('2605-capability-monotonic-pacing-LF.patch', 19911, '20caddf59289cbec840e36f12d08ac3ee327bd564808f32c5d95c0013adbb87a'),
    'TESTONLY': ('2605-TESTONLY-capability-monotonic-pacing-LF.patch', 16831, '1f75793fe30772207ec0e40e0e6a61e3d0a2b78ec18387a4d4150c95ce95df73'),
}
BASE_IDS = {
    RT: (15276, '85d067b571b2ecca216d3b7f49e2cbb94a90bdda89aadb9beb74490d1c07bbca'),
    GEN: (6140, '638aa78f9a4d340cf3f7ef12d26f3a7e0cf25ddf172842fc22e1ab9654daf4b0'),
    PINS: (72096, '2a3d04e05708e887f00be0a80338ead13b4ca1e1c72c5bf300be02bd266e53fb'),
}
TESTS = {
    CLOCK: (14226, 'b716ce50d8668733dfcbb78bdc5027e8ed170646ff1648229e4055a036bcf3a2'),
    GEN: (6259, 'c5afb19b26c6c9063ae5b829049d31e250eb6e817cc283d11bd7bd03b08f5e70'),
}
FINAL = {
    'A': dict(TESTS, **{RT: BASE_IDS[RT]}),
    'B': dict(TESTS, **{RT: (15399, 'c94e7ec13d292d9e6720aa72eda3bf1d52868f014b155eff322b848371877eef')}),
}
STATUS = {
    'A': sorted([' A ' + CLOCK, ' M ' + GEN]),
    'B': sorted([' M ' + RT, ' A ' + CLOCK, ' M ' + GEN]),
}
bad = []


def check(label, path, want, text=False):
    p = pathlib.Path(path)
    if not p.is_file():
        print('MISSING %s %s' % (label, path)); bad.append(label); return
    b = p.read_bytes(); n, h = len(b), hashlib.sha256(b).hexdigest()
    ok = (n, h) == want
    extra = ''
    if text:
        extra = ' cr=%d tail_lf=%s' % (b.count(b'\r'), b.endswith(b'\n'))
        ok = ok and b.count(b'\r') == 0 and b.endswith(b'\n')
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
    print('NODE_MODULES_IN_TREE=%d %s (report-only)' % (len(found), found))


mode = sys.argv[1]
if mode == 'raw':
    d = pathlib.Path(sys.argv[2])
    for k, (name, n, h) in RAW.items():
        check('RAW_' + k, d / name, (n, h), text=True)
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
    absent = not (pathlib.Path(tree) / CLOCK).exists()
    print('BASE_CLOCK_ABSENT=%s %s' % (absent, CLOCK))
    if not absent:
        bad.append('clock-present')
    node_modules(tree)
elif mode == 'post':
    tree, which, rawp, stage, outp = sys.argv[2:7]
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
        ok = m[1] == '100644' and ((path == CLOCK and m[0] == ':000000' and m[4] == 'A') or (path != CLOCK and m[0] == ':100644' and m[4] == 'M'))
        print('RAWDIFF %s %s <TAB> %s' % ('MODE_OK' if ok else 'MODE_OR_STATUS_UNEXPECTED', meta, path))
        if not ok:
            bad.append('mode ' + path)
    st = sorted(git(tree, 'status', '--porcelain=v1', '--untracked-files=all').splitlines())
    print('STATUS=%s %s' % (st, 'MATCH' if st == STATUS[which] else 'MISMATCH'))
    if st != STATUS[which]:
        bad.append('status')
    for p, w in FINAL[which].items():
        check('FINAL_%s_%s %s' % (which, stage, p), pathlib.Path(tree) / p, w, text=True)
    check('PINS_%s_%s' % (which, stage), pathlib.Path(tree) / PINS, BASE_IDS[PINS])
    node_modules(tree)
    print('ENV DSH_PREFIX=%s (must be unset)' % os.environ.get('DSH_PREFIX', '<unset>'))
    if 'DSH_PREFIX' in os.environ:
        bad.append('DSH_PREFIX set')
else:
    print('unknown mode'); sys.exit(2)

print('IDENT_%s=%s %s' % (mode.upper(), 'PASS' if not bad else 'FAIL', bad))
sys.exit(0 if not bad else 1)
