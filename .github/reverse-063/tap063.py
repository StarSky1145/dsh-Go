# reverse request 063 result gates for A1/B1/B2 (temp branch only, never merged). Reads the TAP/stderr files only;
# loads no product code and installs nothing. YAML blocks are read by indentation: "error: |-" is only the block marker,
# the decoded block's FIRST LOGICAL LINE is matched exactly against the oracle text; the whole block (which also holds
# Node's actual/expected diff) is never compared as a whole. actual/expected/stack blocks are kept raw for review.
# Verdicts: PASS exit 0; FAIL exit 3 (a decidable mismatch); PARSER_ERROR exit 4; UNDETERMINED exit 5 (output shape
# unknown or ambiguous). Anything but PASS stops the job.
# usage: tap063.py <A1|B1|B2> <tap stdout> <stderr file> <exit code> <tree root>
import json
import re
import sys
import traceback

FEED = 'runtime/tests/native-feed-clock.test.mjs'
NAMES5 = ['R1 ordinary feed publishes after elapsed time despite wall rollback',
          'R2 ordinary feed retains its elapsed window after a forward wall correction',
          'C1 ordinary feed keeps zero, asynchronous first, latest value and armed timer distinct',
          'C2 ordinary feed rounds a positive fractional request up without a private scheduler',
          'C3 ordinary feed duplicate flush consumes its window without changing the revision']
IDLE6 = ['idle feed updates data and revision without serializing an unsent patch',
         'subscribed feed preserves patch, base, payload and serialization',
         'first-data waiters resolve before idle exit and current revision subscribes with sync',
         'subscription set at flush time determines whether a patch has a receiver',
         'idle null transitions and burst coalescing preserve latest state',
         'idle optimization retains linger cancellation and late callbacks stay stopped']
ORACLE = {NAMES5[0]: ('R1 semantic oracle: a wall rollback must not stall an elapsed ordinary feed window', 69, 76),
          NAMES5[1]: ('R2 semantic oracle: a wall correction must not release an ordinary feed update before its elapsed window', 82, 88)}
DIAG_KEYS = ['case', 'sends', 'steps', 'timeoutRequests']
REV1 = re.compile(r'^([0-9a-f]{6})\.1$')


def em(m, w, n):
    return {'op': 'emit', 'mono': m, 'wallOffset': w, 'value': {'n': n}}


def adv(d, m, w):
    return {'op': 'advance', 'delta': d, 'mono': m, 'wallOffset': w}


A_STEPS = {NAMES5[0]: [em(0, 0, 0), adv(0, 0, 0), adv(300, 300, 300), adv(700, 1000, -59000), em(1000, -59000, 1),
                       adv(0, 1000, -59000)],
           NAMES5[1]: [em(0, 0, 0), adv(0, 0, 0), adv(100, 100, 60100), em(100, 60100, 1), adv(0, 100, 60100)]}
A_REQUESTS = {NAMES5[0]: [0, 59250], NAMES5[1]: [0, 0]}


class Undetermined(Exception):
    pass


def unquote(v):
    # Node's TAP reporter prints scalars with util.inspect: 'x' (or "x" when x holds a single quote), numbers bare.
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '\'"':
        inner = v[1:-1]
        out, i = [], 0
        while i < len(inner):
            c = inner[i]
            if c == '\\' and i + 1 < len(inner) and inner[i + 1] in '\\\'"':
                out.append(inner[i + 1])
                i += 2
                continue
            if c == '\\':
                raise Undetermined('unsupported escape in scalar %r' % v)
            out.append(c)
            i += 1
        return ''.join(out)
    return v


