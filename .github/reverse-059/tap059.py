# reverse request 059 TAP gates (temp branch only, never merged). Reads the TAP file only; loads no product code.
# usage: tap059.py <A1|A2|B1|B2> <tap stdout file> <exit code>
# Exit 0 only when the run matches the request's expectation for that step (B2: report, exit 0 iff both named cases ok).
import re
import sys

step, path, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
R1 = 'R1 capability edges survive wall clock rollback on a live lease'
R2 = 'R2 micro sends the next value after elapsed time despite wall rollback'
C = ['C1 first micro frame is immediate at monotonic zero',
     'C2 ordinary edges, burst, refill and terminal revocation retain their behavior',
     'C3 micro rounds waits up, coalesces, deduplicates and stays quiet after unsubscribe']
ORACLE = {R1: 'R1 semantic oracle: a wall correction must not consume the elapsed edge budget',
          R2: 'R2 semantic oracle: elapsed 100 ms must not acquire a 5000 ms wall-clock wait'}
GEN_KEY = 'micro queued value cannot flush after replacement before deferred sweep'
B2 = ['micro starts on first subscriber, coalesces latest at 10Hz, immediately disposes last',
      'speechStart clears audio role while voice survives; speech edges are paced, terminals never dropped']

lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
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
    block, j = [], i + 1
    if j < len(lines) and lines[j].strip() == '---':
        while j < len(lines):
            block.append(lines[j])
            if lines[j].strip() == '...':
                break
            j += 1
    points.append({'indent': len(indent), 'status': status, 'name': name.replace('\\#', '#'), 'directive': directive, 'block': block})

summary = {}
for line in lines:
    m = re.match(r'^# (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms) (\S+)$', line)
    if m:
        summary[m.group(1)] = m.group(2)


def field(block, key):
    for b in block:
        s = b.strip()
        if s.startswith(key + ':'):
            v = s[len(key) + 1:].strip()
            if len(v) >= 2 and v[0] == v[-1] == "'":
                v = v[1:-1].replace("''", "'")
            return v
    return None


top = [p for p in points if p['indent'] == 0]
print('STEP=%s EXIT=%d' % (step, rc))
print('SUMMARY ' + ' '.join('%s=%s' % (k, summary.get(k, '?')) for k in ['tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo', 'duration_ms']))
print('TEST_POINTS total=%d top_level=%d' % (len(points), len(top)))
for p in points:
    print('POINT indent=%d %s%s - %s' % (p['indent'], p['status'], (' # ' + p['directive']) if p['directive'] else '', p['name']))
for p in points:
    if p['status'] == 'not ok':
        print('FAIL_DETAIL %s | error=%s | code=%s | operator=%s | failureType=%s | location=%s' % (
            p['name'], field(p['block'], 'error'), field(p['block'], 'code'), field(p['block'], 'operator'),
            field(p['block'], 'failureType'), field(p['block'], 'location')))
        for b in p['block']:
            print('    | ' + b)

by = {}
for p in top:
    by.setdefault(p['name'], []).append(p)
reasons = []


def ok_point(name):
    hits = by.get(name, [])
    return len(hits) == 1 and hits[0]['status'] == 'ok' and not hits[0]['directive']


def counts(tests, passed, failed):
    want = {'tests': str(tests), 'pass': str(passed), 'fail': str(failed), 'cancelled': '0', 'skipped': '0', 'todo': '0'}
    for k, v in want.items():
        if summary.get(k) != v:
            reasons.append('%s=%s (want %s)' % (k, summary.get(k), v))


if step == 'A1':
    if rc == 0:
        reasons.append('exit 0')
    counts(5, 3, 2)
    if sorted(by) != sorted([R1, R2] + C) or len(top) != 5:
        reasons.append('test set differs: %s' % sorted(by))
    for name in (R1, R2):
        hits = by.get(name, [])
        if len(hits) != 1 or hits[0]['status'] != 'not ok' or hits[0]['directive']:
            reasons.append('%s not a single not ok' % name); continue
        b = hits[0]['block']
        if field(b, 'error') != ORACLE[name]:
            reasons.append('%s error=%r is not its semantic oracle' % (name, field(b, 'error')))
        if field(b, 'code') != 'ERR_ASSERTION' or field(b, 'failureType') != 'testCodeFailure':
            reasons.append('%s code/failureType %s/%s' % (name, field(b, 'code'), field(b, 'failureType')))
        print('ORACLE_CHECK %s operator=%s error_matches_oracle=%s' % (name, field(b, 'operator'), field(b, 'error') == ORACLE[name]))
    for name in C:
        if not ok_point(name):
            reasons.append('%s not ok/skip/missing' % name)
elif step == 'A2':
    if rc != 0:
        reasons.append('exit %d' % rc)
    counts(5, 5, 0)
    if not ok_point(GEN_KEY):
        reasons.append('key case not ok: ' + GEN_KEY)
    if any(p['status'] != 'ok' or p['directive'] for p in top) or len(top) != 5:
        reasons.append('not exactly 5 plain ok points')
elif step == 'B1':
    if rc != 0:
        reasons.append('exit %d' % rc)
    counts(10, 10, 0)
    for name in [R1, R2] + C + [GEN_KEY]:
        if not ok_point(name):
            reasons.append('not ok/missing: ' + name)
    if any(p['status'] != 'ok' or p['directive'] for p in top) or len(top) != 10:
        reasons.append('not exactly 10 plain ok points')
elif step == 'B2':
    if rc != 0:
        reasons.append('exit %d' % rc)
    for name in B2:
        print('B2_CASE %s -> %s' % (name, [(h['status'], h['directive']) for h in by.get(name, [])] or 'ZERO_MATCH'))
        if not ok_point(name):
            reasons.append('named case not a single plain ok: ' + name)
    others = [p for p in top if p['name'] not in B2]
    print('B2_OTHER_TOP_LEVEL_POINTS=%d (reported as Node printed them; not counted as pass)' % len(others))
else:
    print('unknown step'); sys.exit(2)

print('GATE_%s=%s %s' % (step, 'PASS' if not reasons else 'FAIL', reasons))
sys.exit(0 if not reasons else 3)
