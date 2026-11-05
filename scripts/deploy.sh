#!/bin/sh
# Deploy from a local clone to a Docker host that has no git checkout (e.g. a
# NAS): update the clone, copy everything that matters — docker-compose.yaml
# and requirements.txt included, which are easy to forget and leave the target
# on an old configuration without any warning — then rebuild and show the logs.
#
#   NAS=user@host DIR=/path/on/host scripts/deploy.sh
#
# Optional:
#   OVERLAY=/path/to/private/folder   copied over DIR after the code: per-
#       deployment extensions (app/extensions/*.py), personal.env,
#       docker-compose.override.yml… — see "Extensions & private overlay" in
#       the README. Keeps personal things out of this public repo.
#   DOCKER="sudo /usr/bin/docker"     docker command on the host (default).
#
# Everything runs inside a function: the shell reads the whole function before
# running it, and this script updates itself with the "git reset" below.
# Without it, sh would keep reading a file that changed under its feet. A
# change to THIS script only takes effect on the next run, so when the reset
# changes it the script re-executes itself once.

set -u

: "${NAS:?set NAS=user@host (the Docker host to deploy to)}"
: "${DIR:?set DIR=/path/of/the/project/on/the/host}"
OVERLAY=${OVERLAY:-}
DOCKER=${DOCKER:-sudo /usr/bin/docker}
REPO=${REPO:-$(cd "$(dirname "$0")/.." && pwd)}
SELF=$REPO/scripts/deploy.sh

main() {
  cd "$REPO" || exit 1

  echo "==> updating the clone ($REPO)"
  before=$(git hash-object "$SELF")
  git fetch origin || exit 1
  git reset --hard origin/main || exit 1

  # If the reset changed this very script, restart with the new version;
  # DEPLOY_RESTARTED prevents a loop if something went wrong.
  if [ "$before" != "$(git hash-object "$SELF")" ] && [ -z "${DEPLOY_RESTARTED:-}" ]; then
    echo "==> deploy.sh updated: restarting with the new version"
    DEPLOY_RESTARTED=1
    export DEPLOY_RESTARTED
    exec sh "$SELF" "$@"
  fi

  # Better to stop right away than scatter files in a new place and rebuild
  # an old container.
  if ! ssh "$NAS" "test -d $DIR/app"; then
    echo "!!  $DIR/app does not exist on $NAS. Folders in $(dirname "$DIR"):"
    ssh "$NAS" "ls $(dirname "$DIR")"
    echo "    run again with DIR=<the right one> $0"
    exit 1
  fi
  if [ -n "$OVERLAY" ] && [ ! -d "$OVERLAY" ]; then
    echo "!!  OVERLAY=$OVERLAY is not a folder"
    exit 1
  fi

  echo "==> copying the code to $NAS"
  scp -O app/*.py app/requirements.txt "$NAS:$DIR/app/" || exit 1
  scp -O Dockerfile docker-compose.yaml "$NAS:$DIR/" || exit 1
  # Extensions come only from the overlay: start from an empty folder so a
  # module removed from the overlay doesn't linger in the image.
  ssh "$NAS" "rm -rf $DIR/app/extensions && mkdir -p $DIR/app/extensions" || exit 1
  if [ -n "$OVERLAY" ]; then
    echo "==> copying the overlay ($OVERLAY)"
    # tar keeps the layout; COPYFILE_DISABLE stops macOS tar from adding
    # ._* AppleDouble files, which would land in app/extensions as "modules".
    COPYFILE_DISABLE=1 tar -C "$OVERLAY" --exclude=.git --exclude=.DS_Store \
      --exclude=__pycache__ -cf - . | ssh "$NAS" "tar -C $DIR -xf -" || exit 1
  fi

  echo "==> rebuilding on $NAS"
  # data/ is bind-mounted on /app/data: the Dockerfile's chown doesn't reach
  # it, only the owner on the host counts. Docker creates a missing folder as
  # root, so a freshly moved project restart-loops on PermissionError.
  #
  # The container runs as uid 1000, so the numeric uid is what matters, not
  # the ssh user's name. Check first and fix only when needed: "sudo docker"
  # is often passwordless, "sudo chown" is not, and without -t sudo can't
  # even ask — asking on every deploy for something rarely needed is worse.
  owner=$(ssh "$NAS" "stat -c %u $DIR/data" 2>/dev/null)
  if [ "${owner:-unknown}" != "1000" ]; then
    echo "!!  $DIR/data belongs to uid ${owner:-unknown}, not 1000"
    echo "    fixing it now: sudo on the host asks for the password"
    ssh -t "$NAS" "sudo mkdir -p $DIR/data && sudo chown -R 1000:1000 $DIR/data" || exit 1
  fi
  # --remove-orphans: a renamed service would otherwise leave the old
  # container running, and two bots polling the same token fight each other.
  ssh "$NAS" "cd $DIR && $DOCKER compose up -d --build --remove-orphans" || exit 1

  # The container has just restarted: without a pause the logs are empty and
  # it looks broken.
  sleep 5
  echo "==> logs"
  ssh "$NAS" "cd $DIR && $DOCKER compose logs --tail 15"
}

main "$@"
