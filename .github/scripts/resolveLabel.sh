#!/bin/zsh --no-rcs
# shellcheck disable=SC1071
#
# resolveLabel.sh — resolve a single label's attributes without running Installomator
#
# Each file in fragments/labels/ is a `case` fragment (`label) … ;;`), not a
# standalone script, so it cannot be executed directly. This wraps the fragment
# in the same `case $label in … esac` the assembled script uses, after sourcing
# functions.sh so label helpers (getJSONValue, downloadURLFromGit, versionFromGit,
# …) are available. Labels that compute appNewVersion/downloadURL via curl will
# hit the network, exactly as they do in a real run.
#
# This copy lives in the Patcher repo (it's Patcher's CI collector), not inside
# Installomator, so it has no fragments/ alongside it. Point it at an
# Installomator checkout with INSTALLOMATOR_DIR — the GitHub workflow clones
# upstream fresh and sets it. Resolution must run on macOS (arch, osascript-backed
# getJSONValue, hdiutil); a Linux box cannot resolve labels faithfully.
#
# Usage:
#   INSTALLOMATOR_DIR=/path/to/Installomator ./resolveLabel.sh <label> [<label> …]
#   INSTALLOMATOR_DIR=… ./resolveLabel.sh --eval <label>      # shell-eval'able assignments
#   INSTALLOMATOR_DIR=… ./resolveLabel.sh --json <label> …    # one NDJSON record per label
#   INSTALLOMATOR_DIR=… ./resolveLabel.sh --json --all        # every label in the checkout

emulate -L zsh

if [[ -z $INSTALLOMATOR_DIR ]]; then
    print -u2 "error: set INSTALLOMATOR_DIR to an Installomator checkout (this script lives outside it)"
    exit 78
fi
repo_dir=${INSTALLOMATOR_DIR:A}
labels_dir="$repo_dir/fragments/labels"
functions_file="$repo_dir/fragments/functions.sh"

if [[ ! -d $labels_dir || ! -r $functions_file ]]; then
    print -u2 "error: INSTALLOMATOR_DIR=$repo_dir is not an Installomator checkout (no fragments/labels or fragments/functions.sh)"
    exit 78
fi

# attributes a label may set (mirrors the debug block in fragments/main.sh)
attributes=(
    name appName type archiveName downloadURL curlOptions appNewVersion
    versionKey packageID pkgName choiceChangesXML expectedTeamID
    blockingProcesses installerTool CLIInstaller CLIArguments
    updateTool updateToolArguments updateToolRunAsCurrentUser
)
required=( name type downloadURL expectedTeamID )

mode=pretty
all=0
typeset -i jobs=8 timeout_secs=20
while [[ $1 == --* ]]; do
    case $1 in
        --eval) mode=eval ;;
        --json) mode=json ;;
        --all)  all=1 ;;
        --jobs) shift; jobs=$1 ;;        # concurrent resolutions
        --timeout) shift; timeout_secs=$1 ;;  # per-label cap (curl max-time + hard kill)
        *) print -u2 "unknown flag: $1"; exit 64 ;;
    esac
    shift
done

