#!/bin/bash
#
# Author: liquidz00
# GitHub: https://github.com/liquidz00
#
# Formatting and tty from ohmyzsh installer: https://github.com/ohmyzsh/ohmyzsh/blob/master/tools/install.sh
#
# Shellcheck disables
#   shellcheck disable=SC2129
#   shellcheck disable=SC2162
#   shellcheck disable=SC2155
#   shellcheck disable=SC2016
#   shellcheck disable=SC2183
#
# This script should be run via curl:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/liquidz00/Patcher/main/installer.sh)"
#
# Alternatively, the script can be downloaded first and run afterwards:
#   curl -O https://raw.githubusercontent.com/liquidz00/Patcher/main/installer.sh && bash ./installer.sh
#
# Default repo settings
REPO=${REPO:-liquidz00/Patcher}
REMOTE=${REMOTE:-https://github.com/${REPO}.git}
BRANCH=${BRANCH:-main}

# Directories & files
PARENT="$HOME/.patcher"
LOG_DIR="$HOME/.patcher/logs"
LOG_FILE="$LOG_DIR/installer.log"

# Command checks
command_exists() {
  command -v "$@" >/dev/null 2>&1
}

# Create log directory
if [ -n "$LOG_DIR" ]; then
  mkdir -p "$LOG_DIR"
fi

# tty check (from ohmyzsh/ohmyzsh)
# The [ -t 1 ] check only works when the function is not called from
# a subshell (like in `$(...)` or `(...)`, so this hack redefines the
# function at the top level to always return false when stdout is not
# a tty.
if [ -t 1 ]; then
  is_tty() {
    true
  }
else
  is_tty() {
    false
  }
fi

# This function uses the logic from supports-hyperlinks[1][2], which is
# made by Kat Marchán (@zkat) and licensed under the Apache License 2.0.
# [1] https://github.com/zkat/supports-hyperlinks
# [2] https://crates.io/crates/supports-hyperlinks
#
# Copyright (c) 2021 Kat Marchán
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
supports_hyperlinks() {
  # $FORCE_HYPERLINK must be set and be non-zero (this acts as a logic bypass)
  if [ -n "$FORCE_HYPERLINK" ]; then
    [ "$FORCE_HYPERLINK" != 0 ]
    return $?
  fi

  # If stdout is not a tty, it doesn't support hyperlinks
  is_tty || return 1

  # DomTerm terminal emulator (domterm.org)
  if [ -n "$DOMTERM" ]; then
    return 0
  fi

  # VTE-based terminals above v0.50 (Gnome Terminal, Guake, ROXTerm, etc)
  if [ -n "$VTE_VERSION" ]; then
    [ $VTE_VERSION -ge 5000 ]
    return $?
  fi

  # If $TERM_PROGRAM is set, these terminals support hyperlinks
  case "$TERM_PROGRAM" in
    Hyper|iTerm.app|terminology|WezTerm|vscode) return 0 ;;
  esac

  # These termcap entries support hyperlinks
  case "$TERM" in
    xterm-kitty|alacritty|alacritty-direct) return 0 ;;
  esac

  # xfce4-terminal supports hyperlinks
  if [ "$COLORTERM" = "xfce4-terminal" ]; then
    return 0
  fi

  # Windows Terminal also supports hyperlinks
  if [ -n "$WT_SESSION" ]; then
    return 0
  fi

  # Konsole supports hyperlinks, but it's an opt-in setting that can't be detected
  # https://github.com/ohmyzsh/ohmyzsh/issues/10964
  # if [ -n "$KONSOLE_VERSION" ]; then
  #   return 0
  # fi

  return 1
}

# Adapted from code and information by Anton Kochkov (@XVilka)
# Source: https://gist.github.com/XVilka/8346728
supports_truecolor() {
  case "$COLORTERM" in
    truecolor|24bit) return 0 ;;
  esac

  case "$TERM" in
    iterm           |\
    tmux-truecolor  |\
    linux-truecolor |\
    xterm-truecolor |\
    screen-truecolor) return 0 ;;
  esac

  return 1
}

