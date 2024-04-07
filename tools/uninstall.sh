#!/bin/bash
#
# Author: liquidz00
# GitHub: https://github.com/liquidz00
#
# Removes Patcher directory from $HOME/Patcher (v1.0+) or $HOME/.patcher
#
# Shellcheck disables
#   shellcheck disable=SC2039
#   shellcheck disable=SC2162
#   shellcheck disable=SC2068
#   shellcheck disable=SC2198
#
# This script should be run via curl:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/liquidz00/Patcher/main/uninstaller.sh)"
#
# Parent directory array (accounts for v0 of Patcher)
PARENTS=()

# Add Patcher directories to array if they exist
if [ -d "$HOME/Patcher" ]; then
    PARENTS+=("$HOME/Patcher")
fi

if [ -d "$HOME/.patcher" ]; then
    PARENTS+=("$HOME/.patcher")
fi

# Remove directory function
remove_directory() {
    local dir=$1
    if [ -n "$dir" ] && [ -d "$dir" ]; then
        read -p "Are you sure you want to remove $dir? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            rm -rf "$dir"
            echo "$dir has been removed."
        else
            echo "Removal of $dir canceled."
        fi
    else
        echo "Directory $dir does not exist or variable is unset. Skipping..."
    fi
}

# Iterate over array to remove each directory
for dir in "${PARENTS[@]}"; do
    remove_directory "$dir"
done

if [ ${#PARENTS[@]} -eq 0 ]; then
    echo "No Patcher directories found. Nothing to uninstall."
else
    echo "Patcher uninstalled successfully."
fi

exit 0
