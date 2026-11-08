# reverse request 064: exactly one node --test call per step, then a blocking identity gate (temp branch only, never merged).
# usage: bash test064.sh <A|B1|B2|B3>
# The test's real exit code goes to $O/<step>-exit.txt and the step output "rc"; it is judged by the next (result) step.
# This script itself exits non-zero, blocking every later step, if the DSH_PREFIX pre-check or the post-command
# identity gate fails. No retry, no set -e, no "|| true".
set +e
STEP=$1; X=${STEP:0:1}
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; I="$RUNNER_TEMP/iso-$X"
case "$X" in A) EXP="$RUNNER_TEMP/raw/2609-expected-combined-A.patch";; B) EXP="$RUNNER_TEMP/raw/2609-expected-combined-B.patch";; *) echo "unknown step"; exit 2;; esac
cd "$T" || { echo "NO_TREE $T"; exit 2; }
if [ -n "${DSH_PREFIX+x}" ]; then echo "DSH_PREFIX_GATE=FAIL (set to '$DSH_PREFIX'); command not run"; exit 5; fi
echo "DSH_PREFIX_GATE=PASS (unset)"
echo "STEP=$STEP CWD=$(pwd) NODE_BIN=$(command -v node) EUID=$(id -u) HOME=$HOME"
echo "ISOLATION_BEFORE TMPDIR=$I/tmp entries=$(find "$I/tmp" -mindepth 1 | wc -l) DSH_HOME=$I/dsh-home entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"
case "$STEP" in
A|B1) ARGS=(runtime/tests/native-invoke-clock.test.mjs); SHOW='runtime/tests/native-invoke-clock.test.mjs';;
B2) ARGS=('--test-name-pattern=core: invoke token bucket and concurrency$' runtime/tests/native-unit.test.mjs)
    SHOW='--test-name-pattern="core: invoke token bucket and concurrency$" runtime/tests/native-unit.test.mjs';;
B3) ARGS=('--test-name-pattern=(normal direct result and unrelated panel replacement preserve the action|current handler rejection keeps existing plugin-error contract)$' runtime/tests/native-invoke-generation.test.mjs)
    SHOW='--test-name-pattern="(normal direct result and unrelated panel replacement preserve the action|current handler rejection keeps existing plugin-error contract)$" runtime/tests/native-invoke-generation.test.mjs';;
*) echo "unknown step"; exit 2;;
esac
echo "+ TZ=Asia/Shanghai TMPDIR=$I/tmp DSH_HOME=$I/dsh-home node --test --test-reporter=tap --test-concurrency=1 $SHOW"
printf 'ARGV_EXACT:'; printf ' [%s]' --test --test-reporter=tap --test-concurrency=1 "${ARGS[@]}"; printf '\n'
S0=$(date +%s.%N); echo "=== CMD_$STEP BEGIN $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
TZ=Asia/Shanghai TMPDIR="$I/tmp" DSH_HOME="$I/dsh-home" node --test --test-reporter=tap --test-concurrency=1 "${ARGS[@]}" > "$O/$STEP-node-test.stdout" 2> "$O/$STEP-node-test.stderr"
rc=$?
S1=$(date +%s.%N)
echo "=== CMD_$STEP END $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) CMD_EXIT=$rc seconds=$(awk -v a="$S0" -v b="$S1" 'BEGIN{printf "%.3f", b-a}') invocations=1"
echo "$rc" > "$O/$STEP-exit.txt"
echo "rc=$rc" >> "$GITHUB_OUTPUT"
echo "--- STDOUT $STEP $(wc -c < "$O/$STEP-node-test.stdout") B $(wc -l < "$O/$STEP-node-test.stdout") lines sha256=$(sha256sum "$O/$STEP-node-test.stdout" | cut -c1-64) ---"
cat "$O/$STEP-node-test.stdout"
echo "--- STDERR $STEP $(wc -c < "$O/$STEP-node-test.stderr") B sha256=$(sha256sum "$O/$STEP-node-test.stderr" | cut -c1-64) ---"
cat "$O/$STEP-node-test.stderr"
echo "--- END $STEP ---"
echo "--- last 100 stdout lines of $STEP saved separately ---"
tail -n 100 "$O/$STEP-node-test.stdout" > "$O/$STEP-node-test.stdout.last100"
echo "$STEP-node-test.stdout.last100 = tail -n 100 of the stdout printed above ($(wc -l < "$O/$STEP-node-test.stdout.last100") lines)"
echo "ISOLATION_AFTER TMPDIR entries=$(find "$I/tmp" -mindepth 1 | wc -l) DSH_HOME entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"
find "$I/tmp" "$I/dsh-home" -mindepth 1 -maxdepth 2 | head -40
echo "--- post-command identity gate (blocking; loads no product code) ---"
python3 -I "$RUNNER_TEMP/ident064.py" post "$T" "$X" "$EXP" "${STEP}_AFTER" "$O/$STEP-diff-after.patch" "$O/$STEP-status-after.txt"
irc=$?
echo "POST_IDENT_EXIT=$irc"
if [ "$irc" -ne 0 ]; then echo "IDENT_GATE_${STEP}=FAIL -> stopping; later steps will not run"; exit 6; fi
echo "IDENT_GATE_${STEP}=PASS"
exit 0
