# Qwen role wrappers; scripts/llm owns every local runtime transition.
function __qwen_profile_run --argument-names profile model port agent
    set -l qwen_args $argv[5..-1]
    for arg in $qwen_args
        if string match -qr -- '^(-m|--model|--auth-?type|--openai|--fallback-?model|--advisor|--system-?prompt|--append-?system-?prompt|--bare|--safe-?mode|--resume|--continue|-r|-c|--worktree|--acp)' (string lower -- "$arg")
            echo 'Qwen refused: argument overrides the local role contract' >&2
            return 2
        end
    end
    set -l agent_path /home/grzanka/Work/NeuralEngine/.qwen/agents/$agent.md
    if not test -f "$agent_path"
        echo 'Qwen refused: role instruction file unavailable' >&2
        return 2
    end
    set -l role_file (string collect < "$agent_path")
    set -l role_instructions (string replace -r -- '(?s)^---\n.*?\n---\n\s*' '' "$role_file")
    set -l start_output (/home/grzanka/.local/bin/llm start (string lower -- "$profile") 2>&1)
    set -l start_status $status
    if test $start_status -ne 0
        string join \n -- $start_output >&2
        return $start_status
    end
    set -l owns_runtime false
    set -l owned_pid
    if string match -q -- "$profile STARTED BY THIS INVOCATION" $start_output
        set owned_pid (string match -r --groups-only -- "ownership: $profile pid=([1-9][0-9]*)" $start_output)
        if test (count $owned_pid) -ne 1
            echo 'Qwen refused: llm did not prove one exact owned PID' >&2
            return 1
        end
        set owns_runtime true
    else if not string match -q -- "$profile ALREADY READY" $start_output
        echo 'Qwen refused: llm did not prove started or borrowed runtime' >&2
        return 1
    end
    string join \n -- $start_output
    set -lx QWEN_LOCAL_API_KEY not-needed
    /home/grzanka/.local/bin/qwen --auth-type openai --model "$model" --openai-base-url "http://127.0.0.1:$port/v1" --advisor off --append-system-prompt "$role_instructions" --approval-mode default --max-subagent-depth 1 $qwen_args
    set -l qwen_status $status
    if test "$owns_runtime" = true
        /home/grzanka/.local/bin/llm stop --expected-profile "$profile" --expected-pid "$owned_pid[1]"
        if test $status -ne 0
            echo "Qwen exited, but guarded stop failed for owned $profile PID" >&2
            return 1
        end
    end
    return $qwen_status
end

function qg --description 'Local GENERAL Nemotron with role instruction binding'
    __qwen_profile_run GENERAL /models/gguf/nemotron-3-nano-30b-a3b/nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf 18081 general $argv
end
function qc --description 'Local CODE Qwen3-Coder with role instruction binding'
    __qwen_profile_run CODE /models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf 18080 coder $argv
end
function qv --description 'Local VISION Gemma with mmproj and role instruction binding'
    __qwen_profile_run VISION /models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf 18082 vision $argv
end
