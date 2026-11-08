# reverse request 059 preparation for one tree (temp branch only, never merged).
# usage: bash prep059.sh <A|B> <raw patch file name>. Any non-zero step stops at once; no retry, no tree rebuild.
set +e
X=$1; RAWNAME=$2
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; I="$RUNNER_TEMP/iso-$X"; ID="$RUNNER_TEMP/ident059.py"; RAWP="$RUNNER_TEMP/raw/$RAWNAME"
run() { echo "+ $* [$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)]"; "$@"; rc=$?; echo "  EXIT=$rc"; [ $rc -eq 0 ] || { echo "PREP_${X}_STOPPED rc=$rc"; exit $rc; }; }
echo "=== PREP_$X BEGIN $(date -u +%Y-%m-%dT%H:%M:%SZ) base=$BASE raw=$RAWNAME tree=$T isolation=$I"
[ ! -e "$T" ] && [ ! -L "$T" ] || { echo "TREE_EXISTS $T"; echo "PREP_${X}_STOPPED rc=1"; exit 1; }
[ ! -e "$I" ] || { echo "ISOLATION_EXISTS $I"; echo "PREP_${X}_STOPPED rc=1"; exit 1; }
run git -c core.autocrlf=false worktree add --detach "$T" "$BASE"
run python3 -I "$ID" pre "$T"
run git -c core.autocrlf=false -C "$T" apply --check "$RAWP"
run git -c core.autocrlf=false -C "$T" apply "$RAWP"
run git -c core.autocrlf=false -C "$T" diff --check
run git -c core.autocrlf=false -C "$T" add -N runtime/tests/native-capability-clock.test.mjs
run python3 -I "$ID" post "$T" "$X" "$RAWP" "${X}_PREP" "$O/$X-diff-before-tests.patch"
run mkdir "$I" "$I/tmp" "$I/dsh-home"
echo "ISOLATION_$X TMPDIR=$I/tmp DSH_HOME=$I/dsh-home HOME=$HOME (unchanged)"
echo "=== PREP_$X OK $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit 0
