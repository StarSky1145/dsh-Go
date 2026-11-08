# reverse request 064 preparation for one tree (temp branch only, never merged).
# usage: bash prep064.sh <A|B> <2609 raw patch file name> <expected-combined file name>
# Order: fresh detached worktree at the base -> identity pre -> 2608 FULL apply --check/apply/add -N/diff --check ->
# stage identity (whole diff vs base == 2608 raw) -> 2609 apply --check/apply/add -N/diff --check -> final identity
# (whole diff vs base == expected-combined). Nothing is staged; no commit is made. Any non-zero step stops at once.
set +e
X=$1; RAW2609=$2; EXPNAME=$3
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; I="$RUNNER_TEMP/iso-$X"; ID="$RUNNER_TEMP/ident064.py"
P2608="$RUNNER_TEMP/raw/2608-native-feed-monotonic-LF.patch"; P2609="$RUNNER_TEMP/raw/$RAW2609"; EXP="$RUNNER_TEMP/raw/$EXPNAME"
run() { echo "+ $* [$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)]"; "$@"; rc=$?; echo "  EXIT=$rc [$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)]"; [ $rc -eq 0 ] || { echo "PREP_${X}_STOPPED rc=$rc"; exit $rc; }; }
echo "=== PREP_$X BEGIN $(date -u +%Y-%m-%dT%H:%M:%SZ) base=$BASE 2608=$(basename "$P2608") 2609=$RAW2609 expected=$EXPNAME tree=$T isolation=$I"
[ ! -e "$T" ] && [ ! -L "$T" ] || { echo "TREE_EXISTS $T"; echo "PREP_${X}_STOPPED rc=1"; exit 1; }
[ ! -e "$I" ] || { echo "ISOLATION_EXISTS $I"; echo "PREP_${X}_STOPPED rc=1"; exit 1; }
run git -c core.autocrlf=false worktree add --detach "$T" "$BASE"
run python3 -I "$ID" pre "$T"
run git -c core.autocrlf=false -C "$T" apply --check "$P2608"
run git -c core.autocrlf=false -C "$T" apply "$P2608"
run git -c core.autocrlf=false -C "$T" add -N runtime/tests/native-feed-clock.test.mjs
run git -c core.autocrlf=false -C "$T" diff --check
run python3 -I "$ID" stage "$T" "$X" "$P2608" "$O/$X-diff-stage2608.patch" "$O/$X-status-stage2608.txt"
run git -c core.autocrlf=false -C "$T" apply --check "$P2609"
run git -c core.autocrlf=false -C "$T" apply "$P2609"
run git -c core.autocrlf=false -C "$T" add -N runtime/tests/native-invoke-clock.test.mjs
run git -c core.autocrlf=false -C "$T" diff --check
run python3 -I "$ID" post "$T" "$X" "$EXP" PREP "$O/$X-diff-before-tests.patch" "$O/$X-status-before-tests.txt"
run mkdir "$I" "$I/tmp" "$I/dsh-home"
echo "ISOLATION_$X TMPDIR=$I/tmp entries=$(find "$I/tmp" -mindepth 1 | wc -l) DSH_HOME=$I/dsh-home entries=$(find "$I/dsh-home" -mindepth 1 | wc -l) HOME=$HOME (unchanged)"
echo "TREE_$X HEAD=$(git -c core.autocrlf=false -C "$T" rev-parse HEAD)"
echo "=== PREP_$X OK $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit 0
