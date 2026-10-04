# Pi operating contract

Pi uses provider `deepseek`, model `deepseek-flash`, and no local fallback.
Both global and project settings select this default. The GLOBAL `deepseek-only`
extension denies other model selections and provider requests without starting a
local runtime. Upstream Pi still contains a provider catalog; it is not routing
policy. Explicitly disabling extensions bypasses this operating contract.

Keep the project Guard byte-for-byte and keep Command Protocol. The protocol
skill is installed globally from `integrations/pi/skills/command-protocol`;
its reference files remain exact copies of the canonical repository documents.
Project prompts add instructions separately from the selected model.

`integrations/pi/manifest.json` declares GLOBAL and PROJECT_LOCAL resources.
`uv run --no-sync python scripts/sync-pi-resources` installs GLOBAL resources
without changing unrelated files. The former local lifecycle is retired from
this manifest and from global extension discovery. Its frozen source and tests
live under `tests/fixtures/retired_pi`, outside autoload.

`scripts/pi-model`, `scripts/pi-local`, and `scripts/challenger` now refuse all
operations. Qwen Code local roles use `scripts/llm`, the sole manager. `scripts/pi.py`
is an inactive experiment. Do not install historical local lifecycle fixtures.