def parse_yaml_block(block, base):
    # block: lines strictly between '---' and '...' of one test point; keys sit at indent base+2.
    fields, order, i = {}, [], 0
    kind_re = re.compile(r'^ {%d}([A-Za-z_][A-Za-z0-9_]*):(?: (.*))?$' % (base + 2))
    while i < len(block):
        line = block[i]
        m = kind_re.match(line)
        if not m:
            raise Undetermined('unexpected YAML line %r' % line)
        key, val = m.group(1), m.group(2)
        if key in fields:
            raise Undetermined('duplicate YAML key %s' % key)
        raw = [line]
        j = i + 1
        cont = []
        while j < len(block):
            l2 = block[j]
            ind = len(l2) - len(l2.lstrip(' '))
            if l2.strip() == '' or ind >= base + 4:
                cont.append(l2)
                raw.append(l2)
                j += 1
            else:
                break
        if val is None or val == '':
            if not cont:
                raise Undetermined('empty nested map %s' % key)
            kind, value, lines = 'map', None, [c[base + 4:] if len(c) >= base + 4 else '' for c in cont]
        elif val == '|-':
            if not cont:
                raise Undetermined('empty block scalar %s' % key)
            for c in cont:
                if c.strip() and not c.startswith(' ' * (base + 4)):
                    raise Undetermined('block %s content under-indented' % key)
            kind, value, lines = 'block', None, [c[base + 4:] if len(c) >= base + 4 else '' for c in cont]
        elif val in ('|', '>', '>-', '|+', '>+'):
            raise Undetermined('unsupported block style %s for %s' % (val, key))
        else:
            if cont:
                raise Undetermined('scalar %s followed by indented lines' % key)
            kind, value, lines = 'scalar', unquote(val), [unquote(val)]
        fields[key] = {'kind': kind, 'value': value, 'lines': lines, 'raw': raw}
        order.append(key)
        i = j
    return fields, order


def first_logical_line(f):
    if f['kind'] == 'scalar':
        return f['value']
    if f['kind'] == 'block':
        return f['lines'][0]
    raise Undetermined('error is a nested map')


def parse_tap(text):
    lines = [l[:-1] if l.endswith('\r') else l for l in text.split('\n')]
    if not lines or lines[0] != 'TAP version 13':
        raise Undetermined('first line is not "TAP version 13": %r' % (lines[0] if lines else None))
    point = re.compile(r'^( *)(not ok|ok) (\d+) - (.*)$')
    points, regions, summary, plan = [], [], {}, None
    cur = None  # current top-level region
    i = 1
    while i < len(lines):
        line = lines[i]
        m = point.match(line)
        if m:
            indent, status, num, rest = m.groups()
            name, directive = rest, ''
            dm = re.search(r' # (SKIP|TODO)\b.*$', rest, re.I)
            if dm:
                name, directive = rest[:dm.start()], dm.group(0)[3:]
            name = name.replace('\\#', '#').replace('\\\\', '\\')
            j, block = i + 1, None
            if j < len(lines) and lines[j] == ' ' * len(indent) + '  ---':
                block, j = [], j + 1
                while j < len(lines) and lines[j] != ' ' * len(indent) + '  ...':
                    block.append(lines[j])
                    j += 1
                if j >= len(lines):
                    raise Undetermined('unterminated YAML block for %s' % name)
                j += 1
            p = {'indent': len(indent), 'status': status, 'num': int(num), 'name': name, 'directive': directive,
                 'block': block, 'line': i + 1}
            if p['indent'] == 0:
                if cur is None or cur['point'] is not None or cur['name'] != name:
                    raise Undetermined('top-level point %r without its own "# Subtest:" header' % name)
                cur['point'] = p
            points.append(p)
            i = j
            continue
        if line.startswith('# Subtest: '):
            cur = {'name': line[len('# Subtest: '):].replace('\\#', '#').replace('\\\\', '\\'), 'point': None,
                   'diags': [], 'comments': [], 'line': i + 1}
            regions.append(cur)
        elif re.match(r'^1\.\.\d+$', line):
            if plan is not None:
                raise Undetermined('two top-level plans')
            plan = int(line[3:])
            cur = None
        elif line.startswith('# '):
            sm = re.match(r'^# (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms) (\S+)$', line)
            if cur is None and plan is not None and sm:
                if sm.group(1) in summary:
                    raise Undetermined('duplicate summary %s' % sm.group(1))
                summary[sm.group(1)] = sm.group(2)
            elif cur is not None and line.startswith('# {'):
                cur['diags'].append((i + 1, line[2:]))
            elif cur is not None:
                cur['comments'].append((i + 1, line))
            else:
                raise Undetermined('comment outside any test region: %r' % line)
        elif line.startswith(' '):
            if cur is None:
                raise Undetermined('indented line outside a test region: %r' % line)
            cur['comments'].append((i + 1, line))  # nested subtest output; judged via points
        elif line == '' and i == len(lines) - 1:
            pass
        else:
            raise Undetermined('unexpected TAP line %d: %r' % (i + 1, line))
        i += 1
    return points, regions, summary, plan


