# reverse request 062 result gates for A/B1/B2/B3 (temp branch only, never merged). Reads the TAP/stderr files only;
# loads no product code and installs nothing. YAML blocks are read by indentation: "error: |-" is only the block marker,
# the decoded block's FIRST LOGICAL LINE is matched exactly against the oracle text; the whole block (which also holds
# Node's actual/expected diff) is never compared as a whole. actual/expected/stack blocks are kept raw for review.
# Verdicts: PASS exit 0; FAIL exit 3 (a decidable mismatch); PARSER_ERROR exit 4; UNDETERMINED exit 5 (output shape
# unknown or ambiguous). Anything but PASS stops the job.
# usage: tap062.py <A|B1|B2|B3> <tap stdout> <stderr file> <exit code> <tree root>
import json
import re
import sys
import traceback

STREAM = 'runtime/tests/native-stream-clock.test.mjs'
NAMES5 = ['R1 stream survives a forward wall correction before its first heartbeat',
          'R2 an unresponsive stream still expires after wall clock rollback',
          'C1 ordinary unresponsive streams retain the default idle behavior',
          'C2 inbound activity after a correction refreshes idle with a strict boundary',
          'C3 a stream opened at monotonic zero still requires hello at the first heartbeat']
WS2 = ['ws close retires the destroy deadline after a real TCP close',
       'ws logical close retains its deadline until the socket actually closes']
MEDIA = 'media stop aborts pending handler; disconnect revokes lease'
ORACLE = {NAMES5[0]: ('R1 semantic oracle: 25 elapsed seconds must not exhaust the idle budget', 251, 255),
          NAMES5[1]: ('R2 semantic oracle: 75 elapsed seconds without inbound frames must expire the stream', 258, 265)}

PING = {'type': 'ping', 'payload': ''}
IDLE = {'type': 'close', 'code': 1001, 'reason': 'idle'}
HELLO_SENT = [{'mono': 0, 'wallOffset': 0, 'message': {'t': 'hello', 'v': [1]}}]
WELCOME = {'mono': 0, 'wallOffset': 0, 'frame': {'type': 'message', 't': 'welcome', 'v': 1, 'hb': 25}}


def st(d, m, w):
    return {'delta': d, 'mono': m, 'wallOffset': w}


def rv(m, w, f):
    return {'mono': m, 'wallOffset': w, 'frame': f}


R1_STEPS = [st(25000, 25000, 85000)]
R2_STEPS = [st(25000, 25000, -35000), st(25000, 50000, -10000), st(25000, 75000, 15000)]
C1_STEPS = [st(25000, 25000, 25000), st(25000, 50000, 50000), st(25000, 75000, 75000)]
C2_STEPS = [st(15000, 15000, 75000), st(10000, 25000, 85000), st(25000, 50000, 110000), st(25000, 75000, 135000),
            st(25000, 100000, 160000)]
C3_STEPS = [st(25000, 25000, 25000)]
C2_SENT = HELLO_SENT + [{'mono': 15000, 'wallOffset': 75000, 'message': {'t': 'ping', 'at': 1}}]
C2_RECV = [WELCOME, rv(15000, 75000, {'type': 'message', 't': 'pong', 'at': 1}), rv(25000, 85000, PING),
           rv(50000, 110000, PING), rv(75000, 135000, PING), rv(100000, 160000, IDLE)]
C3_RECV = [rv(25000, 25000, {'type': 'close', 'code': 1008, 'reason': 'hello expected'})]
C1_RECV = [WELCOME, rv(25000, 25000, PING), rv(50000, 50000, PING), rv(75000, 75000, IDLE)]
# Exact diagnostics (steps, sent, received, receivedClose; no fixtureFailure). A: R1/R2 are the semantic reds.
DIAG_A = {NAMES5[0]: (R1_STEPS, HELLO_SENT, [WELCOME, rv(25000, 85000, IDLE)], True),
          NAMES5[1]: (R2_STEPS, HELLO_SENT, [WELCOME, rv(25000, -35000, PING), rv(50000, -10000, PING),
                                              rv(75000, 15000, PING)], False)}
