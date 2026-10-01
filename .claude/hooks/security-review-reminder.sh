#!/bin/bash
# PostToolUse(Edit|Write): once per session, remind Claude to run django-security-reviewer
# after a security-sensitive file is modified.
input=$(cat)
file=$(jq -r '.tool_input.file_path // empty' <<<"$input")
session=$(jq -r '.session_id // "nosession"' <<<"$input")

case "$file" in
  */apps/api/*|*/permissions.py|*/consumers.py|*/pbx/settings.py|*/core/conf.py|*/core/storages.py|*/services/fastagi/*) ;;
  *) exit 0 ;;
esac

marker="${TMPDIR:-/tmp}/pearlpbx2-secreview-$session"
[ -e "$marker" ] && exit 0
touch "$marker"

jq -n --arg f "${file##*/}" '{hookSpecificOutput: {hookEventName: "PostToolUse",
  additionalContext: ("Security-sensitive file changed (" + $f + "). Before finishing, run the django-security-reviewer agent on the diff.")}}'
