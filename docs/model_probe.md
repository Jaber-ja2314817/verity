# Model probe

Run: 2026-10-17 16:34 UTC against `https://api.tokenfactory.nebius.com/v1/`

## NVIDIA / Nemotron models listed by `GET /v1/models`

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- `nvidia/Nemotron-3-Ultra-550b-a55b`
- `nvidia/Nemotron-3.5-Super-VL`
- `nvidia/Nemotron-3_5-Lightning`
- `nvidia/nemotron-3-super-120b-a12b`

## Results

Tokens are input/output. Structured tests ask for a `Verdict` on a tiny claim (expected label: TRUE).

| Model | Plain chat | tool_forced | tool_auto | text_json | `<think>` in content | reasoning_content |
|---|---|---|---|---|---|---|
| `nvidia/Nemotron-3_5-Lightning` | OK: 'OK' (0.5s, 21/85) | OK TRUE (2.4s, 832/244) | OK TRUE (0.5s, 965/79) | OK TRUE (3.8s, 334/880) | no | yes |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | OK: 'OK' (0.6s, 21/15) | OK TRUE (0.7s, 860/133) | OK TRUE (1.1s, 871/189) | OK TRUE (0.9s, 334/239) | no | yes |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | OK: 'OK' (0.6s, 21/40) | OK TRUE (2.6s, 825/387) | OK TRUE (3.1s, 836/583) | OK TRUE (1.9s, 334/285) | no | no |

## Recommendation

```dotenv
MODEL_FAST=nvidia/Nemotron-3_5-Lightning
STRUCTURED_MODE_FAST=tool_forced
MODEL_JUDGE=nvidia/Nemotron-3-Ultra-550b-a55b
STRUCTURED_MODE_JUDGE=tool_forced
```
