"""Emit native shell completion scripts for skillset."""

import sys


COMMANDS = "init create use rename remove list current show doctor skills completions"

BASH = rf"""_skillset_names() {{
    local line
    while IFS= read -r line; do
        printf '%s\n' "${{line#\* }}"
    done < <(command skillset list 2>/dev/null)
}}

_skillset_positional_count() {{
    local index token skip=0 after_options=0 count=0
    for ((index = 2; index < COMP_CWORD; index++)); do
        token="${{COMP_WORDS[index]}}"
        if (( skip )); then skip=0; continue; fi
        if (( after_options )); then ((count++)); continue; fi
        case "$token" in
            --) after_options=1 ;;
            -f|--from) skip=1 ;;
            --from=*) ;;
            -h|--help|--use|--yes|-v|--verbose) ;;
            -*) ;;
            *) ((count++)) ;;
        esac
    done
    printf '%s' "$count"
}}

_skillset_after_option_terminator() {{
    local index
    for ((index = 2; index < COMP_CWORD; index++)); do
        [[ "${{COMP_WORDS[index]}}" == -- ]] && return 0
    done
    return 1
}}

_skillset_completion() {{
    local current="${{COMP_WORDS[COMP_CWORD]}}"
    local previous="${{COMP_WORDS[COMP_CWORD-1]}}"
    local subcommand position candidates value after_terminator=0
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        COMPREPLY=( $(compgen -W '-h --help {COMMANDS}' -- "$current") )
        return
    fi
    subcommand="${{COMP_WORDS[1]}}"
    position="$(_skillset_positional_count)"
    if _skillset_after_option_terminator; then after_terminator=1; fi
    case "$subcommand" in
        create)
            if (( ! after_terminator )) && [[ "$previous" == -f || "$previous" == --from ]]; then
                COMPREPLY=( $(compgen -W "$(_skillset_names)" -- "$current") )
                return
            fi
            if (( ! after_terminator )) && [[ "$current" == --from=* ]]; then
                value="${{current#--from=}}"
                COMPREPLY=( $(compgen -W "$(_skillset_names)" -- "$value") )
                COMPREPLY=( "${{COMPREPLY[@]/#/--from=}}" )
                return
            fi
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help -f --from --use'; fi
            ;;
        use|remove|show)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( ! after_terminator )) && [[ "$subcommand" == remove ]]; then candidates+=' --yes'; fi
            if (( position == 0 )); then candidates+=" $(_skillset_names)"; fi
            ;;
        rename)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( position == 0 )); then candidates+=" $(_skillset_names)"; fi
            ;;
        list)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help -v --verbose'; fi
            ;;
        completions)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( position == 0 )); then candidates+=' bash zsh fish'; fi
            ;;
        init|current|doctor)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            ;;
        skills) return ;;
        *) return ;;
    esac
    COMPREPLY=( $(compgen -W "$candidates" -- "$current") )
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
