#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/demo-magic.sh"

DEMO_PROMPT="${GREEN}➜ ${COLOR_RESET}"
TYPE_SPEED=150
ESC_YELLOW=$(printf '\033[0;33m')
ESC_BOLD=$(printf '\033[0;1m')
ESC_GREEN=$(printf '\033[0;32m')

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

DISPLAY_CMD="curl -s ${ESC_GREEN}http://localhost:8080${ESC_BOLD}/v1/chat/completions \\
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
comment "# Same call, routed through context-use"
comment "# — your memories injected automatically"
echo
pe "context-use proxy --background"
PROXY_PID=$(cat "$HOME/.config/context-use/proxy.pid" 2>/dev/null)
trap 'kill $PROXY_PID 2>/dev/null || true' EXIT
until curl -s http://localhost:8080/health > /dev/null 2>&1; do sleep 0.3; done
p "$DISPLAY_CMD"
echo
run_cmd "curl -s http://localhost:8080/v1/chat/completions \
  -H \"Authorization: Bearer $OPENAI_API_KEY\" \
  -H \"Content-Type: application/json\" \
  -d '$DATA' | jq -r '.choices[0].message.content' | pretty"
echo
comment "# Personal. Just for you. 👍"
echo
printf "$DEMO_PROMPT"
wait
