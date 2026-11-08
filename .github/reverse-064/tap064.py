# reverse request 064 result gates for A/B1/B2/B3 (temp branch only, never merged). Reads the TAP/stderr files only;
# loads no product code and installs nothing. YAML blocks are read by indentation: "error: |-" is only the block marker,
# the decoded block's FIRST LOGICAL LINE is matched exactly against the oracle text; the whole block (which also holds
# Node's actual/expected diff) is never compared as a whole and actual/expected are not parsed as YAML objects: they are
# kept raw for independent review. The asserted values are bound through the case's own "# INVOKE_CLOCK_TRACE {...}"
# JSON (TAP-escaped by Node's reporter: \\ \# \b \f \t \n \r \v are decoded strictly, any other escape stops).
# Verdicts: PASS exit 0; FAIL exit 3 (a decidable mismatch); PARSER_ERROR exit 4; UNDETERMINED exit 5 (output shape
# unknown or ambiguous). Anything but PASS stops the job.
# usage: tap064.py <A|B1|B2|B3> <tap stdout> <stderr file> <exit code> <tree root>
import json
import re
import sys
import traceback

INVOKE = 'runtime/tests/native-invoke-clock.test.mjs'
NAMES4 = ['R1 invoke accepts a fresh copy after elapsed time despite wall rollback',
          'R2 invoke does not refill a spent burst on a wall clock jump',
          'C1 invoke starts at monotonic zero and retains burst and elapsed refill',
          'C2 invoke keeps concurrency, release and package buckets independent']
UNIT1 = ['core: invoke token bucket and concurrency']
GEN2 = ['normal direct result and unrelated panel replacement preserve the action',
        'current handler rejection keeps existing plugin-error contract']
ORACLE = {NAMES4[0]: ('R1 semantic oracle: rollback must not reject the next lawful copy', 179, 184),
          NAMES4[1]: ('R2 semantic oracle: a wall jump must not replenish the relative budget', 187, 194)}
TRACE_PREFIX = 'INVOKE_CLOCK_TRACE '
TRACE_KEYS = ['fixtureFailures', 'requests', 'warnings']
OK_KEYS = ['body', 'complete', 'entered', 'headers', 'mono', 'pkg', 'rawBody', 'retryAfter', 'status', 'wallOffset']
PA, PB = 'invoke-clock-a', 'invoke-clock-b'
COPY = {'v': 1, 'effects': [{'type': 'copy', 'text': 'ok'}], 'issues': []}
LIMITED = {'v': 1, 'error': {'code': 'rate-limited', 'message': 'too many invokes'}}


def ok(pkg, mono, wall, entered):
    return (pkg, mono, wall, 200, COPY, None, entered)


def lim(pkg, mono, wall, ra, entered):
    return (pkg, mono, wall, 429, LIMITED, ra, entered)


# Expected request records in response-completion order (mono/wallOffset = launch snapshot, entered = the package's
# cumulative handler entries when that response completed). R1/R2 differ between A and B only in the last record.
SEQ = {
    'A': {NAMES4[0]: [ok(PA, 0, 0, 1), lim(PA, 1000, -59000, '58', 1)],
          NAMES4[1]: [ok(PA, 0, 0, i) for i in range(1, 9)] + [ok(PA, 100, 60100, 9)]},
    'B1': {NAMES4[0]: [ok(PA, 0, 0, 1), ok(PA, 1000, -59000, 2)],
           NAMES4[1]: [ok(PA, 0, 0, i) for i in range(1, 9)] + [lim(PA, 100, 60100, '1', 8)]},
}
C_SEQ = {NAMES4[2]: [ok(PA, 0, 0, i) for i in range(1, 9)] + [lim(PA, 0, 0, '1', 8), ok(PA, 250, 250, 9),
                                                               lim(PA, 250, 250, '1', 9)],
         NAMES4[3]: [lim(PA, 0, 0, '1', 4), ok(PB, 0, 0, 1), ok(PA, 0, 0, 4)] + [ok(PA, 0, 0, i) for i in range(5, 9)]
         + [lim(PA, 0, 0, '1', 8), ok(PB, 0, 0, 2)] + [ok(PA, 0, 0, 8)] * 3}
for _s in SEQ.values():
    _s.update(C_SEQ)


class Undetermined(Exception):
    pass