fmt_link() {
  # $1: text, $2: url, $3: fallback mode
  if supports_hyperlinks; then
    printf '\033]8;;%s\033\\%s\033]8;;\033\\\n' "$2" "$1"
    return
  fi

  case "$3" in
    --text) printf '%s\n' "$1" ;;
    --url|*) fmt_underline "$2" ;;
  esac
}

fmt_underline() {
  is_tty && printf '\033[4m%s\033[24m\n' "$*" || printf '%s\n' "$*"
}

fmt_code() {
  is_tty && printf '`\033[2m%s\033[22m`\n' "$*" || printf '`%s`\n' "$*"
}

fmt_error() {
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  printf '%s ERROR: %s%s\n' "${FMT_BOLD}${FMT_RED}" "$timestamp" "$message" "$FMT_RESET" >&2
  echo "$timestamp - ERROR - $message" >> "$LOG_FILE"
}

fmt_warning() {
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  printf '%s WARNING: %s%s\n' "${FMT_BOLD}${FMT_YELLOW}" "$timestamp" "$message" "$FMT_RESET" >&2
  echo "$timestamp - WARNING - $message" >> "$LOG_FILE"
}

fmt_info() {
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  printf '%s INFO: %s%s\n' "${FMT_BOLD}${FMT_YELLOW}" "$timestamp" "$message" "$FMT_RESET" >&2
  echo "$timestamp - INFO - $message" >> "$LOG_FILE"
}

setup_color() {
  # Colors should only be used if connected to a terminal (tty)
  if ! is_tty; then
    FMT_RAINBOW=""
    FMT_RED=""
    FMT_GREEN=""
    FMT_YELLOW=""
    FMT_BLUE=""
    FMT_BOLD=""
    FMT_RESET=""
    return
  fi

  if supports_truecolor; then
    FMT_RAINBOW="
      $(printf '\033[38;2;255;0;0m')
      $(printf '\033[38;2;255;97;0m')
      $(printf '\033[38;2;247;255;0m')
      $(printf '\033[38;2;0;255;30m')
      $(printf '\033[38;2;77;0;255m')
      $(printf '\033[38;2;168;0;255m')
      $(printf '\033[38;2;245;0;172m')
    "
  else
    FMT_RAINBOW="
      $(printf '\033[38;5;196m')
      $(printf '\033[38;5;202m')
      $(printf '\033[38;5;226m')
      $(printf '\033[38;5;082m')
      $(printf '\033[38;5;021m')
      $(printf '\033[38;5;093m')
      $(printf '\033[38;5;163m')
    "
  fi

  FMT_RED=$(printf '\033[31m')
  FMT_GREEN=$(printf '\033[32m')
  FMT_YELLOW=$(printf '\033[33m')
  FMT_BLUE=$(printf '\033[34m')
  FMT_BOLD=$(printf '\033[1m')
  FMT_RESET=$(printf '\033[0m')
}

setup_patcher() {
  echo "${FMT_BLUE}Starting installation...${FMT_RESET}"
  echo "Starting installation..." >> "$LOG_FILE"

  # Manually clone with git config options (for git versions < v1.7.2)
  git init --quiet "$PARENT" && cd "$PARENT" \
  && git config core.eol lf \
  && git config core.autocrlf false \
  && git config fsck.zeroPaddedFilemode ignore \
  && git config fetch.fsck.zeroPaddedFilemode ignore \
  && git config receive.fsck.zeroPaddedFilemode ignore \
  && git config Patcher.remote origin \
  && git config Patcher.branch "$BRANCH" \
  && git remote add origin "$REMOTE" \
  && git fetch --depth=1 origin \
  && git checkout -b "$BRANCH" "origin/$BRANCH" || {
    [ ! -d "$PARENT" ] || {
      cd .. || exit
      rm -rf "$PARENT" 2>/dev/null
    }
    fmt_error "git clone of Patcher repo failed"
    exit 1
  }
}

