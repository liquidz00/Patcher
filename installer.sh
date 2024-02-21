#!/bin/bash
# shellcheck disable=SC2129

echo "Starting installation..."

# Prompt for Jamf instance details, write to .env
read -pr "Enter the URL of your Jamf instance: " jamf_url
read -pr "Enter your client_id: " client_id
read -pr "Enter your client secret: " client_secret
read -pr "Enter your token: " token

# Create .env if it does not exist already
if [ ! -f ".env" ]; then
  touch ".env"
fi

# Write details to .env
echo "URL=${jamf_url}" > .env
echo "CLIENT_ID=${client_id}" >> .env
echo "CLIENT_SECRET=${client_secret}" >> .env
echo "TOKEN=${token}" >> .env

echo "Jamf instance details saved to .env file."

# Install project dependencies
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
  echo "Dependencies installed."
else
  echo "requirements.txt not found. Skipping dependency installation."
fi

# Update UI configurations in ui_config.py
read -pr "Enter the header text you would like to use: " header_text
read -pr "Enter the footer text you would like to use: " footer_text

# Ensure ui_config.py exists. If not, create with default values
if [ -f "ui_config.py" ]; then
  echo "Creating default ui_config.py..."
  cat > ui_config.py << EOF
# ui_config.py
import os

BASE = os.path.abspath(os.path.dirname(__file__))
FONTS = os.path.join(BASE, "fonts")

# Default UI Configurations
HEADER_TEXT = "$header_text"
FOOTER_TEXT = "$footer_text"
FONT_NAME = "Assistant"
FONT_REGULAR_PATH = os.path.join(FONTS, "Assistant-Regular.ttf")
FONT_BOLD_PATH = os.path.join(FONTS, "Assistant-Bold.ttf")
EOF
else
  # Update existing ui_config.py with the new values
  echo "Updating ui_config.py with new UI configurations..."
  sed -i '' "s/^HEADER_TEXT = .*/HEADER_TEXT = \"$header_text\"/" ui_config.py
  sed -i '' "s/^FOOTER_TEXT = .*/FOOTER_TEXT = \"$footer_text\"/" ui-config.py
fi

echo "UI configurations updated as expected."
