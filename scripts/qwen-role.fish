# Qwen role wrappers read local routes from the manifest-backed llm projection.
function __qwen_profile_run --argument-names role agent
    set -l qwen_args $argv[3..-1]
    for arg in $qwen_args
        if string match -qr -- '^(-m|--model|--auth-?type|--openai|--fallback-?model|--advisor|--system-?prompt|--append-?system-?prompt|--bare|--safe-?mode|--resume|--continue|-r|-c|--worktree|--acp)' (string lower -- "$arg")
            echo 'Qwen refused: argument overrides the local role contract' >&2
            return 2
        end
    end

    set -l neuralengine_root $NEURALENGINE_ROOT
    if test -z "$neuralengine_root"
        set neuralengine_root /home/grzanka/Work/NeuralEngine
    end
    set -l llm_launcher $NEURALENGINE_LLM
    if test -z "$llm_launcher"
        set llm_launcher "$neuralengine_root/scripts/llm"
    end
    set -l projection ($llm_launcher project --role "$role" 2>&1)
    set -l projection_status $status
    if test $projection_status -ne 0
        string join \n -- $projection >&2
        return $projection_status
    end
    set -l model_id (string collect -- (printf '%s\n' "$projection" | jq -er '.model_id'))
    set -l endpoint (string collect -- (printf '%s\n' "$projection" | jq -er '.endpoint'))
    set -l max_output_tokens (string collect -- (printf '%s\n' "$projection" | jq -er '.max_output_tokens'))
    if test -z "$model_id"; or test -z "$endpoint"; or test -z "$max_output_tokens"
        echo 'Qwen refused: manifest route projection was incomplete' >&2
        return 1
    end

    set -l agent_path "$neuralengine_root/.qwen/agents/$agent.md"
    if not test -f "$agent_path"
        echo 'Qwen refused: role instruction file unavailable' >&2
        return 2
    end
    set -l role_file (string collect < "$agent_path")
    set -l role_instructions (string replace -r -- '(?s)^---\n.*?\n---\n\s*' '' "$role_file")
    set -lx QWEN_LOCAL_API_KEY not-needed
    set -lx QWEN_CODE_MAX_OUTPUT_TOKENS $max_output_tokens
    /home/grzanka/.local/bin/qwen --auth-type openai --model "$model_id" --openai-base-url "$endpoint" --advisor off --append-system-prompt "$role_instructions" --approval-mode default --max-subagent-depth 1 $qwen_args
end

function qg --description 'Qwen current LOCAL_GENERAL compatibility projection'
    __qwen_profile_run LOCAL_GENERAL general $argv
end
function qc --description 'Qwen current LOCAL_CODE compatibility projection'
    __qwen_profile_run LOCAL_CODE coder $argv
end
function qv --description 'Qwen current LOCAL_VISION compatibility projection'
    __qwen_profile_run LOCAL_VISION vision $argv
end