def teq(a, b):
    # Type-strict deep equality (Python would otherwise treat True == 1 and 1 == 1.0).
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return sorted(a) == sorted(b) and all(teq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(teq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def tap_unescape(s):
    # Exact inverse of Node's TAP reporter escaping (backslash first, then '#', then control characters).
    m = {'\\': '\\', '#': '#', 'b': '\b', 'f': '\f', 't': '\t', 'n': '\n', 'r': '\r', 'v': '\v'}
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            if i + 1 >= len(s) or s[i + 1] not in m:
                raise Undetermined('unknown TAP escape at %d in diagnostic: %r' % (i, s[i:i + 2]))
            out.append(m[s[i + 1]])
            i += 2
            continue
        if c == '#':
            raise Undetermined('unescaped "#" in a TAP-escaped diagnostic at %d' % i)
        out.append(c)
        i += 1
    return ''.join(out)


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
            name = tap_unescape(name)
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
            cur = {'name': tap_unescape(line[len('# Subtest: '):]), 'point': None, 'diags': [], 'comments': [],
                   'line': i + 1}
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
            elif cur is not None and line.startswith('# ' + TRACE_PREFIX):
                if cur['point'] is None:
                    raise Undetermined('trace line %d before the test point of %r' % (i + 1, cur['name']))
                cur['diags'].append((i + 1, line[2 + len(TRACE_PREFIX):]))
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

    def region_trace(r):
        if r['comments']:
            raise Undetermined('unexpected extra comment/output lines in region %r: %r' % (r['name'], r['comments']))
        if len(r['diags']) != 1:
            raise Undetermined('region %r has %d INVOKE_CLOCK_TRACE lines (want exactly 1)' % (r['name'], len(r['diags'])))
        ln, esc = r['diags'][0]
        js = tap_unescape(esc)
        try:
            d = json.loads(js)
        except ValueError as e:
            raise Undetermined('INVOKE_CLOCK_TRACE of %r is not JSON: %s' % (r['name'], e))
        if not isinstance(d, dict):
            raise Undetermined('INVOKE_CLOCK_TRACE of %r is not an object' % r['name'])
        print('TRACE line=%d test=%s escaped_chars=%d decoded_chars=%d json=%s' % (
            ln, r['name'], len(esc), len(js), json.dumps(d, separators=(',', ':'), ensure_ascii=False)))
        if sorted(d) != TRACE_KEYS:
            raise Undetermined('INVOKE_CLOCK_TRACE of %r has keys %s (want %s)' % (r['name'], sorted(d), TRACE_KEYS))
        if not isinstance(d['requests'], list) or not isinstance(d['warnings'], list) \
                or not isinstance(d['fixtureFailures'], list):
            raise Undetermined('INVOKE_CLOCK_TRACE of %r: requests/warnings/fixtureFailures are not all arrays' % r['name'])
        print('TRACE_SUMMARY test=%s requests=%d warnings=%d fixtureFailures=%d' % (
            r['name'], len(d['requests']), len(d['warnings']), len(d['fixtureFailures'])))
        for w in d['warnings']:
            print('TRACE_WARNING test=%s %s' % (r['name'], json.dumps(w, ensure_ascii=False)))
        for ff in d['fixtureFailures']:
            print('TRACE_FIXTURE_FAILURE test=%s %s' % (r['name'], json.dumps(ff, ensure_ascii=False)))
        want(d['fixtureFailures'] == [], '%s fixtureFailures is not [] (%d entries)' % (r['name'], len(d['fixtureFailures'])))
        return d

    def check_requests(name, reqs, seq):
        want(len(reqs) == len(seq), '%s has %d request records (want %d)' % (name, len(reqs), len(seq)))
        for k, e in enumerate(reqs):
            tag = '%s request %d' % (name, k + 1)
            if not isinstance(e, dict):
                reasons.append('%s is not an object: %r' % (tag, e))
                continue
            if 'error' in e or sorted(e) != OK_KEYS:
                reasons.append('%s is not a completed response record: keys=%s error=%r' % (tag, sorted(e), e.get('error')))
                continue
            want(e['complete'] is True, '%s complete=%r (want true)' % (tag, e['complete']))
            body_ok = False
            try:
                body_ok = isinstance(e['rawBody'], str) and teq(json.loads(e['rawBody']), e['body'])
            except ValueError:
                pass
            want(body_ok, '%s JSON.parse(rawBody) does not equal body' % tag)
            h = e['headers']
            if not isinstance(h, dict):
                reasons.append('%s headers is not an object' % tag)
            else:
                ra = e['retryAfter']
                hdr_ok = ('retry-after' not in h) if ra is None else teq(h.get('retry-after'), ra)
                want(hdr_ok, '%s Retry-After header %r does not match retryAfter %r' % (tag, h.get('retry-after'), ra))
            if k < len(seq):
                pkg, mono, wall, status, body, ra, entered = seq[k]
                got = (e['pkg'], e['mono'], e['wallOffset'], e['status'], e['body'], e['retryAfter'], e['entered'])
                same = all(teq(x, y) for x, y in zip(got, seq[k]))
                print('REQ %s #%d pkg=%s mono=%s wallOffset=%s status=%s retryAfter=%s entered=%s %s' % (
                    name[:2], k + 1, e['pkg'], e['mono'], e['wallOffset'], e['status'], json.dumps(e['retryAfter']),
                    e['entered'], 'MATCH' if same else 'MISMATCH want pkg=%s mono=%s wallOffset=%s status=%s '
                    'retryAfter=%s entered=%s body=%s' % (pkg, mono, wall, status, json.dumps(ra), entered,
                                                          json.dumps(body, separators=(',', ':')))))
                want(same, '%s %r (want %r)' % (tag, got, seq[k]))

    if step in ('A', 'B1'):
        want(len(points) == 4 and len(top) == 4, 'want exactly 4 test points, all top level')
        want(plan == 4, 'plan %s (want 4)' % plan)
        want([p['name'] for p in top] == NAMES4, 'names/order differ: %s' % [p['name'] for p in top])
        want([p['num'] for p in top] == [1, 2, 3, 4], 'numbers %s' % [p['num'] for p in top])
        want([r['name'] for r in regions] == NAMES4 and all(r['point'] for r in regions), 'regions differ')
        traces = {r['name']: region_trace(r) for r in regions}
        for name in NAMES4:
            if name in traces:
                check_requests(name, traces[name]['requests'], SEQ[step][name])
        if step == 'A':
            want(rc == 1, 'exit %d (want 1)' % rc)
            want(len(stderr_bytes) == 0, 'stderr is %d bytes (want 0: no extra error output)' % len(stderr_bytes))
            counts({'tests': 4, 'suites': 0, 'pass': 2, 'fail': 2, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                if p['name'] in ORACLE:
                    want(p['status'] == 'not ok' and not p['directive'], '%s is not a plain not ok' % p['name'])
                else:
                    want(plain(p), '%s is not a plain ok' % p['name'])
            for p in top:
                if p['name'] not in ORACLE or p['status'] != 'not ok':
                    continue  # a non-red R case is already a decidable FAIL above; it has no failure YAML to read
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
                want(lm is not None and lm.group(1) == tree + '/' + INVOKE and int(lm.group(2)) == decl,
                     '%s location %r (want %s/%s:%d:<col>)' % (p['name'], loc, tree, INVOKE, decl))
                stack = [s for s in f['stack']['lines'] if s.strip()]
                top_frame = stack[0] if stack else ''
                sm = re.search(r'\(file://(.*):(\d+):(\d+)\)$', top_frame) or re.search(r'at file://(.*):(\d+):(\d+)$', top_frame)
                print('STACK_TOP %s :: %s' % (p['name'], top_frame))
                want(sm is not None and sm.group(1) == tree + '/' + INVOKE and int(sm.group(2)) == assert_line,
                     '%s top stack frame %r (want %s:%d)' % (p['name'], top_frame, INVOKE, assert_line))
                if sm is not None:
                    print('ASSERT_FRAME %s line=%s col=%s (column 10 usual)' % (p['name'], sm.group(2), sm.group(3)))
                file_frames = [s for s in stack if (tree + '/' + INVOKE + ':') in s]
                print('STACK_TEST_FILE_FRAMES %s :: %s' % (p['name'], file_frames))
                for k in ('expected', 'actual', 'stack', 'error'):
                    for rl in f[k]['raw']:
                        print('RAW_%s %s | %s' % (k.upper(), p['name'][:2], rl))
        else:
            want(rc == 0, 'exit %d (want 0)' % rc)
            counts({'tests': 4, 'suites': 0, 'pass': 4, 'fail': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0})
            for p in top:
                want(plain(p), '%s is not a plain ok' % p['name'])
    elif step in ('B2', 'B3'):
        targets = UNIT1 if step == 'B2' else GEN2
        want(rc == 0, 'exit %d (want 0)' % rc)
        want(len(points) == len(top), 'nested test points present (executed subtests)')
        for t in targets:
            hits = [p for p in top if p['name'] == t]
            print('%s_CASE %s -> %s' % (step, t, [(h['status'], h['directive']) for h in hits] or 'ZERO_MATCH'))
            want(len(hits) == 1 and plain(hits[0]), 'named case %r is not exactly one plain ok' % t)
        others = [p for p in top if p['name'] not in targets]
        for p in others:
            want(p['status'] == 'ok' and p['directive'].upper().startswith('SKIP'),
                 'other case actually ran or failed: %s %s %s' % (p['status'], p['directive'], p['name']))
        print('%s_OTHER_TOP_LEVEL_POINTS=%d (any printed must be SKIP as Node printed them; never counted as pass)' % (
            step, len(others)))
        counts({'pass': len(targets), 'fail': 0, 'cancelled': 0, 'todo': 0})
        want(plan == len(top), 'plan %s vs %d top-level points' % (plan, len(top)))
        want(summary.get('tests') == str(len(top)), 'tests=%s vs %d points' % (summary.get('tests'), len(top)))
        want(summary.get('skipped') == str(len(others)), 'skipped=%s vs %d other points' % (summary.get('skipped'), len(others)))
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
