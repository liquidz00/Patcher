#!/bin/bash
# shellcheck disable=SC2129
# shellcheck disable=SC2162
# shellcheck disable=SC2155

# Logging
LOG_DIR="$HOME/.patcher/logs"
LOG_FILE="$LOG_DIR/installer.log"

log_message() {
  local message="$1"
  local type="$2"  # INFO, WARNING, or ERROR
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  # Log error to logfile
  echo "$timestamp - $type - $message" >> "$LOG_FILE"

  # Echo error to stdout for user visibility
  echo "$timestamp - $type - $message"
}

# Pre-flight checks
# Create log directory
mkdir -p "$LOG_DIR"

# Git
if ! command -v git &> /dev/null
then
  log_message "Git is not installed. Please install Git and try again." "ERROR"
  exit 1
fi

# Python
if ! command -v python3 &> /dev/null
then
  log_message "Python is not installed. Please install Python and try again." "ERROR"
  exit 1
fi

# Clone repo into home directory
PROJECT_DIR="$HOME/patcher"
if [ ! -d "$PROJECT_DIR" ]; then
  log_message "Cloning Patcher repository into $PROJECT_DIR" "INFO"
  git clone https://github.com/liquidz00/patcher.git "$PROJECT_DIR"
else
  log_message "Directory already exists. Pulling latest updates..." "INFO"
  (cd "$PROJECT_DIR" && git pull)
fi

# Change into project directory or exit if error thrown
cd "$PROJECT_DIR" || exit

log_message "Starting installation..." "INFO"

# Prompt for Jamf instance details, write to .env
read -p "Enter the URL of your Jamf instance: " jamf_url
read -p "Enter your client_id: " client_id
read -p "Enter your client secret: " client_secret

# Prompt if user has bearer token already. If not, generate one.
read -p "Do you already have a bearer token? (y/n): " has_token
if [[ "$has_token" =~ ^[Yy]$ ]]; then
  read -p "Enter your token: " token
else
  response=$(curl --silent --location --request POST "${jamf_url}/api/oauth/token" \
		--header "Content-Type: application/x-www-form-urlencoded" \
		--data-urlencode "client_id=${client_id}" \
		--data-urlencode "grant_type=client_credentials" \
		--data-urlencode "client_secret=${client_secret}")
  token=$(echo "$response" | plutil -extract access_token raw -)
  if [ "$token" == "null" ]; then
    log_message "Failed to generate a token. Please check your Jamf instance details." "ERROR"
    exit 1
  fi
fi

# Create .env if it does not exist already
if [ ! -f ".env" ]; then
  touch ".env"
fi

# Write details to .env
echo "URL=${jamf_url}" > .env
echo "CLIENT_ID=${client_id}" >> .env
echo "CLIENT_SECRET=${client_secret}" >> .env
echo "TOKEN=${token}" >> .env

log_message "Jamf instance details saved to .env file." "INFO"

# Install project dependencies
if [ -f "requirements.txt" ]; then
  python3 -m pip install -r requirements.txt
  log_message "Dependencies installed." "INFO"
else
  log_message "requirements.txt not found. Skipping dependency installation." "WARNING"
fi

# Update UI configurations in ui_config.py
read -p "Enter the header text you would like to use: " header_text
read -p "Enter the footer text you would like to use: " footer_text
read -p "Would you like to use a custom font? (y/n): " use_custom_font

custom_font="Assistant"
custom_font_regular_path="Assistant-Regular.ttf"
custom_font_bold_path="Assistant-Bold.ttf"

if [[ "$use_custom_font" =~ ^[Yy]$ ]]; then
  read -p "Enter the custom font name: " custom_font
  read -p "Enter the relative path to the custom font regular file (e.g., fonts/MyCustom-Regular.ttf): " custom_font_regular_path
  read -p "Enter the relative path to the custom font bold file (e.g., fonts/MyCustom-Bold.ttf): " custom_font_bold_path
fi

# Ensure ui_config.py exists. If not, create with default values
if [ -f "ui_config.py" ]; then
  log_message "Creating default ui_config.py with user-defined configurations..." "INFO"
  cat > ui_config.py << EOF
# ui_config.py
import os

BASE = os.path.abspath(os.path.dirname(__file__))
FONTS = os.path.join(BASE, "fonts")

# Default UI Configurations
HEADER_TEXT = "$header_text"
FOOTER_TEXT = "$footer_text"
FONT_NAME = "$custom_font"
FONT_REGULAR_PATH = os.path.join(FONTS, "$custom_font_regular_path")
FONT_BOLD_PATH = os.path.join(FONTS, "$custom_font_bold_path")
EOF
else
  # Update existing ui_config.py with the new values
  log_message "ui_config.py exists. Updating with new UI configurations..." "INFO"
  # Use -i.bak to make it compatible across GNU and BSD sed, creates a backup file
  sed -i.bak "s/^HEADER_TEXT = .*/HEADER_TEXT = \"$header_text\"/" ui_config.py
  sed -i.bak "s/^FOOTER_TEXT = .*/FOOTER_TEXT = \"$footer_text\"/" ui_config.py
  sed -i.bak "s/^FONT_NAME = .*/FONT_NAME = \"$custom_font\"/" ui_config.py
  sed -i.bak "s/^FONT_REGULAR_PATH = .*/FONT_REGULAR_PATH = os.path.join(FONTS, \"$custom_font_regular_path\")/" ui_config.py
  sed -i.bak "s/^FONT_BOLD_PATH = .*/FONT_BOLD_PATH = os.path.join(FONTS, \"$custom_font_bold_path\")/" ui_config.py

  # Remove backup files created by sed
  rm ui_config.py.bak
fi

log_message "UI configurations updated as expected." "INFO"