setup_environment() {
  fmt_info "Setting up environment..."
  cd "$PARENT" || exit

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
      fmt_error "Failed to generate a token. Please check your Jamf instance details."
      exit 1
    fi
  fi

  # If .env file exists, ask user if they want to overwrite
  if [ -f ".env" ]; then
    read -p "An .env file already exists in this location...Overwrite? (y/n): " env_exists
    if [[ "$env_exists" =~ ^[Yy]$ ]]; then
      # Write details to .env
      echo "URL=${jamf_url}" > .env
      echo "CLIENT_ID=${client_id}" >> .env
      echo "CLIENT_SECRET=${client_secret}" >> .env
      echo "TOKEN=${token}" >> .env
      fmt_info "User chose to overwrite contents of .env file."
    elif [[ "$env_exists" =~ ^[Nn]$ ]]; then
      fmt_error "User chose not to overwrite existing .env file."
      exit 1
    fi
  else
    # Write details to .env
    echo "URL=${jamf_url}" > .env
    echo "CLIENT_ID=${client_id}" >> .env
    echo "CLIENT_SECRET=${client_secret}" >> .env
    echo "TOKEN=${token}" >> .env
    fmt_info "Jamf instance details saved to .env file."
  fi

  # Install project dependencies
  if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt
    log_message "Dependencies installed." "INFO"
  else
    log_message "requirements.txt not found. Skipping dependency installation." "WARNING"
  fi

  local target="$PARENT/patcher.py"
  local link="/usr/local/bin/patcher"

  # Ensure script is executable
  chmod +x "$target"

  # Check if symlink exists already
  if [ -e "$link" ] || [ -L "$link" ]; then
    fmt_warning "Symlink $link already exists. Skipping."
  else
    # Create symlink
    if ln -s "$target" "$link"; then
      fmt_info "Symlink created at $link"
    else
      fmt_error "Failed to create symlink at $link"
      exit 1
    fi
  fi
}

setup_ui() {
  fmt_info "Configuring UI elements..."
  cd "$PARENT" || exit
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
    fmt_info "Creating default ui_config.py with user-defined configurations..."
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
    fmt_info "ui_config.py exists. Updating with new UI configurations..."
    # Use -i.bak to make it compatible across GNU and BSD sed, creates a backup file
    sed -i.bak "s/^HEADER_TEXT = .*/HEADER_TEXT = \"$header_text\"/" ui_config.py
    sed -i.bak "s/^FOOTER_TEXT = .*/FOOTER_TEXT = \"$footer_text\"/" ui_config.py
    sed -i.bak "s/^FONT_NAME = .*/FONT_NAME = \"$custom_font\"/" ui_config.py
    sed -i.bak "s/^FONT_REGULAR_PATH = .*/FONT_REGULAR_PATH = os.path.join(FONTS, \"$custom_font_regular_path\")/" ui_config.py
    sed -i.bak "s/^FONT_BOLD_PATH = .*/FONT_BOLD_PATH = os.path.join(FONTS, \"$custom_font_bold_path\")/" ui_config.py

    # Remove backup files created by sed
    rm ui_config.py.bak
  fi

  fmt_info "UI configurations updated as expected."
}

print_success() {
  printf '%s   ___         __        __           %s\n'   $FMT_RAINBOW $FMT_RESET
  printf '%s  / _ \\ ___ _ / /_ ____ / /  ___  ____%s\n'  $FMT_RAINBOW $FMT_RESET
  printf '%s / ___// _ `// __// __// _ \\/ -_)/ __/%s\n'  $FMT_RAINBOW $FMT_RESET
  printf '%s/_/    \\_,_/ \\__/ \\__//_//_/\\__//_/%s\n'  $FMT_RAINBOW $FMT_RESET
  printf '%s                                      %s\n'   $FMT_RAINBOW $FMT_RESET
  printf '\n'
  printf '\n'
  printf "%s %s %s\n" "${FMT_BOLD}${FMT_BLUE}Patcher has finished installing and is ready for use!${FMT_RESET}"
  printf '\n'
  printf "%s %s %s\n" "If you have not already, be sure to check out the project Wiki here $(fmt_link https://github.com/liquidz00/Patcher/wiki) ${FMT_RESET}"
}

main() {
  setup_color

  # Pre-flight checks (Git, python)
  command_exists git || {
    fmt_error "Git is not installed. Please install Git and try again."
    exit 1
  }

  command_exists python3 || {
    fmt_error "Python is not installed. Please install Python and try again."
    exit 1
  }

  setup_patcher
  setup_environment
  setup_ui
  print_success
}

main "$@"
