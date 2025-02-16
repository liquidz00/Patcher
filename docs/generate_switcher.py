import json
import os
import subprocess
from pathlib import Path
from src.patcher.__about__ import __version__

def get_tags():
    try:
        tags = subprocess.check_output(["git", "tag"], text=True).splitlines()
        valid_tags = [tag for tag in tags if tag.startswith("v1.4.") or tag.startswith("v2.")]
        return sorted(valid_tags, reverse=True)
    except subprocess.CalledProcessError:
        return []

tags = get_tags()
versions = [
    {"name": "Stable (latest)", "version": "latest", "url": "https://patcher.liquidzoo.io/latest/"},
    {"name": "Develop", "version": "develop", "url": "https://patcher.liquidzoo.io/develop/"},
]

for tag in tags:
    versions.append({"name": tag, "version": tag, "url": f"https://patcher.liquidzoo.io/{tag}/"})

output_path = Path("docs/latest/_static/switcher.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "w") as f:
    json.dump(versions, f, indent=4)

print(f"✅ switcher.json saved to {output_path}")