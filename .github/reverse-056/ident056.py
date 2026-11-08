# reverse request 056 identity checks (temp branch only, never merged). All comparisons happen here; exit code decides.
# usage:
#   ident056.py raw <dir>
#   ident056.py pre <tree>
#   ident056.py post <tree> <A|B>
#   ident056.py prefix <tree> <prefix> <stage-label>
#   ident056.py pins <tree> <stage-label>
import hashlib
import json
import pathlib
import subprocess
import sys

BASE = '3a91fab9e80d2a92be071a74b8b208214d7e6277'
M = 'runtime/media/dsh-media/'
RAW = {
    'FULL': ('2602-media-secret-original-strings-LF.patch', 4460, '133ee421726b2e41fdaaa03db7609fbd8624a630a65a3f90c080b3cb32a0bf13'),
    'TESTONLY': ('2602-TESTONLY-media-secret-original-strings-LF.patch', 1713, 'e74d5f0271a0c2b6971bdea5b310475bc08bd34034d8463992bd786c7a3ad0cd'),
}
# Required by the request text.
FIXED = {
    'runtime/locks/dsh-0.2.2-rc.1/package-lock.json': (410906, '9809a7a64fd5d40df441a30fb4407c037802162d75e8a8e39dc0ef2569bec2ab'),
    M + 'test/headless-v2/prepare.mjs': (2123, 'd4990c2fca426cfda82f66dd006f40d3a442178bf08379e1642bd5014ce58024'),
    'runtime/patches/pins.json': (72096, '2a3d04e05708e887f00be0a80338ead13b4ca1e1c72c5bf300be02bd266e53fb'),
}
# From the attachment's 056-base-identities.json: reported, not gating.
REPORT_ONLY_BASE = {
    'runtime/locks/dsh-0.2.2-rc.1/package.json': (126, 'ff39278b4a4eb3b92cb77f4b281be810bfebe24b4c9ce50b67e25959ea9c067f'),
    M + 'package.json': (1869, 'b2b807a588711cbd0262a8eb99882c86ad3af7717b3912b71550574c6ed1df30'),
    M + 'test/media-v2.test.js': (24911, '7783230afe316c0749aee60d1be5d1715948673ce94944ace9161fa8d016d635'),
}
TEST = (25920, 'b90e889ae9d97071aa2e784cda2dbe20918ece301744ab2734e4a446b4f21e75')
SRC = {
    'A': {M + 'src/core.js': (13266, '970c82f299e258649611a0b31687d1eea402589772c97aaef0ec3e1cf3d435ed'),
          M + 'src/media-engine.js': (10442, 'a4d851ce3bc876b8c6451cede1f74b888abe7e8302501fa24876f620792fb12e'),
          M + 'test/media-v2.test.js': TEST},
    'B': {M + 'src/core.js': (13273, 'db541f43e414c1f85e183cd4b63d47b292578ae57e440d668e4996a5cd597d50'),
          M + 'src/media-engine.js': (10440, '681f57d0d8a21e68379913e6e0d29c543b64231329b8e2d121e1ae48dc105023'),
          M + 'test/media-v2.test.js': TEST},
}
CHANGED = {'A': {M + 'test/media-v2.test.js'},
           'B': {M + 'src/core.js', M + 'src/media-engine.js', M + 'test/media-v2.test.js'}}
PREFIX_OUT = {
    'package.json': (207, '456c54133f7a308bf9b13b43b85715b6860eaee97ce78563d8e23e488a3232b6'),
    'package-lock.json': (411636, '1a3861b63591a7456e9aa880d044df19da00ad149e2b9e78b613967f218e1af8'),
    'test-inputs.json': (308, '4841f599016963ddf8156f87342eab6a024d43ca4475bbff1a576053c775efb4'),
}
ADDED = {'node_modules/@deepseek-ai/dsh-llm-mock-server': '0.2.2-rc.1', 'node_modules/image-size': '2.0.2'}

bad = []


def ident(path):
    b = pathlib.Path(path).read_bytes()
    return b, len(b), hashlib.sha256(b).hexdigest()


def check(label, path, want, gating=True, text=False):
    b, n, h = ident(path)
    ok = (n, h) == want
    extra = ''
    if text:
        cr = b.count(b'\r')
        tail = b.endswith(b'\n')
        extra = ' cr=%d tail_lf=%s' % (cr, tail)
        ok = ok and cr == 0 and tail
    print('%s %s bytes=%d sha256=%s%s %s' % ('MATCH' if ok else ('MISMATCH' if gating else 'MISMATCH(report-only)'), label, n, h, extra, path))
    if gating and not ok:
        bad.append(label)


