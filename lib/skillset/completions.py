"""Emit native shell completion scripts for skillset."""

import sys


COMMANDS = "init create use rename remove list current show doctor skills completions"

BASH = rf"""_skillset_names() {{
    local output line
    output="$(command skillset list 2>/dev/null)" || return 0
    while IFS= read -r line; do
        printf '%s\n' "${{line#\* }}"
    done <<< "$output"
}}

_skillset_positional_count() {{
    local index token skip=0 after_options=0 count=0
    for ((index = 2; index < COMP_CWORD; index++)); do
        token="${{COMP_WORDS[index]}}"
        if (( skip )); then ((skip--)); continue; fi
        if (( after_options )); then ((count++)); continue; fi
        case "$token" in
            --) after_options=1 ;;
            -f) skip=1 ;;
            --from)
                if [[ "${{COMP_WORDS[index+1]}}" == = ]]; then skip=2; else skip=1; fi
                ;;
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
    local current="${{2-${{COMP_WORDS[COMP_CWORD]}}}}"
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
            if (( ! after_terminator && COMP_CWORD >= 2 )) &&
                    [[ "$previous" == = && "${{COMP_WORDS[COMP_CWORD-2]}}" == --from ]]; then
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

ZSH = r"""#compdef skillset
if (( ! $+functions[compdef] )); then
    autoload -Uz compinit && compinit
fi

_skillset_names() {
    local output line
    output="$(command skillset list 2>/dev/null)" || return 0
    while IFS= read -r line; do
        print -r -- "${line#\* }"
    done <<< "$output"
}

_skillset() {
    local context state state_descr line
    typeset -A opt_args
    _arguments -S -C \
        -A "-*" \
        '(-h --help)'{-h,--help}'[show help]' \
        '1:command:->command' \
        '*::argument:->arguments' && return 0

    case "$state" in
        command)
            local -a commands
            commands=(
                'init:adopt existing global skills'
                'create:create a skillset'
                'use:activate a skillset'
                'rename:rename a skillset'
                'remove:remove an inactive skillset'
                'list:list managed skillsets'
                'current:print the active skillset name'
                'show:show skills in a skillset'
                'doctor:diagnose the managed layout'
                'skills:run managed upstream skills'
                'completions:emit a shell completion script'
            )
            _describe 'skillset command' commands
            ;;
        arguments)
            case "${words[1]}" in
                init)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:name:' && return 0
                    ;;
                create)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '(-f --from)'{-f,--from=}'[clone from an existing skillset]:source skillset:->skillsets' \
                        '--use[activate the created skillset]' \
                        '1:name:' && return 0
                    ;;
                use)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:name:->skillsets' && return 0
                    ;;
                rename)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '1:old name:->skillsets' '2:new name:' && return 0
                    ;;
                remove)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '--yes[skip confirmation]' '1:name:->skillsets' && return 0
                    ;;
                list)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '(-v --verbose)'{-v,--verbose}'[show skill inventory]' && return 0
                    ;;
                current|doctor)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' && return 0
                    ;;
                show)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1::name:->skillsets' && return 0
                    ;;
                completions)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:shell:(bash zsh fish)' && return 0
                    ;;
                skills) return 0 ;;
            esac
            if [[ "$state" == skillsets ]]; then
                local -a names
                names=("${(@f)$(_skillset_names)}")
                (( ${#names} )) && _describe 'skillset' names
            fi
            ;;
    esac
}

if [[ "${zsh_eval_context[-1]}" == loadautofunc ]]; then
    _skillset "$@"
else
    compdef _skillset skillset
fi
"""

FISH = """function __skillset_names
    set -l output (command skillset list 2>/dev/null)
    set -l list_status $status
    test $list_status -eq 0; or return 0
    test (count $output) -gt 0; or return 0
    string replace -r '^\\* ' '' $output
end

function __skillset_needs_command
    set -l tokens (commandline -xpc)
    test (count $tokens) -eq 1
end

function __skillset_using_command
    set -l tokens (commandline -xpc)
    test (count $tokens) -ge 2; and test $tokens[2] = $argv[1]
end

function __skillset_positional_count
    set -l tokens (commandline -xpc)
    set -e tokens[1..2]
    set -l count 0
    set -l skip false
    set -l after_options false
    for token in $tokens
        if test $skip = true
            set skip false
            continue
        end
        if test $after_options = true
            set count (math $count + 1)
            continue
        end
        switch $token
            case --
                set after_options true
            case -f --from
                set skip true
            case '--from=*' -h --help --use --yes -v --verbose '-*'
            case '*'
                set count (math $count + 1)
        end
    end
    echo $count
end

function __skillset_at_position
    test (__skillset_positional_count) -eq $argv[1]
end

complete -c skillset -f
complete -c skillset -n __skillset_needs_command -s h -l help -d 'Show help'
complete -c skillset -n __skillset_needs_command -a init -d 'Adopt existing global skills'
complete -c skillset -n __skillset_needs_command -a create -d 'Create a skillset'
complete -c skillset -n __skillset_needs_command -a use -d 'Activate a skillset'
complete -c skillset -n __skillset_needs_command -a rename -d 'Rename a skillset'
complete -c skillset -n __skillset_needs_command -a remove -d 'Remove an inactive skillset'
complete -c skillset -n __skillset_needs_command -a list -d 'List managed skillsets'
complete -c skillset -n __skillset_needs_command -a current -d 'Print the active skillset name'
complete -c skillset -n __skillset_needs_command -a show -d 'Show skills in a skillset'
complete -c skillset -n __skillset_needs_command -a doctor -d 'Diagnose the managed layout'
complete -c skillset -n __skillset_needs_command -a skills -d 'Run managed upstream skills'
complete -c skillset -n __skillset_needs_command -a completions -d 'Emit a shell completion script'

for subcommand in init create use rename remove list current show doctor completions
    complete -c skillset -n "__skillset_using_command $subcommand" -s h -l help -d 'Show help'
end
complete -c skillset -n '__skillset_using_command create' -s f -l from -x -a '(__skillset_names)' -d 'Clone from a skillset'
complete -c skillset -n '__skillset_using_command create' -l use -d 'Activate the created skillset'
complete -c skillset -n '__skillset_using_command use; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command rename; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command remove; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command remove' -l yes -d 'Skip confirmation'
complete -c skillset -n '__skillset_using_command list' -s v -l verbose -d 'Show skill inventory'
complete -c skillset -n '__skillset_using_command show; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command completions; and __skillset_at_position 0' -a 'bash zsh fish'
"""

SCRIPTS = {"bash": BASH, "zsh": ZSH, "fish": FISH}


def emit_completions(shell, output=None):
    output = sys.stdout if output is None else output
    output.write(SCRIPTS[shell])
