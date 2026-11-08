# reverse request 056 TAP reader (temp branch only, never merged).
# usage: tap056.py <gateA|summary> <tap stdout file> <exit code> <tree test file>
# gateA exits 0 only for the expected semantic red; summary always exits 0 (report only).
import re
import sys

mode, path, rc, testfile = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
NEW = ['media engine rejects quote-escaped credential in prompt before submission',
       'media engine rejects backslash-escaped credential in prompt before submission']
lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
src = open(testfile, encoding='utf-8').read().split('\n')
rejects_line = [i + 1 for i, s in enumerate(src) if "await assert.rejects(generateMedia(req, f.context), { code: 'credential' });" in s]
print('ASSERT_REJECTS_SOURCE_LINES=%s' % rejects_line)

point = re.compile(r'^(\s*)(not ok|ok) (\d+) - (.*)$')
points = []
for i, line in enumerate(lines):
    m = point.match(line)
    if not m:
        continue
    indent, status, num, rest = m.groups()
    name, directive = rest, ''
    dm = re.search(r' # (SKIP|TODO)\b.*$', rest, re.I)
    if dm:
        name, directive = rest[:dm.start()], dm.group(0)[3:]
    block = []
    j = i + 1
    if j < len(lines) and lines[j].strip() == '---':
        while j < len(lines):
            block.append(lines[j])
            if lines[j].strip() == '...':
                break
            j += 1
    points.append({'indent': len(indent), 'status': status, 'num': int(num), 'name': name, 'directive': directive, 'block': block})

summary = {}
for line in lines:
    m = re.match(r'^# (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms) (\S+)$', line)
    if m:
        summary[m.group(1)] = m.group(2)
print('EXIT=%d' % rc)
print('SUMMARY ' + ' '.join('%s=%s' % (k, summary.get(k, '?')) for k in ['tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo', 'duration_ms']))
print('TEST_POINTS=%d not_ok=%d skip_directive=%d todo_directive=%d' % (
    len(points), sum(p['status'] == 'not ok' for p in points),
    sum(p['directive'].upper().startswith('SKIP') for p in points), sum(p['directive'].upper().startswith('TODO') for p in points)))
for p in points:
    if p['status'] == 'not ok':
        print('NOT_OK indent=%d #%d %s %s' % (p['indent'], p['num'], p['name'], p['directive']))


def field(block, key):
    for i, b in enumerate(block):
        s = b.strip()
        if s.startswith(key + ':'):
            v = s[len(key) + 1:].strip()
            if v in ('|-', '|', '>-', '>'):  # YAML block scalar: join the more-indented lines
                ind = len(b) - len(b.lstrip())
                more = []
                for c in block[i + 1:]:
                    if c.strip() and len(c) - len(c.lstrip()) > ind:
                        more.append(c.strip())
                    else:
                        break
                v = v + ' ' + ' / '.join(more)
            return v
    return None


new_ok = True
for n in NEW:
    hits = [p for p in points if p['name'] == n]
    if not hits:
        print('NEW_CASE %s -> ZERO_MATCH' % n)
        new_ok = False
        continue
    for p in hits:
        stack_hit = [ln for ln in rejects_line if any(('media-v2.test.js:%d:' % ln) in b for b in p['block'])]
        print('NEW_CASE %s -> %s%s location=%s failureType=%s error=%s code=%s operator=%s stack_hits_assert_rejects_line=%s' % (
            n, p['status'], (' # ' + p['directive']) if p['directive'] else '', field(p['block'], 'location'),
            field(p['block'], 'failureType'), field(p['block'], 'error'), field(p['block'], 'code'),
            field(p['block'], 'operator'), stack_hit))
        for b in p['block']:
            print('    | ' + b)
    if mode == 'gateA':
        if len(hits) != 1:
            new_ok = False
            continue
        p = hits[0]
        err = field(p['block'], 'error') or ''
        if not (p['status'] == 'not ok' and not p['directive'] and 'Missing expected rejection' in err
                and field(p['block'], 'code') == "'ERR_ASSERTION'" and field(p['block'], 'failureType') == "'testCodeFailure'"):
            new_ok = False

if mode == 'gateA':
    not_ok_names = sorted(p['name'] for p in points if p['status'] == 'not ok')
    reasons = []
    if rc == 0:
        reasons.append('exit 0')
    if not_ok_names != sorted(NEW):
        reasons.append('not-ok set differs: %s' % not_ok_names)
    if not new_ok:
        reasons.append('new-case failure is not the expected Missing expected rejection / ERR_ASSERTION / testCodeFailure')
    if summary.get('fail') != '2' or summary.get('cancelled') != '0':
        reasons.append('summary fail=%s cancelled=%s' % (summary.get('fail'), summary.get('cancelled')))
    print('GATE_A=%s %s' % ('PASS' if not reasons else 'FAIL', reasons))
    sys.exit(0 if not reasons else 3)
sys.exit(0)
