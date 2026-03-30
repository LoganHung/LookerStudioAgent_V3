#!/bin/bash
# config_helper.sh - Pure bash (no Python/jq dependency)
# Usage: bash config_helper.sh <init|status|validate> [--config <path>]

set -e

CONFIG_DIR="./.looker-automation"
CONFIG_PATH="$CONFIG_DIR/dashboard_config.json"

COMMAND="${1:-}"
shift 2>/dev/null || true
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --config) CONFIG_PATH="$2"; CONFIG_DIR=$(dirname "$CONFIG_PATH"); shift ;;
        *) ;;
    esac
    shift
done

EMPTY_SCHEMA='{
  "vertex_ai_project_id": "",
  "data_source": { "project_id": "", "dataset": "", "table_name": "" },
  "visualizations": [],
  "responsive_rows": []
}'

# Helper: extract a top-level string value from flat JSON (handles "key": "value")
get_value() {
    grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$CONFIG_PATH" | head -1 | sed 's/.*:[[:space:]]*"\(.*\)"/\1/'
}

# Helper: check if a JSON array is non-empty (handles multi-line arrays)
array_has_items() {
    # Collapse file to single line, then check if array after key contains { or "
    local content
    content=$(tr -d '\n' < "$CONFIG_PATH")
    echo "$content" | grep -oP "\"$1\"\s*:\s*\[.*?\]" | grep -q '[{"]' && return 0 || return 1
}

case "$COMMAND" in
    init)
        mkdir -p "$CONFIG_DIR"
        if [ -f "$CONFIG_PATH" ]; then
            echo "EXISTS"
        else
            echo "$EMPTY_SCHEMA" > "$CONFIG_PATH"
            echo "CREATED"
        fi
        ;;

    status)
        if [ ! -f "$CONFIG_PATH" ]; then
            echo "RESUME_FROM=none"
            exit 0
        fi

        # Check for valid JSON (basic: file has opening brace)
        if ! grep -q '{' "$CONFIG_PATH" 2>/dev/null; then
            echo "RESUME_FROM=corrupt"
            exit 0
        fi

        vertex=$(get_value "vertex_ai_project_id")
        bq_project=$(get_value "project_id")
        dataset=$(get_value "dataset")
        table=$(get_value "table_name")

        has_data=false
        has_viz=false
        has_rows=false

        [[ -n "$vertex" && -n "$bq_project" && -n "$dataset" && -n "$table" ]] && has_data=true
        array_has_items "visualizations" && has_viz=true
        array_has_items "responsive_rows" && has_rows=true

        if $has_data && $has_viz && $has_rows; then
            echo "RESUME_FROM=complete"
        elif $has_data && $has_viz; then
            echo "RESUME_FROM=step3"
        elif $has_data; then
            echo "RESUME_FROM=step2"
        else
            echo "RESUME_FROM=step1"
        fi

        # Always output context when data exists
        $has_data && echo "VERTEX_PROJECT=$vertex" && echo "BQ_SOURCE=$bq_project/$dataset/$table"
        ;;

    validate)
        if [ ! -f "$CONFIG_PATH" ]; then
            echo "MISSING: config file not found at $CONFIG_PATH"
            exit 1
        fi

        missing=""

        vertex=$(get_value "vertex_ai_project_id")
        bq_project=$(get_value "project_id")
        dataset=$(get_value "dataset")
        table=$(get_value "table_name")

        [ -z "$vertex" ] && missing="$missing vertex_ai_project_id,"
        [ -z "$bq_project" ] && missing="$missing data_source.project_id,"
        [ -z "$dataset" ] && missing="$missing data_source.dataset,"
        [ -z "$table" ] && missing="$missing data_source.table_name,"
        array_has_items "visualizations" || missing="$missing visualizations,"
        array_has_items "responsive_rows" || missing="$missing responsive_rows,"

        if [ -n "$missing" ]; then
            # Trim trailing comma
            missing=$(echo "$missing" | sed 's/,$//')
            echo "MISSING:$missing"
            exit 1
        else
            echo "VALID"
        fi
        ;;

    set_user_data_dir)
        if [ ! -f "$CONFIG_PATH" ]; then
            echo "MISSING: config file not found at $CONFIG_PATH"
            exit 1
        fi

        chrome_src="${HOME}/.config/google-chrome"
        chrome_dest="$(pwd)/chrome-profile"

        if [ ! -d "$chrome_src" ]; then
            echo "MISSING: Chrome data directory not found at $chrome_src"
            exit 1
        fi

        if [ -d "$chrome_dest" ]; then
            echo "EXISTS: chrome-profile already exists at $chrome_dest, skipping copy"
        else
            echo "Copying Chrome profile to $chrome_dest ..."
            cp -r "$chrome_src" "$chrome_dest"
        fi

        if grep -q '"user_data_dir"' "$CONFIG_PATH"; then
            sed -i "s|\"user_data_dir\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"user_data_dir\": \"$chrome_dest\"|" "$CONFIG_PATH"
        else
            sed -i "0,/{/s|{|{\n  \"user_data_dir\": \"$chrome_dest\",|" "$CONFIG_PATH"
        fi

        echo "SET: user_data_dir=$chrome_dest"
        ;;

    *)
        echo "Usage: bash config_helper.sh <init|status|validate|set_user_data_dir> [--config <path>]"
        exit 1
        ;;
esac
