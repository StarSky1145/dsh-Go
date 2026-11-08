# reverse request 056 preparation for one tree (temp branch only, never merged).
# usage: bash prep056.sh <A|B> <raw patch file name>. Any non-zero step stops at once (no retry).
set +e
X=$1; RAWNAME=$2
O="$RUNNER_TEMP/out"; T="$RUNNER_TEMP/tree-$X"; P="$RUNNER_TEMP/pfx-$X"; ID="$RUNNER_TEMP/ident056.py"
run() { echo "+ $* [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"; "$@"; rc=$?; echo "  EXIT=$rc"; [ $rc -eq 0 ] || { echo "PREP_${X}_STOPPED rc=$rc"; exit $rc; }; }
stop() { echo "PREP_${X}_STOPPED rc=$1"; exit $1; }
echo "=== PREP_$X BEGIN $(date -u +%Y-%m-%dT%H:%M:%SZ) base=$BASE raw=$RAWNAME tree=$T prefix=$P"
[ ! -e "$T" ] && [ ! -L "$T" ] || { echo "TREE_EXISTS $T"; stop 1; }
run git -c core.autocrlf=false worktree add --detach "$T" "$BASE"
run python3 -I "$ID" pre "$T"
run git -c core.autocrlf=false -C "$T" apply --check "$RUNNER_TEMP/raw/$RAWNAME"
run git -c core.autocrlf=false -C "$T" apply "$RUNNER_TEMP/raw/$RAWNAME"
echo "+ git -c core.autocrlf=false -C $T diff > $O/$X-diff.txt [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
git -c core.autocrlf=false -C "$T" diff > "$O/$X-diff.txt"; rc=$?
echo "  EXIT=$rc bytes=$(wc -c < "$O/$X-diff.txt") sha256=$(sha256sum "$O/$X-diff.txt" | cut -c1-64)"
[ $rc -eq 0 ] || stop $rc
echo "----- full diff $X -----"; cat "$O/$X-diff.txt"; echo "----- end diff $X -----"
run git -c core.autocrlf=false -C "$T" diff --check
run python3 -I "$ID" post "$T" "$X"
[ ! -e "$P" ] && [ ! -L "$P" ] || { echo "PREFIX_EXISTS $P"; stop 1; }
echo "PREFIX_ABSENT_BEFORE $P"
echo "+ (cwd $T) node runtime/media/dsh-media/test/headless-v2/prepare.mjs --out $P [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
(cd "$T" && node runtime/media/dsh-media/test/headless-v2/prepare.mjs --out "$P") > "$O/$X-prepare.stdout" 2> "$O/$X-prepare.stderr"; rc=$?
echo "  EXIT=$rc"
echo "  prepare stdout ($(wc -c < "$O/$X-prepare.stdout") B):"; cat "$O/$X-prepare.stdout"
echo "  prepare stderr ($(wc -c < "$O/$X-prepare.stderr") B):"; cat "$O/$X-prepare.stderr"
[ $rc -eq 0 ] || stop $rc
cp "$P/test-inputs.json" "$O/$X-test-inputs.json"
run python3 -I "$ID" prefix "$T" "$P" "${X}_AFTER_PREPARE"
echo "+ npm ci --ignore-scripts --no-audit --no-fund --prefix $P [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
npm ci --ignore-scripts --no-audit --no-fund --prefix "$P" > "$O/$X-npm-ci.stdout" 2> "$O/$X-npm-ci.stderr"; rc=$?
echo "  EXIT=$rc [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
echo "  npm stdout ($(wc -c < "$O/$X-npm-ci.stdout") B):"; cat "$O/$X-npm-ci.stdout"
echo "  npm stderr ($(wc -c < "$O/$X-npm-ci.stderr") B):"; cat "$O/$X-npm-ci.stderr"
[ $rc -eq 0 ] || stop $rc
run python3 -I "$ID" prefix "$T" "$P" "${X}_AFTER_NPM_CI"
L="$T/runtime/media/dsh-media/node_modules"
[ ! -e "$L" ] && [ ! -L "$L" ] || { echo "LINK_POSITION_EXISTS $L"; stop 1; }
echo "LINK_POSITION_ABSENT_BEFORE $L"
run ln -s "$P/node_modules" "$L"
echo "SYMLINK $L -> $(readlink "$L") realpath=$(realpath "$L")"
run python3 -I "$ID" pins "$T" "${X}_BEFORE_TEST"
echo "=== PREP_$X OK $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit 0