def git(tree, *args):
    r = subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', tree, *args], capture_output=True)
    print('GIT %s exit=%d' % (' '.join(args), r.returncode))
    if r.returncode != 0:
        bad.append('git ' + ' '.join(args))
        sys.stdout.write(r.stderr.decode('utf-8', 'replace'))
    return r.stdout.decode('utf-8')


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
        print(st)
        bad.append('clean')
    for p, w in FIXED.items():
        check('BASE ' + p, pathlib.Path(tree) / p, w)
    for p, w in SRC['A'].items():
        if p.endswith('.js') and 'src/' in p:
            check('BASE ' + p, pathlib.Path(tree) / p, w, text=True)
    for p, w in REPORT_ONLY_BASE.items():
        check('BASE ' + p, pathlib.Path(tree) / p, w, gating=False)
elif mode == 'post':
    tree, which = sys.argv[2], sys.argv[3]
    names = set(git(tree, 'diff', '--name-only').split())
    print('CHANGED_PATHS=%s expected=%s %s' % (sorted(names), sorted(CHANGED[which]), 'MATCH' if names == CHANGED[which] else 'MISMATCH'))
    if names != CHANGED[which]:
        bad.append('changed-paths')
    for line in git(tree, 'diff', '--raw', '--no-abbrev').splitlines():
        meta = line.split('\t')[0].split()
        same = meta[0] == ':100644' and meta[1] == '100644' and meta[4] == 'M'
        print('RAWDIFF %s %s' % ('MODE_SAME_M' if same else 'MODE_OR_STATUS_CHANGED', line))
        if not same:
            bad.append('mode')
    st = git(tree, 'status', '--porcelain=v1', '--untracked-files=all').splitlines()
    want = sorted(' M ' + p for p in CHANGED[which])
    print('STATUS=%s %s' % (st, 'MATCH' if sorted(st) == want else 'MISMATCH'))
    if sorted(st) != want:
        bad.append('status')
    for p, w in SRC[which].items():
        check('FINAL_%s %s' % (which, p), pathlib.Path(tree) / p, w, text=True)
    for p, w in FIXED.items():
        check('UNCHANGED ' + p, pathlib.Path(tree) / p, w)
elif mode == 'prefix':
    tree, pfx, stage = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), sys.argv[4]
    for name, w in PREFIX_OUT.items():
        check('PREFIX_%s %s' % (stage, name), pfx / name, w)
    orig = json.loads((tree / 'runtime/locks/dsh-0.2.2-rc.1/package-lock.json').read_bytes())
    gen = json.loads((pfx / 'package-lock.json').read_bytes())
    op, gp = orig['packages'], gen['packages']
    nonroot = [k for k in op if k != '']
    same = [k for k in nonroot if k in gp and gp[k] == op[k]]
    added = {k: gp[k].get('version') for k in gp if k not in op}
    print('LOCK_%s original_nonroot=%d preserved_identical=%d added=%s' % (stage, len(nonroot), len(same), json.dumps(added, sort_keys=True)))
    if not (len(nonroot) == 661 and len(same) == 661 and added == ADDED):
        bad.append('lock-compare')
    root_o, root_g = op[''], gp['']
    dep_diff = {k: root_g['dependencies'].get(k) for k in set(root_g.get('dependencies', {})) ^ set(root_o.get('dependencies', {}))}
    other_root = sorted(k for k in set(root_o) | set(root_g) if k != 'dependencies' and root_o.get(k) != root_g.get(k))
    other_top = sorted(k for k in set(orig) | set(gen) if k != 'packages' and orig.get(k) != gen.get(k))
    print('LOCK_%s root_dependency_additions=%s root_other_changed=%s top_level_other_changed=%s (report-only)' % (stage, json.dumps(dep_diff, sort_keys=True), other_root, other_top))
    ti = json.loads((pfx / 'test-inputs.json').read_bytes())
    print('TEST_INPUTS_%s %s' % (stage, json.dumps(ti, sort_keys=True)))
elif mode == 'pins':
    tree, stage = pathlib.Path(sys.argv[2]), sys.argv[3]
    check('PINS_' + stage, tree / 'runtime/patches/pins.json', FIXED['runtime/patches/pins.json'])
else:
    print('unknown mode')
    sys.exit(2)

print('IDENT_%s=%s %s' % (mode.upper(), 'PASS' if not bad else 'FAIL', bad))
sys.exit(0 if not bad else 1)