# discovers every label in the checkout (basename without .sh)
if (( all )); then
    set -- ${labels_dir}/*.sh(:t:r)
fi

if (( $# == 0 )); then
    print -u2 "usage: ${0:t} [--eval|--json] [--all] <label> [<label> …]"
    exit 64
fi

# escape a string for inclusion in a JSON double-quoted value
jsonEscape() {
    local s=$1
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    print -rn -- "$s"
}

# emit a JSON value: a quoted, escaped string, or null when empty
jsonStrOrNull() {
    if [[ -z $1 ]]; then print -rn -- null; else print -rn -- "\"$(jsonEscape "$1")\""; fi
}

# resolve one label in a clean subshell so labels never leak state into each other
resolveLabel() {
    local label=$1
    local labelFile="$labels_dir/$label.sh"
    if [[ ! -r $labelFile ]]; then
        print -u2 "# label '$label' not found at $labelFile"
        return 1
    fi

    source "$functions_file"
    printlog() { : }  # silence label logging

    # bind curls and *fromGit helpers to prevent stalling the whole run
    curl() { command curl --connect-timeout 10 --max-time $timeout_secs "$@"; }

    # only emitJSON writes stdout
    eval "case \$label in
$(<"$labelFile")
esac" 1>&2

    [[ $mode == json ]] && { emitJSON "$label"; return 0 }

    [[ $mode == eval ]] || print -r -- "# $label"
    local attr
    for attr in $attributes; do
        if [[ ${(Pt)attr} == *array* ]]; then
            (( ${#${(P)attr}} )) || continue
            if [[ $mode == eval ]]; then
                print -r -- "$attr=( ${(qq)${(P)attr}} )"
            else
                printf '  %-22s ( %s )\n' "$attr" "${(P)attr}"
            fi
        elif [[ -n ${(P)attr} ]]; then
            if [[ $mode == eval ]]; then
                print -r -- "$attr=${(qq)${(P)attr}}"
            else
                printf '  %-22s %s\n' "$attr" "${(P)attr}"
            fi
        fi
    done

    # appCustomVersion is a function, not a variable
    if typeset -f appCustomVersion >/dev/null; then
        [[ $mode == eval ]] || print -r -- "  appCustomVersion       (function defined)"
    fi
}

emitJSON() {
    local label=$1
    local -a parts missing
    local attr e

    local r
    for r in $required; do [[ -n ${(P)r} ]] || missing+=$r; done
    local ok=true error=""
    if (( ${#missing} )); then ok=false; error="missing: ${(j:, :)missing}"; fi

    parts+=( "\"label\":\"$(jsonEscape "$label")\"" )
    parts+=( "\"arch\":\"$(jsonEscape "$(arch 2>/dev/null)")\"" )
    parts+=( "\"resolved_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" )
    parts+=( "\"ok\":$ok" )
    parts+=( "\"error\":$(jsonStrOrNull "$error")" )
    typeset -f appCustomVersion >/dev/null && parts+=( "\"hasAppCustomVersion\":true" ) \
                                           || parts+=( "\"hasAppCustomVersion\":false" )

    for attr in $attributes; do
        if [[ ${(Pt)attr} == *array* ]]; then
            # Reset per attribute: a bare `local -a q` in a loop keeps the prior
            # field's values in zsh, bleeding them into the next array field.
            local -a q=()
            for e in "${(@P)attr}"; do q+=( "\"$(jsonEscape "$e")\"" ); done
            parts+=( "\"$attr\":[${(j:,:)q}]" )
        else
            parts+=( "\"$attr\":$(jsonStrOrNull "${(P)attr}")" )
        fi
    done

    print -r -- "{${(j:,:)parts}}"
}

# Sequential for a single label (or --jobs 1); a batched worker pool otherwise.
if (( $# == 1 || jobs <= 1 )); then
    rc=0
    for label in "$@"; do
        ( resolveLabel "$label" </dev/null ) || rc=1
    done
    exit $rc
fi

# Batched pool: run `jobs` at a time, each in its own subshell
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
typeset -i total=$# done=0 hard_timeout=$(( timeout_secs + 5 ))
typeset -a batch

# intl labels use runAsUser to obtain region's download url which will
# cause runners to hang indefinitely, and curl's --max-time can't catch
# a non-curl stall. </dev/null so nothing can block reading the terminal either.
run_one() {
    local label=$1
    resolveLabel "$label" >| "$tmpdir/$label.out" 2>/dev/null </dev/null &
    local wpid=$!
    { sleep $hard_timeout && kill -KILL $wpid 2>/dev/null } &
    local killer=$!
    wait $wpid 2>/dev/null
    kill -KILL $killer 2>/dev/null  # work finished first; cancel the watchdog
    wait $killer 2>/dev/null
}

flush_batch() {
    wait
    local l
    for l in $batch; do
        [[ -s "$tmpdir/$l.out" ]] && cat "$tmpdir/$l.out"
        rm -f "$tmpdir/$l.out"
    done
    (( done += ${#batch} ))
    printf '\rresolved %d/%d labels' "$done" "$total" >&2
    batch=()
}

for label in "$@"; do
    run_one "$label" &
    batch+=($label)
    (( ${#batch} >= jobs )) && flush_batch
done
(( ${#batch} )) && flush_batch
printf '\n' >&2  # newline after the in-place progress line
