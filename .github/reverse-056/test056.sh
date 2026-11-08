# reverse request 056: the single node --test call for one tree (temp branch only, never merged).
# usage: bash test056.sh <A|B>. The real exit code is kept in $O/<X>-exit.txt and the step output; no retry.
set +e
X=$1
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; I="$RUNNER_TEMP/iso-$X"
mkdir "$I" "$I/tmp" "$I/dsh-home" || { echo "ISOLATION_MKDIR_FAILED"; exit 1; }
echo "ISOLATION_$X TMPDIR=$I/tmp DSH_HOME=$I/dsh-home HOME=$HOME (unchanged) TZ=Asia/Shanghai tmp_entries=$(find "$I/tmp" -mindepth 1 | wc -l) dsh_home_entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"
cd "$T" || exit 1
echo "NODE_EUID=$(node -p 'process.geteuid()') NODE=$(node --version) CWD=$(pwd)"
B0=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ); S0=$(date +%s.%N)
echo "=== CMD_$X BEGIN $B0 cwd=$(pwd)"
if [ "$X" = A ]; then
  echo '+ TZ=Asia/Shanghai TMPDIR='"$I/tmp"' DSH_HOME='"$I/dsh-home"' node --test --test-reporter=tap --test-name-pattern="media engine rejects (quote|backslash)-escaped credential in prompt before submission" runtime/media/dsh-media/test/media-v2.test.js'
  TZ=Asia/Shanghai TMPDIR="$I/tmp" DSH_HOME="$I/dsh-home" node --test --test-reporter=tap --test-name-pattern="media engine rejects (quote|backslash)-escaped credential in prompt before submission" runtime/media/dsh-media/test/media-v2.test.js > "$O/$X-node-test.stdout" 2> "$O/$X-node-test.stderr"
  rc=$?
else
  echo '+ TZ=Asia/Shanghai TMPDIR='"$I/tmp"' DSH_HOME='"$I/dsh-home"' node --test --test-reporter=tap runtime/media/dsh-media/test/media-v2.test.js'
  TZ=Asia/Shanghai TMPDIR="$I/tmp" DSH_HOME="$I/dsh-home" node --test --test-reporter=tap runtime/media/dsh-media/test/media-v2.test.js > "$O/$X-node-test.stdout" 2> "$O/$X-node-test.stderr"
  rc=$?
fi
E0=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ); S1=$(date +%s.%N)
echo "=== CMD_$X END $E0 CMD_EXIT=$rc seconds=$(awk -v a="$S0" -v b="$S1" 'BEGIN{printf "%.3f", b-a}') invocations=1"
echo "$rc" > "$O/$X-exit.txt"
echo "rc=$rc" >> "$GITHUB_OUTPUT"
echo "--- STDOUT $X $(wc -c < "$O/$X-node-test.stdout") B sha256=$(sha256sum "$O/$X-node-test.stdout" | cut -c1-64) ---"
cat "$O/$X-node-test.stdout"
echo "--- STDERR $X $(wc -c < "$O/$X-node-test.stderr") B sha256=$(sha256sum "$O/$X-node-test.stderr" | cut -c1-64) ---"
cat "$O/$X-node-test.stderr"
echo "--- END $X ---"
echo "TMPDIR_AFTER_$X entries=$(find "$I/tmp" -mindepth 1 | wc -l)"; find "$I/tmp" -maxdepth 2 -mindepth 1 | head -40
echo "DSH_HOME_AFTER_$X entries=$(find "$I/dsh-home" -mindepth 1 | wc -l)"; find "$I/dsh-home" -maxdepth 3 -mindepth 1 | head -40
python3 -I "$RUNNER_TEMP/ident056.py" pins "$T" "${X}_AFTER_TEST"
echo "TREE_STATUS_AFTER_$X:"; git -c core.autocrlf=false -C "$T" status --porcelain=v1 --untracked-files=all
exit 0
