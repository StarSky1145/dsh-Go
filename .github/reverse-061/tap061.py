# reverse request 061 result gates for A2/B1/B2 only (temp branch only, never merged). Reads the TAP file only.
# Judges by: process exit code, exact test names, plain ok/not ok/directive per test point, and the summary counts.
# It never compares error text. If the parser itself errors, it prints PARSER_ERROR and exits 4 (stop; raw TAP is
# already in the step log and the artifact).
# usage: tap061.py <A2|B1|B2> <tap stdout file> <exit code>
import re
import sys
import traceback

GEN = ['micro rejects late producer after replace and can subscribe replacement',
       'micro rejects late producer after dispose and can subscribe replacement',
       'micro rejects late producer after replace-invalid and can subscribe replacement',
       'micro queued value cannot flush after replacement before deferred sweep',
       'unrelated registration preserves a current micro producer and last unsubscribe cancels once']
GEN_KEY = 'micro queued value cannot flush after replacement before deferred sweep'
CLOCK = ['R1 capability edges survive wall clock rollback on a live lease',
         'R2 micro sends the next value after elapsed time despite wall rollback',
         'C1 first micro frame is immediate at monotonic zero',
         'C2 ordinary edges, burst, refill and terminal revocation retain their behavior',
         'C3 micro rounds waits up, coalesces, deduplicates and stays quiet after unsubscribe']
B2 = ['micro starts on first subscriber, coalesces latest at 10Hz, immediately disposes last',
      'speechStart clears audio role while voice survives; speech edges are paced, terminals never dropped']


def main():
    step, path, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
    lines = [l[:-1] if l.endswith('\r') else l for l in open(path, encoding='utf-8', errors='replace').read().split('\n')]
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

    def field(block, key):  # display only; block scalars (|-) show their first content line
        for k, b in enumerate(block):
            s = b.strip()
            if s.startswith(key + ':'):
                v = s[len(key) + 1:].strip()
                if v in ('|-', '|', '>-', '>'):
                    return block[k + 1].strip() if k + 1 < len(block) else ''
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
            print('FAIL_DETAIL %s | location=%s | code=%s | failureType=%s | first error line=%s' % (
                p['name'], field(p['block'], 'location'), field(p['block'], 'code'), field(p['block'], 'failureType'), field(p['block'], 'error')))

    by = {}
    for p in top:
        by.setdefault(p['name'], []).append(p)
    reasons = []

    def plain_ok(name):
        hits = by.get(name, [])
        return len(hits) == 1 and hits[0]['status'] == 'ok' and not hits[0]['directive']

    def want_counts(want):
        for k, v in want.items():
            if summary.get(k) != str(v):
                reasons.append('%s=%s (want %s)' % (k, summary.get(k), v))

    if step in ('A2', 'B1'):
        names = GEN if step == 'A2' else CLOCK + GEN
        n = len(names)
        if rc != 0:
            reasons.append('exit %d' % rc)
        want_counts({'tests': n, 'pass': n, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
        if sorted(by) != sorted(names) or len(top) != n:
            reasons.append('test name set differs: got %s' % sorted(by))
        for name in names:
            if not plain_ok(name):
                reasons.append('not a single plain ok: ' + name)
        if not plain_ok(GEN_KEY):
            reasons.append('key case not ok: ' + GEN_KEY)
    elif step == 'B2':
        if rc != 0:
            reasons.append('exit %d' % rc)
        want_counts({'fail': 0, 'cancelled': 0})
        for name in B2:
            print('B2_CASE %s -> %s' % (name, [(h['status'], h['directive']) for h in by.get(name, [])] or 'ZERO_MATCH'))
            if not plain_ok(name):
                reasons.append('named case not a single plain ok: ' + name)
        others = [p for p in top if p['name'] not in B2]
        print('B2_OTHER_TOP_LEVEL_POINTS=%d (as Node printed them; not counted as pass)' % len(others))
        if any(p['status'] == 'not ok' for p in points):
            reasons.append('a not ok point exists')
    else:
        print('unknown step')
        return 2
    print('GATE_%s=%s %s' % (step, 'PASS' if not reasons else 'FAIL', reasons))
    return 0 if not reasons else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        print('PARSER_ERROR (gate script failed; stop and return the raw TAP)')
        traceback.print_exc(file=sys.stdout)
        sys.exit(4)
