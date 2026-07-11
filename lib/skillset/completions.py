"""Emit native shell completion scripts for skillset."""

import sys


COMMANDS = "init create use rename remove list current show doctor skills completions"

BASH = rf"""_skillset_completion() {{
    local current="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        COMPREPLY=( $(compgen -W '-h --help {COMMANDS}' -- "$current") )
    fi
}}
complete -F _skillset_completion skillset
"""

ZSH = rf"""#compdef skillset
if (( ! $+functions[compdef] )); then
    autoload -Uz compinit && compinit
fi
_skillset() {{
    local -a commands
    commands=({COMMANDS})
    if (( CURRENT == 2 )); then
        _describe 'skillset command' commands
    fi
}}
compdef _skillset skillset
"""

FISH = """function __skillset_needs_command
    set -l tokens (commandline -opc)
    test (count $tokens) -eq 1
end
complete -c skillset -f
complete -c skillset -n __skillset_needs_command -s h -l help -d 'Show help'
complete -c skillset -n __skillset_needs_command -a 'init create use rename remove list current show doctor skills completions'
"""

SCRIPTS = {"bash": BASH, "zsh": ZSH, "fish": FISH}


def emit_completions(shell, output=None):
    output = sys.stdout if output is None else output
    output.write(SCRIPTS[shell])