def main():
    step, tap_path, err_path, rc, tree = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5].rstrip('/')
    text = open(tap_path, 'rb').read().decode('utf-8')
    stderr_bytes = open(err_path, 'rb').read()
    points, regions, summary, plan = parse_tap(text)
    top = [p for p in points if p['indent'] == 0]
    print('STEP=%s EXIT=%d STDERR_BYTES=%d PLAN=%s' % (step, rc, len(stderr_bytes), plan))
    print('SUMMARY ' + ' '.join('%s=%s' % (k, summary.get(k, '?')) for k in
                                ['tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo', 'duration_ms']))
    print('TEST_POINTS total=%d top_level=%d nested=%d' % (len(points), len(top), len(points) - len(top)))
    for p in points:
        print('POINT line=%d indent=%d %s %d%s - %s' % (p['line'], p['indent'], p['status'], p['num'],
              (' # ' + p['directive']) if p['directive'] else '', p['name']))
    reasons = []

    def want(cond, why):
        if not cond:
            reasons.append(why)

    def counts(w):
        for k, v in w.items():
            want(summary.get(k) == str(v), '%s=%s (want %s)' % (k, summary.get(k), v))

    def plain(p):
        return p['status'] == 'ok' and not p['directive']

    def region_diag(r):
        if r['comments']:
            raise Undetermined('unexpected extra comment/output lines in region %r: %r' % (r['name'], r['comments']))
        if len(r['diags']) != 1:
            raise Undetermined('region %r has %d JSON diagnostics (want exactly 1)' % (r['name'], len(r['diags'])))
        ln, js = r['diags'][0]
        try:
            d = json.loads(js)
        except ValueError as e:
            raise Undetermined('diagnostic of %r is not JSON: %s' % (r['name'], e))
        if not isinstance(d, dict):
            raise Undetermined('diagnostic of %r is not an object' % r['name'])
        print('DIAG line=%d test=%s json=%s' % (ln, r['name'], json.dumps(d, separators=(',', ':'))))
        if sorted(d) != DIAG_KEYS:
            raise Undetermined('diagnostic of %r has keys %s (want %s)' % (r['name'], sorted(d), DIAG_KEYS))
        if d['case'] != r['name']:
            raise Undetermined('diagnostic case %r is not the region name %r' % (d['case'], r['name']))
        return d

    def check_sends_a(name, sends):
        # R1: exactly the first data. R2: the first data, then one patch on the same epoch.
        if not isinstance(sends, list) or not sends:
            reasons.append('%s sends %r' % (name, sends))
            return
        s0 = sends[0]
        m0 = s0.get('message') if isinstance(s0, dict) else None
        ok0 = (isinstance(s0, dict) and sorted(s0) == ['message', 'mono', 'wallOffset'] and s0['mono'] == 0
               and s0['wallOffset'] == 0 and isinstance(m0, dict) and sorted(m0) == ['data', 'rev', 'sub', 't']
               and m0['t'] == 'data' and m0['sub'] == 'clock' and m0['data'] == {'n': 0}
               and isinstance(m0['rev'], str) and REV1.match(m0['rev']) is not None)
        want(ok0, '%s first send %r (want mono0/wallOffset0 data sub=clock data={n:0} rev=<6 hex>.1)' % (name, s0))
        if name == NAMES5[0]:
            want(len(sends) == 1, '%s has %d sends (want exactly 1)' % (name, len(sends)))
            return
        want(len(sends) == 2, '%s has %d sends (want exactly 2)' % (name, len(sends)))
        if len(sends) < 2 or not ok0:
            return
        s1 = sends[1]
        m1 = s1.get('message') if isinstance(s1, dict) else None
        epoch = REV1.match(m0['rev']).group(1)
        ok1 = (isinstance(s1, dict) and sorted(s1) == ['message', 'mono', 'wallOffset'] and s1['mono'] == 100
               and s1['wallOffset'] == 60100 and isinstance(m1, dict)
               and sorted(m1) == ['base', 'merge', 'rev', 'sub', 't'] and m1['t'] == 'patch' and m1['sub'] == 'clock'
               and m1['merge'] == {'n': 1} and m1['base'] == m0['rev'] and m1['rev'] == epoch + '.2')
        want(ok1, '%s second send %r (want mono100/wallOffset60100 patch sub=clock merge={n:1} base=%s rev=%s.2)' % (
            name, s1, m0['rev'], epoch))

    if step in ('A1', 'B1'):
        want(len(points) == 5 and len(top) == 5, 'want exactly 5 test points, all top level')
        want(plan == 5, 'plan %s (want 5)' % plan)
        want([p['name'] for p in top] == NAMES5, 'names/order differ: %s' % [p['name'] for p in top])
        want([p['num'] for p in top] == [1, 2, 3, 4, 5], 'numbers %s' % [p['num'] for p in top])
        want([r['name'] for r in regions] == NAMES5 and all(r['point'] for r in regions), 'regions differ')
        diags = {r['name']: region_diag(r) for r in regions}
        c2 = diags.get(NAMES5[3])
        print('C2_TIMEOUT_REQUESTS %r' % ((c2 or {}).get('timeoutRequests'),))
        if step == 'A1':
            want(c2 is not None and c2['timeoutRequests'] == [0, 151],
                 'C2 timeoutRequests %r (want [0, 151])' % (c2 or {}).get('timeoutRequests'))
            want(rc == 1, 'exit %d (want 1)' % rc)
            want(len(stderr_bytes) == 0, 'stderr is %d bytes (want 0: no extra error output)' % len(stderr_bytes))
            counts({'tests': 5, 'pass': 3, 'fail': 2, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                if p['name'] in ORACLE:
                    want(p['status'] == 'not ok' and not p['directive'], '%s is not a plain not ok' % p['name'])
                else:
                    want(plain(p), '%s is not a plain ok' % p['name'])
            for p in top:
                if p['name'] not in ORACLE:
                    continue
                d = diags[p['name']]
                want(d['steps'] == A_STEPS[p['name']], '%s steps %r (want %r)' % (p['name'], d['steps'], A_STEPS[p['name']]))
                want(d['timeoutRequests'] == A_REQUESTS[p['name']],
                     '%s timeoutRequests %r (want %r)' % (p['name'], d['timeoutRequests'], A_REQUESTS[p['name']]))
                check_sends_a(p['name'], d['sends'])
                if p['status'] != 'not ok':  # already a decidable FAIL above; no failure YAML to read
                    continue
                oracle, decl, assert_line = ORACLE[p['name']]
                if p['block'] is None:
                    raise Undetermined('%s has no YAML block' % p['name'])
                f, order = parse_yaml_block(p['block'], 0)
                print('YAML_KEYS %s %s' % (p['name'], order))
                for k in ('type', 'location', 'failureType', 'error', 'code', 'name', 'operator', 'stack', 'expected', 'actual'):
                    if k not in f:
                        raise Undetermined('%s YAML lacks %s' % (p['name'], k))
                for k in ('type', 'location', 'failureType', 'code', 'name', 'operator'):
                    if f[k]['kind'] != 'scalar':
                        raise Undetermined('%s %s is not a scalar' % (p['name'], k))
                if f['stack']['kind'] != 'block' or f['error']['kind'] not in ('block', 'scalar'):
                    raise Undetermined('%s stack/error shape' % p['name'])
                fl = first_logical_line(f['error'])
                print('ERROR_FIRST_LOGICAL_LINE %s :: %s' % (p['name'], fl))
                want(fl == oracle, '%s first error line %r (want %r)' % (p['name'], fl, oracle))
                want(f['type']['value'] == 'test', '%s type %r' % (p['name'], f['type']['value']))
                want(f['failureType']['value'] == 'testCodeFailure', '%s failureType %r' % (p['name'], f['failureType']['value']))
                want(f['code']['value'] == 'ERR_ASSERTION', '%s code %r' % (p['name'], f['code']['value']))
                want(f['name']['value'] == 'AssertionError', '%s name %r' % (p['name'], f['name']['value']))
                want(f['operator']['value'] == 'deepStrictEqual', '%s operator %r' % (p['name'], f['operator']['value']))
                loc = f['location']['value']
                lm = re.match(r'^(.*):(\d+):(\d+)$', loc)
                print('LOCATION %s :: %s' % (p['name'], loc))
                want(lm is not None and lm.group(1) == tree + '/' + FEED and int(lm.group(2)) == decl,
                     '%s location %r (want %s/%s:%d:<col>)' % (p['name'], loc, tree, FEED, decl))
                stack = [s for s in f['stack']['lines'] if s.strip()]
                top_frame = stack[0] if stack else ''
                sm = re.search(r'\(file://(.*):(\d+):(\d+)\)$', top_frame) or re.search(r'at file://(.*):(\d+):(\d+)$', top_frame)
                print('STACK_TOP %s :: %s' % (p['name'], top_frame))
                want(sm is not None and sm.group(1) == tree + '/' + FEED and int(sm.group(2)) == assert_line,
                     '%s top stack frame %r (want %s:%d)' % (p['name'], top_frame, FEED, assert_line))
                if sm is not None:
                    print('ASSERT_FRAME %s line=%s col=%s (column 10 usual)' % (p['name'], sm.group(2), sm.group(3)))
                file_frames = [s for s in stack if (tree + '/' + FEED + ':') in s]
                print('STACK_TEST_FILE_FRAMES %s :: %s' % (p['name'], file_frames))
                for k in ('expected', 'actual', 'stack', 'error'):
                    for rl in f[k]['raw']:
                        print('RAW_%s %s | %s' % (k.upper(), p['name'][:2], rl))
        else:
            want(rc == 0, 'exit %d (want 0)' % rc)
            counts({'tests': 5, 'pass': 5, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                want(plain(p), '%s is not a plain ok' % p['name'])
    elif step == 'B2':
        want(rc == 0, 'exit %d (want 0)' % rc)
        counts({'tests': 6, 'pass': 6, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
        want(len(points) == 6 and len(top) == 6, 'want exactly 6 test points, all top level')
        want([p['name'] for p in top] == IDLE6, 'names/order differ: %s' % [p['name'] for p in top])
        for p in top:
            want(plain(p), '%s is not a plain ok' % p['name'])
        for r in regions:
            if r['comments'] or r['diags']:
                print('NOTE region %r extra lines %r %r' % (r['name'], r['comments'], r['diags']))
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
    except Undetermined as e:
        print('GATE_%s=UNDETERMINED (%s) -> stop; raw TAP is in the step log and the artifact' % (sys.argv[1], e))
        sys.exit(5)
    except BaseException:
        print('PARSER_ERROR (gate script failed; stop and return the raw TAP)')
        traceback.print_exc(file=sys.stdout)
        sys.exit(4)
