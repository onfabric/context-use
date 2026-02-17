# /// script
# requires-python = ">=3.12"
# dependencies = ["contextuse[disk]"]
# [tool.uv.sources]
# contextuse = { path = ".", editable = true }
# ///

"""Quick start demo for contextuse.

Usage:
    uv run quickstart.py ~/downloads/chatgpt-export.zip
    uv run quickstart.py ~/downloads/chatgpt-export.zip ~/downloads/instagram-export.zip
"""

import sys

from contextuse import ContextUse
from contextuse.providers.registry import Provider

if len(sys.argv) < 2:
    print("Usage: uv run quickstart.py <chatgpt-export.zip> [instagram-export.zip]")
    sys.exit(1)

ctx = ContextUse.from_config(
    {
        "storage": {"provider": "disk", "config": {"base_path": "./data"}},
        "db": {"provider": "sqlite", "config": {"path": "./contextuse.db"}},
    }
)

# --- ChatGPT ---
chatgpt_path = sys.argv[1]
print(f"Processing ChatGPT archive: {chatgpt_path}")
result = ctx.process_archive(Provider.CHATGPT, chatgpt_path)
print(
    f"  ChatGPT: {result.threads_created} threads from "
    f"{result.tasks_completed} tasks"
)
if result.errors:
    print(f"  Errors: {result.errors}")

# --- Instagram (optional) ---
if len(sys.argv) > 2:
    instagram_path = sys.argv[2]
    print(f"\nProcessing Instagram archive: {instagram_path}")
    result = ctx.process_archive(Provider.INSTAGRAM, instagram_path)
    print(
        f"  Instagram: {result.threads_created} threads from "
        f"{result.tasks_completed} tasks"
    )
    if result.errors:
        print(f"  Errors: {result.errors}")

print("\nDone! Data stored in ./contextuse.db and ./data/")

