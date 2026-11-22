#!/usr/bin/env bash
# mirror_sync.sh — push the governing branch and all tags to a second (mirror) host.
#
# Independence doctrine (docs/benchmark/STRATEGIC_LEADERSHIP_PLAN.md, P0):
# a project must not be a single-host failure point (the OneGeology lesson).
# This script is deliberately conservative:
#   - fast-forward pushes only: no forced updates, no mirror deletion semantics;
#   - verifies that the mirror reports the exact same hashes after the push;
#   - refuses to "mirror" into the origin remote itself (a no-op loop);
#   - reports tag signing state honestly (unsigned tags are stated, not hidden).
#
# Configuration (environment, CLI flags override):
#   GEOLOGIA_MIRROR_REMOTE_URL   mirror URL or local bare-repo path.
#                                Unset => clean skip with exit 0 (CI-safe).
#   GEOLOGIA_MIRROR_BRANCH       branch to sync (default: current branch).
#   GEOLOGIA_MIRROR_REMOTE_NAME  remote name to add in the source repo
#                                (default: mirror).
#
# Usage:
#   scripts/mirror_sync.sh [--repo DIR] [--url URL] [--branch B] [--remote-name N]
#
# Exit codes: 0 success or clean skip; 2 usage/config error;
#             3 push failure; 1 post-push verification mismatch.
set -u

REPO="."
URL="${GEOLOGIA_MIRROR_REMOTE_URL:-}"
BRANCH="${GEOLOGIA_MIRROR_BRANCH:-}"
REMOTE_NAME="${GEOLOGIA_MIRROR_REMOTE_NAME:-mirror}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo) REPO="${2:?--repo needs a value}"; shift 2 ;;
        --url) URL="${2:?--url needs a value}"; shift 2 ;;
        --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
        --remote-name) REMOTE_NAME="${2:?--remote-name needs a value}"; shift 2 ;;
        *) echo "[mirror] unknown option: $1" >&2; exit 2 ;;
    esac
done

REPO="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO" ]; then
    echo "[mirror] --repo does not point at a git work tree" >&2
    exit 2
fi

if [ -z "$URL" ]; then
    echo "[mirror] skipped: GEOLOGIA_MIRROR_REMOTE_URL is not set and no --url given."
    echo "[mirror] skipped: the second host is the owner's account decision (ADR-0009);"
    echo "[mirror] skipped: machinery is active, external activation is pending."
    exit 0
fi

# One URL scheme allow-list: no exotic transports, no relative-path escapes.
case "$URL" in
    http://*|https://*|ssh://*|git://*|file://*|/*) ;;
    *) echo "[mirror] unsupported mirror URL scheme: $URL" >&2; exit 2 ;;
esac

ORIGIN_URL="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
if [ -n "$ORIGIN_URL" ] && [ "$ORIGIN_URL" = "$URL" ]; then
    echo "[mirror] refusing to mirror into the origin remote itself ($ORIGIN_URL)" >&2
    exit 2
fi

if git -C "$REPO" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    git -C "$REPO" remote set-url "$REMOTE_NAME" "$URL"
else
    git -C "$REPO" remote add "$REMOTE_NAME" "$URL"
fi

if [ -z "$BRANCH" ]; then
    BRANCH="$(git -C "$REPO" symbolic-ref --short HEAD)"
fi

echo "[mirror] syncing branch $BRANCH to $REMOTE_NAME ($URL)"
if ! git -C "$REPO" push "$REMOTE_NAME" "refs/heads/$BRANCH:refs/heads/$BRANCH"; then
    echo "[mirror] branch push failed (fast-forward only; history divergence stays visible)" >&2
    exit 3
fi

if ! git -C "$REPO" push "$REMOTE_NAME" --tags; then
    echo "[mirror] tag push failed (an existing mirror tag with a different hash blocks it)" >&2
    exit 3
fi

# Post-push verification: the mirror must report exactly our hashes.
MIRROR_BRANCH_HASH="$(git -C "$REPO" ls-remote "$REMOTE_NAME" "refs/heads/$BRANCH" | awk '{print $1}')"
LOCAL_BRANCH_HASH="$(git -C "$REPO" rev-parse "refs/heads/$BRANCH")"
MISMATCH=0
if [ "$MIRROR_BRANCH_HASH" != "$LOCAL_BRANCH_HASH" ]; then
    echo "[mirror] MISMATCH branch $BRANCH: local=$LOCAL_BRANCH_HASH mirror=${MIRROR_BRANCH_HASH:-absent}" >&2
    MISMATCH=1
fi

TAG_FAILURES=""
SIGNED=0
TOTAL=0
for TAG in $(git -C "$REPO" for-each-ref --format='%(refname:short)' refs/tags); do
    TOTAL=$((TOTAL + 1))
    LOCAL_TAG_HASH="$(git -C "$REPO" rev-parse "refs/tags/$TAG")"
    MIRROR_TAG_HASH="$(git -C "$REPO" ls-remote "$REMOTE_NAME" "refs/tags/$TAG" | awk '{print $1}')"
    if [ "$MIRROR_TAG_HASH" != "$LOCAL_TAG_HASH" ]; then
        TAG_FAILURES="$TAG_FAILURES $TAG"
    fi
    if git -C "$REPO" rev-parse "refs/tags/$TAG^{commit}" >/dev/null 2>&1 \
        && [ "$(git -C "$REPO" rev-parse "refs/tags/$TAG")" \
            != "$(git -C "$REPO" rev-parse "refs/tags/$TAG^{commit}")" ] \
        && git -C "$REPO" cat-file tag "refs/tags/$TAG" 2>/dev/null \
            | grep -q "BEGIN PGP SIGNATURE"; then
        SIGNED=$((SIGNED + 1))
    fi
done

if [ -n "$TAG_FAILURES" ]; then
    echo "[mirror] MISMATCH tags:$TAG_FAILURES" >&2
    MISMATCH=1
fi

if [ "$MISMATCH" -ne 0 ]; then
    echo "[mirror] FAILED: mirror does not report our hashes" >&2
    exit 1
fi

echo "[mirror] PASS branch=$BRANCH@$LOCAL_BRANCH_HASH tags=$TOTAL signed_tags=$SIGNED/$TOTAL"
echo "[mirror] signed-tag honesty: $SIGNED/$TOTAL tags carry a PGP signature;"
echo "[mirror] signing activates when a release key is provisioned (ADR-0009)."
echo "[mirror] verified $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