DIAG_B1 = {NAMES5[0]: (R1_STEPS, HELLO_SENT, [WELCOME, rv(25000, 85000, PING)], False),
           NAMES5[1]: (R2_STEPS, HELLO_SENT, [WELCOME, rv(25000, -35000, PING), rv(50000, -10000, PING),
                                               rv(75000, 15000, IDLE)], True),
           NAMES5[2]: (C1_STEPS, HELLO_SENT, C1_RECV, True),
           NAMES5[3]: (C2_STEPS, C2_SENT, C2_RECV, True),
           NAMES5[4]: (C3_STEPS, [], C3_RECV, True)}


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
    # Returns {key: {'kind': 'scalar'|'block'|'map', 'value': str|None, 'lines': [decoded content lines], 'raw': [...]}}
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
        return d

    def check_diag(name, d, exp):
        steps, sent, received, rclose = exp
        keys = sorted(d)
        want(keys == sorted(['steps', 'sent', 'received', 'receivedClose']),
             '%s diagnostic keys %s (want steps/sent/received/receivedClose, no fixtureFailure)' % (name, keys))
        want(d.get('steps') == steps, '%s steps %s (want %s)' % (name, d.get('steps'), steps))
        want(d.get('sent') == sent, '%s sent %s (want %s)' % (name, d.get('sent'), sent))
        want(d.get('received') == received, '%s received %s (want %s)' % (name, d.get('received'), received))
        want(d.get('receivedClose') is rclose, '%s receivedClose %r (want %r)' % (name, d.get('receivedClose'), rclose))

    if step in ('A', 'B1'):
        want(len(points) == 5 and len(top) == 5, 'want exactly 5 test points, all top level')
        want(plan == 5, 'plan %s (want 5)' % plan)
        want([p['name'] for p in top] == NAMES5, 'names/order differ: %s' % [p['name'] for p in top])
        want([p['num'] for p in top] == [1, 2, 3, 4, 5], 'numbers %s' % [p['num'] for p in top])
        want([r['name'] for r in regions] == NAMES5 and all(r['point'] for r in regions), 'regions differ')
        diags = {r['name']: region_diag(r) for r in regions}
        if step == 'A':
            want(rc == 1, 'exit %d (want 1)' % rc)
            want(len(stderr_bytes) == 0, 'stderr is %d bytes (want 0: no extra error output)' % len(stderr_bytes))
            counts({'tests': 5, 'pass': 3, 'fail': 2, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                if p['name'] in ORACLE:
                    want(p['status'] == 'not ok' and not p['directive'], '%s is not a plain not ok' % p['name'])
                else:
                    want(plain(p), '%s is not a plain ok' % p['name'])
            for p in top:
                d = diags[p['name']]
                if p['name'] not in ORACLE:
                    want('fixtureFailure' not in d, '%s has fixtureFailure' % p['name'])
                    continue
                oracle, decl, assert_line = ORACLE[p['name']]
                if p['status'] != 'not ok':  # already a decidable FAIL above; no failure YAML to read
                    check_diag(p['name'], d, DIAG_A[p['name']])
                    continue
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
                want(lm is not None and lm.group(1) == tree + '/' + STREAM and int(lm.group(2)) == decl,
                     '%s location %r (want %s/%s:%d:<col>)' % (p['name'], loc, tree, STREAM, decl))
                stack = [s for s in f['stack']['lines'] if s.strip()]
                top_frame = stack[0] if stack else ''
                sm = re.search(r'\(file://(.*):(\d+):(\d+)\)$', top_frame) or re.search(r'at file://(.*):(\d+):(\d+)$', top_frame)
                print('STACK_TOP %s :: %s' % (p['name'], top_frame))
                want(sm is not None and sm.group(1) == tree + '/' + STREAM and int(sm.group(2)) == assert_line,
                     '%s top stack frame %r (want %s:%d)' % (p['name'], top_frame, STREAM, assert_line))
                if sm is not None:
                    print('ASSERT_FRAME %s line=%s col=%s (column 10 usual)' % (p['name'], sm.group(2), sm.group(3)))
                file_frames = [s for s in stack if (tree + '/' + STREAM + ':') in s]
                print('STACK_TEST_FILE_FRAMES %s :: %s' % (p['name'], file_frames))
                for k in ('expected', 'actual', 'stack', 'error'):
                    for rl in f[k]['raw']:
                        print('RAW_%s %s | %s' % (k.upper(), p['name'][:2], rl))
                check_diag(p['name'], d, DIAG_A[p['name']])
        else:
            want(rc == 0, 'exit %d (want 0)' % rc)
            counts({'tests': 5, 'pass': 5, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                want(plain(p), '%s is not a plain ok' % p['name'])
                check_diag(p['name'], diags[p['name']], DIAG_B1[p['name']])
    elif step == 'B2':
        want(rc == 0, 'exit %d (want 0)' % rc)
        counts({'tests': 2, 'pass': 2, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
        want(len(points) == 2 and len(top) == 2, 'want exactly 2 test points, all top level')
        want([p['name'] for p in top] == WS2, 'names/order differ: %s' % [p['name'] for p in top])
        for p in top:
            want(plain(p), '%s is not a plain ok' % p['name'])
        for r in regions:
            if r['comments'] or r['diags']:
                print('NOTE region %r extra lines %r %r' % (r['name'], r['comments'], r['diags']))
    elif step == 'B3':
        want(rc == 0, 'exit %d (want 0)' % rc)
        hits = [p for p in top if p['name'] == MEDIA]
        others = [p for p in top if p['name'] != MEDIA]
        print('B3_CASE %s -> %s' % (MEDIA, [(h['status'], h['directive']) for h in hits] or 'ZERO_MATCH'))
        want(len(hits) == 1 and plain(hits[0]), 'named case is not exactly one plain ok')
        want(len(points) == len(top), 'nested test points present (executed subtests)')
        for p in others:
            want(p['status'] == 'ok' and p['directive'].upper().startswith('SKIP'),
                 'other case actually ran or failed: %s %s %s' % (p['status'], p['directive'], p['name']))
        print('B3_OTHER_TOP_LEVEL_POINTS=%d (all must be SKIP as Node printed them; never counted as pass)' % len(others))
        counts({'pass': 1, 'fail': 0, 'cancelled': 0, 'todo': 0})
        want(summary.get('tests') == str(len(top)), 'tests=%s vs %d points' % (summary.get('tests'), len(top)))
        want(summary.get('skipped') == str(len(others)), 'skipped=%s vs %d other points' % (summary.get('skipped'), len(others)))
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
