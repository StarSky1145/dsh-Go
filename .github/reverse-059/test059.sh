# reverse request 059: exactly one node --test call per step (temp branch only, never merged).
# usage: bash test059.sh <A1|A2|B1|B2>. The real exit code goes to $O/<step>-exit.txt and the step output; no retry.
set +e
STEP=$1; X=${STEP:0:1}
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; I="$RUNNER_TEMP/iso-$X"
case "$X" in A) RAWP="$RUNNER_TEMP/raw/2605-TESTONLY-capability-monotonic-pacing-LF.patch";; B) RAWP="$RUNNER_TEMP/raw/2605-capability-monotonic-pacing-LF.patch";; esac
cd "$T" || exit 1
echo "STEP=$STEP CWD=$(pwd) NODE=$(node --version) NODE_BIN=$(command -v node) EUID=$(id -u) HOME=$HOME DSH_PREFIX=${DSH_PREFIX-<unset>}"
echo "ISOLATION_BEFORE TMPDIR=$I/tmp entries=$(find "$I/tmp" -mindepth 1 | wc -l) DSH_HOME=$I/dsh-home entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"
S0=$(date +%s.%N); echo "=== CMD_$STEP BEGIN $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
case "$STEP" in
A1|A2|B1)
  case "$STEP" in
    A1) FILES="runtime/tests/native-capability-clock.test.mjs";;
    A2) FILES="runtime/tests/native-micro-generation.test.mjs";;
    B1) FILES="runtime/tests/native-capability-clock.test.mjs runtime/tests/native-micro-generation.test.mjs";;
  esac
  echo "+ TZ=Asia/Shanghai TMPDIR=$I/tmp DSH_HOME=$I/dsh-home node --test --test-reporter=tap --test-concurrency=1 $FILES"
  TZ=Asia/Shanghai TMPDIR="$I/tmp" DSH_HOME="$I/dsh-home" node --test --test-reporter=tap --test-concurrency=1 $FILES > "$O/$STEP-node-test.stdout" 2> "$O/$STEP-node-test.stderr"
  rc=$?;;
B2)
  echo '+ TZ=Asia/Shanghai TMPDIR='"$I/tmp"' DSH_HOME='"$I/dsh-home"' node --test --test-reporter=tap --test-concurrency=1 --test-name-pattern="micro starts on first subscriber, coalesces latest at 10Hz, immediately disposes last|speechStart clears audio role while voice survives; speech edges are paced, terminals never dropped" runtime/tests/native-capabilities.test.mjs'
  TZ=Asia/Shanghai TMPDIR="$I/tmp" DSH_HOME="$I/dsh-home" node --test --test-reporter=tap --test-concurrency=1 --test-name-pattern="micro starts on first subscriber, coalesces latest at 10Hz, immediately disposes last|speechStart clears audio role while voice survives; speech edges are paced, terminals never dropped" runtime/tests/native-capabilities.test.mjs > "$O/$STEP-node-test.stdout" 2> "$O/$STEP-node-test.stderr"
  rc=$?;;
*) echo "unknown step"; exit 1;;
esac
S1=$(date +%s.%N)
echo "=== CMD_$STEP END $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) CMD_EXIT=$rc seconds=$(awk -v a="$S0" -v b="$S1" 'BEGIN{printf "%.3f", b-a}') invocations=1"
echo "$rc" > "$O/$STEP-exit.txt"
echo "rc=$rc" >> "$GITHUB_OUTPUT"
echo "--- STDOUT $STEP $(wc -c < "$O/$STEP-node-test.stdout") B sha256=$(sha256sum "$O/$STEP-node-test.stdout" | cut -c1-64) ---"
cat "$O/$STEP-node-test.stdout"
echo "--- STDERR $STEP $(wc -c < "$O/$STEP-node-test.stderr") B sha256=$(sha256sum "$O/$STEP-node-test.stderr" | cut -c1-64) ---"
cat "$O/$STEP-node-test.stderr"
echo "--- END $STEP ---"
echo "ISOLATION_AFTER TMPDIR entries=$(find "$I/tmp" -mindepth 1 | wc -l) DSH_HOME entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"
find "$I/tmp" "$I/dsh-home" -mindepth 1 -maxdepth 2 | head -40
echo "--- post-command identity (report only; loads no product code) ---"
python3 -I "$RUNNER_TEMP/ident059.py" post "$T" "$X" "$RAWP" "${STEP}_AFTER" "$O/$STEP-diff-after.patch"
echo "POST_IDENT_EXIT=$?"
exit 0
