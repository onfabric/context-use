#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/demo-magic.sh"

DEMO_PROMPT="${GREEN}➜ ${COLOR_RESET}"
TYPE_SPEED=150
ESC_YELLOW=$(printf '\033[0;33m')
ESC_BOLD=$(printf '\033[0;1m')
ESC_RED=$(printf '\033[0;31m')

function comment() {
  echo -en "${DEMO_COMMENT_COLOR}$1${COLOR_RESET}"
  echo ""
}

function pretty() {
  python3 -c "
import sys
from rich.console import Console
from rich.markdown import Markdown
text = sys.stdin.read().strip()
Console().print(Markdown(text))
"
}

QUESTION="What should I focus on learning this month?"
DATA="{\"model\":\"gpt-4o\",\"messages\":[{\"role\":\"system\",\"content\":\"Answer based only on what you know about the user. If you have no context about them, say so honestly in one sentence.\"},{\"role\":\"user\",\"content\":\"$QUESTION\"}]}"

OPENAI_API_KEY=$(python3 -c "
import tomllib, pathlib
p = pathlib.Path.home() / '.config' / 'context-use' / 'config.toml'
print(tomllib.load(open(p, 'rb'))['openai']['api_key'])
")

DISPLAY_CMD="curl -s ${ESC_RED}https://api.openai.com${ESC_BOLD}/v1/chat/completions \\
  -H \"Authorization: Bearer \$OPENAI_API_KEY\" \\
  -H \"Content-Type: application/json\" \\
  -d '{
    \"model\": \"gpt-4o\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": \"${ESC_YELLOW}$QUESTION${ESC_BOLD}\"
    }]
  }'"

clear
comment "# Direct call to OpenAI"
comment "# — the model knows nothing about you"
echo
p "$DISPLAY_CMD"
echo
run_cmd "curl -s https://api.openai.com/v1/chat/completions \
  -H \"Authorization: Bearer $OPENAI_API_KEY\" \
  -H \"Content-Type: application/json\" \
  -d '$DATA' | jq -r '.choices[0].message.content' | pretty"
echo
comment "# Generic. Could be anyone. 👎"
echo
printf "$DEMO_PROMPT"
wait
