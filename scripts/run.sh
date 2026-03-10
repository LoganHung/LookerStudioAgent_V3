#!/bin/bash
set -e

CONFIG_PATH=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --config) CONFIG_PATH="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$CONFIG_PATH" ]; then
    echo "❌ Error: --config path is required"
    exit 1
fi

echo "🚀 Starting Looker Studio Automation Environment Setup..."
echo ""

# Resolve dynamic paths inside the skill folder
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SKILL_DIR=$(dirname "$SCRIPT_DIR")
REQUIREMENTS_PATH="$SKILL_DIR/assets/requirements.txt"
PYTHON_SCRIPT_PATH="$SCRIPT_DIR/test_vision_click_action.py"

# Use the skill directory as the stable base for the Python environment
PROJECT_ROOT="$SKILL_DIR"

# =========================================================================================
# 1. VALIDATE CONFIG FILE
# =========================================================================================
echo "[1/6] Validating configuration file..."
if [ ! -f "$CONFIG_PATH" ]; then
    echo "❌ Error: Configuration file not found at: $CONFIG_PATH"
    exit 1
fi
echo "✅ Config file found: $CONFIG_PATH"
echo ""

echo "   Running config validation..."
python3 "$SCRIPT_DIR/validate_config.py" --config "$CONFIG_PATH"
if [ $? -ne 0 ]; then
    echo "❌ Fix the config errors above before re-running."
    exit 1
fi
echo "✅ Config validation passed."
echo ""

# =========================================================================================
# 2. CHECK GOOGLE CLOUD AUTHENTICATION
# =========================================================================================
echo "[2/6] Checking Google Cloud Application Default Credentials (ADC)..."
if ! gcloud auth application-default print-access-token > /dev/null 2>&1; then
    echo "❌ Error: Google Cloud Application Default Credentials not found."
    echo "👉 Please run: gcloud auth application-default login"
    exit 1
fi
echo "✅ GCP ADC Verified."
echo ""

# =========================================================================================
# 3. INSTALL UV (PYTHON PACKAGE MANAGER)
# =========================================================================================
echo "[3/6] Checking for 'uv' (Python package manager)..."
if ! command -v uv &> /dev/null; then
    echo "📦 'uv' not found. Installing astral-sh/uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to current session PATH
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    # Verify installation
    if ! command -v uv &> /dev/null; then
        echo "❌ Failed to install uv. Please install manually from https://astral.sh/uv"
        exit 1
    fi
fi
echo "✅ uv is installed."
echo ""

# =========================================================================================
# 4. SETUP ISOLATED PYTHON ENVIRONMENT
# =========================================================================================
echo "[4/6] Setting up Python 3.12 environment..."

# Navigate to project root for consistent environment location
cd "$PROJECT_ROOT"

# Create or reuse .venv (uv is smart - instant if exists with correct Python version)
echo "   Creating/verifying virtual environment..."
if [ ! -d ".venv" ]; then
    uv venv --python 3.12 --quiet
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create Python virtual environment"
        exit 1
    fi
else
    echo "   Virtual environment already exists, reusing..."
fi

# Install dependencies (uv uses global cache - fast on subsequent runs)
echo "   Installing dependencies..."
uv pip install -r "$REQUIREMENTS_PATH" --quiet

if [ $? -ne 0 ]; then
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

echo "✅ Python environment ready"
echo ""

# =========================================================================================
# 5. SET CHROME USER DATA DIR
# =========================================================================================
echo "[5/6] Setting Chrome user data directory..."
SET_DIR_OUTPUT=$(bash "$SCRIPT_DIR/config_helper.sh" set_user_data_dir --config "$CONFIG_PATH" 2>&1) || {
    echo "❌ Chrome profile setup failed: $SET_DIR_OUTPUT"
    exit 1
}
echo "   $SET_DIR_OUTPUT"
echo "✅ Chrome user data directory configured."
echo ""

# =========================================================================================
# 6. EXECUTE AUTOMATION SCRIPT
# =========================================================================================
echo "[6/6] Executing Looker Studio Automation..."
echo "================================================================================"
echo "🤖 EXECUTING LOOKER STUDIO AUTOMATION"
echo "================================================================================"
echo "Script: $PYTHON_SCRIPT_PATH"
echo "Config: $CONFIG_PATH"
echo ""

# Navigate to project root to ensure .venv is used
cd "$PROJECT_ROOT"

# Increase CDP screenshot timeout (default 15s is too short under Xwayland)
export TIMEOUT_ScreenshotEvent=60

# Run the Python automation script (uv run automatically uses .venv)
uv run python "$PYTHON_SCRIPT_PATH" --config "$CONFIG_PATH"
EXIT_CODE=$?

# =========================================================================================
# 7. REPORT RESULTS
# =========================================================================================
echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo "================================================================================"
    echo "⚠️ AUTOMATION FAILED (Exit Code: $EXIT_CODE)"
    echo "================================================================================"
    exit $EXIT_CODE
else
    echo "================================================================================"
    echo "🎉 LOOKER STUDIO AUTOMATION COMPLETED SUCCESSFULLY!"
    echo "================================================================================"
fi
