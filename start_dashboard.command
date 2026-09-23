#!/bin/zsh
# Start the local Streamlit dashboard from this repository.
set -eu

project_root="${0:A:h}"
cd "$project_root"

uv_command="$(command -v uv 2>/dev/null || true)"
for candidate in \
  "${HOME}/.local/bin/uv" \
  "${HOME}/.cargo/bin/uv" \
  "/opt/homebrew/bin/uv" \
  "/usr/local/bin/uv"; do
  if [[ -z "$uv_command" && -x "$candidate" ]]; then
    uv_command="$candidate"
  fi
done

if [[ -z "$uv_command" ]]; then
  osascript -e 'display alert "uv が見つかりません" message "uv をインストールしてから、もう一度起動してください。" as critical'
  exit 1
fi

exec "$uv_command" run streamlit run app/streamlit_app.py
