# Local Computer Use / GUI Automation Models on Apple Silicon Mac

> Research date: 2026-03-11 | Target: macOS with Apple Silicon (M1/M2/M3/M4 Pro/Max)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Model Comparison Matrix](#model-comparison-matrix)
3. [Detailed Model Profiles](#detailed-model-profiles)
4. [Deployment Infrastructure](#deployment-infrastructure)
5. [Quick-Start Recipes](#quick-start-recipes)
6. [Memory Requirements Reference](#memory-requirements-reference)
7. [Action Output Formats](#action-output-formats)
8. [End-to-End Frameworks](#end-to-end-frameworks)
9. [Integration with UI-TARS Desktop](#integration-with-ui-tars-desktop)
10. [Recommendations](#recommendations)

---

## 1. Executive Summary

### Fastest Path to GUI-Understanding VLM on M1 Pro 16GB

```bash
# Option A: Ollama (easiest, 30 seconds to running)
ollama pull qwen2.5vl:7b        # 6.0 GB download
ollama run qwen2.5vl:7b "describe this screenshot" --images screenshot.png

# Option B: MLX (best Apple Silicon optimization)
pip install mlx-vlm
mlx_vlm.generate --model mlx-community/Qwen2-VL-2B-Instruct-4bit --max-tokens 100 --image screenshot.png

# Option C: Ollama with UI-TARS (purpose-built for GUI automation)
ollama pull 0000/ui-tars-1.5-7b  # GUI-specialized
```

### Best Quality/Speed Tradeoff for GUI Automation

| Priority | Model | Runtime | Why |
|----------|-------|---------|-----|
| Best quality | UI-TARS-7B-DPO (Q4_K_M) | Ollama | Purpose-built for GUI, 18.7% OSWorld (beats Claude CU 14.9%) |
| Best speed | Qwen2.5-VL-3B | Ollama | 3.2 GB, fast inference, decent grounding |
| Best balance | UI-TARS-1.5-7B (Q4_K_M) | Ollama/llama.cpp | Latest version, improved over 1.0 |
| Lightest | ShowUI-2B | transformers | 2B params, MIT license, GUI-specialized |

### Can These Models Output Click Coordinates?

**Yes.** All the GUI-specialized models below can take a screenshot and output structured actions with coordinates:

- **UI-TARS**: `Action: click(start_box='(100,200)')` -- pixel coordinates
- **ShowUI**: `{"action": "CLICK", "position": [0.45, 0.32]}` -- normalized 0-1 coordinates
- **CogAgent**: `CLICK(box=[[352,102,786,139]], element_info='Search')` -- bounding box coordinates
- **Qwen2-VL/2.5-VL**: Can do visual grounding with bounding boxes when prompted appropriately
- **SmolVLM2-Agentic-GUI**: Trained for GUI action output (2.2B, lightweight)

---

## 2. Model Comparison Matrix

### GUI-Specialized Models (purpose-built for Computer Use)

| Model | Params | Base | GUI Grounding | Action Output | GGUF | Ollama | OSWorld Score | License |
|-------|--------|------|---------------|---------------|------|--------|---------------|---------|
| **UI-TARS-7B-DPO** | 7B | Qwen2-VL | 91.6% ScreenSpot v2 | click/type/scroll with pixel coords | Yes (many) | Yes | 18.7% | Apache 2.0 |
| **UI-TARS-1.5-7B** | 7B | Qwen2-VL | Improved | Same as above | Yes (many) | Yes | Improved | Apache 2.0 |
| **UI-TARS-2B-SFT** | 2B | Qwen2-VL | 84.7% ScreenSpot v2 | Same format | Yes | Limited | 17.7% | Apache 2.0 |
| **UI-TARS-72B-DPO** | 72B | Qwen2-VL | Best | Same format | Yes | Yes | 22.7% | Apache 2.0 |
| **CogAgent-9B** | 14B (9B lang + 5B vis) | GLM-4V-9B | Yes | CLICK/TYPE/SCROLL with bbox | No | No | N/A | Custom |
| **ShowUI-2B** | 2B | Qwen2-VL-2B | Yes | JSON with normalized coords | Limited | No | N/A | MIT |
| **SmolVLM2-Agentic-GUI** | 2.2B | SmolLM2 + SigLIP | Trained for GUI | Action format | Yes | No | N/A | Apache 2.0 |

### General VLMs with GUI Capability

| Model | Params | GUI Grounding | GGUF | Ollama | MLX | Notes |
|-------|--------|---------------|------|--------|-----|-------|
| **Qwen2.5-VL-7B** | 7B | Bounding box output | Yes (many) | Yes (1.4M pulls) | Yes | Base model for UI-TARS; visual localization built-in |
| **Qwen2.5-VL-3B** | 3B | Decent | Yes | Yes | Yes | Edge-friendly, outperforms Qwen2-VL-7B |
| **Qwen2.5-VL-32B** | 32B | Strong | Yes | Yes | Possible | Needs 21GB+ RAM |
| **Qwen2-VL-7B** | 7B | Bounding box | Yes | Yes | Yes | Predecessor, still solid |
| **Molmo-7B-D** | 7B | Limited | Yes (7 quants) | Possible | No | General VLM, not GUI-specialized |

---

## 3. Detailed Model Profiles

### 3.1 UI-TARS Family (ByteDance) -- RECOMMENDED for GUI Automation

**Architecture**: End-to-end VLM built on Qwen2-VL, integrating perception, reasoning, grounding, and memory in a single model.

**Key Results (UI-TARS-7B-DPO)**:
- ScreenSpot v2 grounding: **91.6%**
- OSWorld (15 steps): **18.7%** (vs Claude Computer Use 14.9%)
- Multimodal Mind2Web: 73.1% element accuracy, 92.2% operation F1
- AndroidWorld: Tested and benchmarked

**UI-TARS 1.5-7B** (latest):
- Improved over 1.0 across all benchmarks
- GGUF widely available (Q4_K_M, Q6_K, Q8_0 from multiple providers)
- Available on Ollama as `0000/ui-tars-1.5-7b`

**Action Output Format**:
```
Action: click(start_box='(x,y)')
Action: type(content='hello world')
Action: scroll(direction='down', amount=3)
Action: hotkey(key='ctrl+c')
```

Coordinates are pixel-based, relative to screenshot resolution. The `ui-tars` pip package provides parsers:
```python
pip install ui-tars
from ui_tars import parse_action_to_structure_output, parsing_response_to_pyautogui_code
```

**GGUF Versions Available** (UI-TARS-7B-DPO):
| Provider | Quantizations | Downloads |
|----------|---------------|-----------|
| bartowski | Multiple (Q4_K_M through Q8_0) | 901 |
| lmstudio-community | Multiple | 567 |
| mradermacher | Standard + i1 | 283+108 |
| FelisDwan | Q4_K_M | 14 |

**GGUF Versions Available** (UI-TARS-1.5-7B):
| Provider | Quantizations | Downloads |
|----------|---------------|-----------|
| Mungert | Multiple | 3,040 |
| mradermacher | Standard + i1 | 1,620+80 |
| Lucy-in-the-Sky | Q4_K_M, Q6_K, Q8_0 | Various |

### 3.2 Qwen2.5-VL (Alibaba) -- Best General-Purpose VLM

The base model family that UI-TARS is built on. These are general-purpose VLMs that can do GUI understanding with proper prompting, but are not specifically fine-tuned for GUI automation.

**Available on Ollama** (1.4M+ pulls total):
```bash
ollama pull qwen2.5vl:3b    # 3.2 GB -- edge-friendly
ollama pull qwen2.5vl:7b    # 6.0 GB -- sweet spot
ollama pull qwen2.5vl:32b   # 21 GB  -- needs 32GB+ RAM
ollama pull qwen2.5vl:72b   # 49 GB  -- needs 64GB+ RAM
```

**GUI Capabilities**: Built-in visual localization with bounding boxes. Can identify UI elements, read text from screenshots, describe interfaces. For actual GUI automation (outputting click coordinates in a structured format), you need specific prompting or fine-tuning -- this is exactly what UI-TARS adds.

**Key Strength**: 125K token context window, strong document understanding, structured output for invoices/forms.

**MLX Support**: Full support via `mlx-vlm`:
```bash
pip install mlx-vlm
mlx_vlm.generate --model mlx-community/Qwen2-VL-2B-Instruct-4bit --max-tokens 100 --image screenshot.png
```

### 3.3 CogAgent-9B (Tsinghua/Zhipu)

**Architecture**: 14B total (9B language + 5B vision), based on GLM-4V-9B. Specifically designed for GUI agents.

**Action Format**:
```
CLICK(box=[[352,102,786,139]], element_info='Search')    Left click on search box
TYPE(box=[[352,102,786,139]], text='doors', element_info='Search')    Type 'doors'
SCROLL_DOWN(box=[[0,209,998,952]], step_count=5, element_info='[None]')    Scroll down
```

**Memory Requirements**:
- BF16: ~29 GB VRAM
- INT8: ~15 GB VRAM
- INT4: ~8 GB VRAM (quality degradation)

**Mac Support**: Documentation explicitly supports macOS 14/15 with `--platform "Mac"` flag:
```bash
python inference/cli_demo.py --model_dir THUDM/cogagent-9b-20241220 --platform "Mac"
```

**Limitations**:
- No GGUF format available
- Not on Ollama
- INT8 (15GB) is the realistic minimum for M1 Pro 16GB -- tight fit
- Online demo only shows inference results, does not control the computer

### 3.4 ShowUI-2B (Microsoft)

**Architecture**: 2B params, based on Qwen2-VL-2B. Lightweight GUI grounding and navigation model.

**Action Format** (Web):
```json
{
    "action": "CLICK",
    "value": "element_description",
    "position": [0.45, 0.32]
}
```

**Action Format** (Mobile):
```json
{
    "action": "TAP",
    "value": null,
    "position": [0.5, 0.7]
}
```

Coordinates are **normalized 0-1** (relative to screenshot dimensions).

**Supported Actions**: CLICK, INPUT, SELECT, HOVER, SCROLL, SELECT_TEXT, COPY, ENTER, ANSWER (web) / TAP, SWIPE, INPUT, ENTER, ANSWER (mobile)

**Key Feature**: UI-Guided Token Selection -- reduces 1,296 screenshot patches to 167 UI components for efficient processing.

**Deployment**:
```python
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch

model = Qwen2VLForConditionalGeneration.from_pretrained(
    "showlab/ShowUI-2B",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
```

**Mac Viability**: At 2B params with bfloat16, this needs ~4-5 GB RAM. Very feasible on M1 Pro 16GB.

**Integration**: Part of the [Computer Use OOTB](https://github.com/showlab/computer_use_ootb) framework that supports macOS.

### 3.5 SmolVLM2-2.2B-Agentic-GUI (HuggingFace)

**Architecture**: 2.2B params. SmolLM2-1.7B (text) + SigLIP (vision). Fine-tuned on `aguvis-stage-2` dataset for GUI tasks.

**GGUF Available**: Yes, from bartowski and mradermacher.

**Deployment**: Standard transformers pipeline. Very lightweight (~5 GB RAM).

**Caveat**: Relatively new, less battle-tested than UI-TARS. Limited community adoption (231 downloads for GGUF).

### 3.6 SeeClick

**Status**: Original SeeClick is a GUI grounding model, but no standalone GGUF versions found. One derivative exists:
- `mradermacher/EvoCUA-32B-seeclick-ft-GGUF` -- 33B params, too large for 16GB Mac

**Verdict**: Not practical for local Mac deployment.

### 3.7 Molmo-7B-D (AI2)

**Architecture**: 7B params, trained on PixMo (1M image-text pairs). General-purpose VLM.

**GUI Capabilities**: Not specifically trained for GUI automation. Can describe screenshots and understand visual content, but does not natively output structured action commands with coordinates.

**GGUF**: 7 quantized versions available.

**Verdict**: Not recommended for GUI automation. Better options exist (UI-TARS, ShowUI).

---

## 4. Deployment Infrastructure

### 4.1 Ollama -- Simplest Local Deployment

**Best for**: Getting started quickly. One-command setup.

**Vision Models Available**:
```bash
# GUI-Specialized
ollama pull 0000/ui-tars-1.5-7b          # 7B, GUI-specialized
ollama pull 0000/ui-tars-1.5-7b-q8_0     # 7B, Q8 quantized
ollama pull avil/UI-TARS                  # 7B, community
ollama pull rashakol/UI-TARS-72B-DPO      # 72B, needs 64GB+

# General VLMs (with GUI capability via prompting)
ollama pull qwen2.5vl:3b                  # 3.2 GB
ollama pull qwen2.5vl:7b                  # 6.0 GB (recommended)
ollama pull qwen2.5vl:32b                 # 21 GB
ollama pull qwen2.5vl:72b                 # 49 GB
```

**Apple Silicon Performance** (estimated, based on community reports for 7B models):
- M1 Pro 16GB: ~8-15 tok/s (Q4_K_M), ~5-10 tok/s (Q8_0)
- M2 Pro 16GB: ~10-18 tok/s (Q4_K_M)
- M3 Pro 18GB: ~12-20 tok/s (Q4_K_M)
- M3 Max 36GB: ~20-30 tok/s (Q4_K_M)

**Note**: Vision models are slower than text-only because they process image tokens. A single 1920x1080 screenshot generates 1000-2000 image tokens before the model even starts reasoning. Expect 3-10 seconds per action for 7B models.

**API Usage**:
```bash
# Start server
ollama serve

# Use via API (OpenAI-compatible)
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "0000/ui-tars-1.5-7b",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64>"}},
          {"type": "text", "text": "Click on the search box"}
        ]
      }
    ]
  }'
```

### 4.2 llama.cpp -- Best Raw Performance on Apple Silicon

**Best for**: Maximum tokens/sec via Metal acceleration.

**Vision Model Support**: llama.cpp supports multimodal models via its LLaVA-style architecture. Qwen2-VL GGUF models work. UI-TARS GGUF models (being Qwen2-VL based) should work but may need the correct mmproj (multimodal projection) file.

**Setup**:
```bash
# Build with Metal support
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_METAL=ON
cmake --build build --config Release -j

# Download model
# Option 1: Use huggingface-cli
pip install huggingface-hub
huggingface-cli download bartowski/UI-TARS-7B-DPO-GGUF \
  --include "UI-TARS-7B-DPO-Q4_K_M.gguf" \
  --local-dir ./models/

# Run with vision
./build/bin/llama-llava-cli \
  -m models/UI-TARS-7B-DPO-Q4_K_M.gguf \
  --mmproj models/mmproj.gguf \
  --image screenshot.png \
  -p "Click on the search button"
```

**Important Caveat**: Not all vision models have pre-built mmproj files. Qwen2-VL architecture may need custom handling. Check the GGUF provider's repo for mmproj files.

**Performance**: Generally 20-40% faster than Ollama for the same model, due to direct Metal optimization without the Ollama wrapper overhead.

### 4.3 MLX (Apple's Framework) -- Best Native Apple Silicon

**Best for**: Maximum optimization on Apple Silicon. Uses unified memory efficiently.

**Package**: `mlx-vlm`
```bash
pip install -U mlx-vlm
```

**Supported Vision Models**:
- Qwen2-VL (all sizes) -- confirmed working
- Qwen2.5-VL (all sizes) -- confirmed working
- Qwen3.5 -- supported
- DeepSeek-OCR, GLM-OCR -- supported
- Phi-4 -- supported
- MiniCPM-o, Moondream3 -- supported
- **UI-TARS**: Not explicitly listed but may work (Qwen2-VL architecture)

**CLI Usage**:
```bash
# Generate from image
mlx_vlm.generate \
  --model mlx-community/Qwen2-VL-2B-Instruct-4bit \
  --max-tokens 200 \
  --image screenshot.png \
  --prompt "Identify all clickable UI elements and their coordinates"

# Launch chat UI
mlx_vlm.chat_ui --model mlx-community/Qwen2-VL-2B-Instruct-4bit

# Start OpenAI-compatible API server
mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8080
```

**OpenAI-Compatible API**: Yes! `mlx_vlm.server` exposes `/v1/chat/completions` endpoint. This means any tool expecting an OpenAI API can connect to it.

**Performance**: Generally the fastest option on Apple Silicon for supported models, as it uses Metal compute shaders optimized for the unified memory architecture.

### 4.4 LM Studio -- GUI-Based Local Deployment

**Best for**: Non-technical users who want a GUI.

**Vision Model Support**: Yes.
- Qwen2.5-VL (all sizes)
- Qwen3-VL (2B, 4B, 8B, 30B, 32B)
- GLM-4.6V-Flash (9B)
- olmOCR 2
- **UI-TARS**: Not in the default catalog but can load custom GGUF files

**Usage**:
1. Download LM Studio from https://lmstudio.ai
2. Search for "Qwen2.5-VL" or load a custom GGUF
3. Enable the local server (exposes OpenAI-compatible API on port 1234)
4. Point your application to `http://localhost:1234/v1`

### 4.5 vLLM -- Production Serving

**Apple Silicon Support**: No native support as of March 2026. vLLM targets NVIDIA/AMD GPUs. Not recommended for Mac deployment.

### 4.6 SGLang -- High-Performance Serving

**Apple Silicon Support**: No. Targets NVIDIA GPUs, AMD GPUs, Intel Xeon, Google TPUs, Ascend NPUs. Does NOT list Apple Silicon or macOS.

---

## 5. Quick-Start Recipes

### Recipe 1: UI-TARS 7B via Ollama (Recommended Starting Point)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
# Or: brew install ollama

# Pull the model
ollama pull 0000/ui-tars-1.5-7b

# Test with a screenshot
ollama run 0000/ui-tars-1.5-7b "What UI elements do you see? Click on the search bar." --images ~/Desktop/screenshot.png
```

**Memory**: ~6-8 GB RAM
**Speed**: ~8-15 tok/s on M1 Pro

### Recipe 2: Qwen2.5-VL via MLX (Best Apple Silicon Performance)

```bash
# Install
pip install -U mlx-vlm

# Run inference
python3 -c "
from mlx_vlm import load, generate
model, processor = load('mlx-community/Qwen2-VL-2B-Instruct-4bit')
output = generate(model, processor, 'screenshot.png',
                  'Identify all clickable elements with their positions',
                  max_tokens=200)
print(output)
"

# Or start an API server for integration
mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8080
```

**Memory**: ~3-4 GB RAM (4-bit quantized 2B model)
**Speed**: Fastest option for 2B models on Apple Silicon

### Recipe 3: ShowUI-2B via Transformers (Lightest GUI-Specialized)

```bash
pip install transformers torch qwen-vl-utils

python3 << 'EOF'
import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

model = Qwen2VLForConditionalGeneration.from_pretrained(
    "showlab/ShowUI-2B",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
processor = AutoProcessor.from_pretrained(
    "showlab/ShowUI-2B",
    min_pixels=256*28*28,
    max_pixels=1344*28*28
)

messages = [
    {"role": "user", "content": [
        {"type": "image", "image": "screenshot.png"},
        {"type": "text", "text": "Click on the search box"}
    ]}
]

text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
image_inputs, video_inputs = process_vision_info(messages)
inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                   padding=True, return_tensors="pt")
inputs = inputs.to(model.device)

generated_ids = model.generate(**inputs, max_new_tokens=128)
output = processor.batch_decode(generated_ids[:, inputs.input_ids.shape[1]:],
                                skip_special_tokens=True)
print(output[0])
# Expected: {"action": "CLICK", "position": [0.45, 0.32]}
EOF
```

**Memory**: ~5 GB RAM
**Speed**: ~15-25 tok/s on M1 Pro (MPS backend)

### Recipe 4: Computer Use OOTB (Full Framework with ShowUI/UI-TARS)

```bash
# Install Miniconda if not present
# Clone repo
git clone https://github.com/showlab/computer_use_ootb
cd computer_use_ootb
pip install -r requirements.txt

# Run with local ShowUI model
python app.py
# Opens Gradio UI at http://localhost:7860
```

**This is the closest to a "local version of GPT-5.4 CU"** -- it combines:
- Screenshot capture
- VLM inference (ShowUI, UI-TARS, or Claude)
- Action execution (mouse/keyboard)
- macOS support (M1+ with 16GB+)

### Recipe 5: CogAgent on Mac

```bash
git clone https://github.com/THUDM/CogAgent
cd CogAgent
pip install -r requirements.txt

# Run with INT8 quantization (fits in 16GB)
python inference/cli_demo.py \
  --model_dir THUDM/cogagent-9b-20241220 \
  --platform "Mac" \
  --quant 8
```

**Memory**: ~15 GB RAM (INT8)
**Caveat**: Tight fit on 16GB machine. May swap.

---

## 6. Memory Requirements Reference

### By Model + Quantization

| Model | FP16 | Q8_0 | Q6_K | Q4_K_M | Q4_0 |
|-------|------|------|------|--------|------|
| UI-TARS-2B / ShowUI-2B | ~4 GB | ~2.5 GB | ~2.2 GB | ~1.8 GB | ~1.5 GB |
| SmolVLM2-2.2B | ~5 GB | ~3 GB | ~2.5 GB | ~2 GB | ~1.7 GB |
| Qwen2.5-VL-3B | ~6 GB | ~4 GB | ~3.5 GB | ~3 GB | ~2.5 GB |
| UI-TARS-7B / Qwen2.5-VL-7B | ~14 GB | ~8 GB | ~6.5 GB | ~5 GB | ~4.5 GB |
| CogAgent-9B (14B total) | ~29 GB | ~15 GB | ~12 GB | ~8 GB | ~7 GB |
| Qwen2.5-VL-32B | ~64 GB | ~35 GB | ~28 GB | ~21 GB | ~18 GB |
| UI-TARS-72B / Qwen2.5-VL-72B | ~144 GB | ~75 GB | ~60 GB | ~49 GB | ~42 GB |

**Note**: These are model weights only. Actual RAM usage includes KV cache, image processing buffers, and OS overhead. Add 2-4 GB to the numbers above for real-world usage.

### What Fits on Which Mac

| Mac | RAM | Recommended Models |
|-----|-----|--------------------|
| M1 Pro 16GB | 16 GB | UI-TARS-2B, ShowUI-2B, Qwen2.5-VL-3B, UI-TARS-7B (Q4_K_M) |
| M2 Pro 16GB | 16 GB | Same as above, slightly faster |
| M3 Pro 18GB | 18 GB | Same + UI-TARS-7B (Q6_K), CogAgent-9B (INT4 -- tight) |
| M2 Max 32GB | 32 GB | All 7B at any quant + Qwen2.5-VL-32B (Q4_K_M -- tight) |
| M3 Max 36GB | 36 GB | Same + more comfortable margin for 32B |
| M3 Max 64GB | 64 GB | All 7B + 32B + UI-TARS-72B (Q4_K_M -- tight) |
| M2/M3 Ultra 128GB+ | 128+ GB | Everything including 72B at Q8 |

---

## 7. Action Output Formats

### UI-TARS Format
```
Action: click(start_box='(523, 287)')
Action: type(content='search query')
Action: scroll(direction='down', amount=3)
Action: hotkey(key='ctrl+c')
Action: wait()
Action: finished()
```
- Coordinates: **Pixel-based** (absolute x,y relative to screenshot resolution)
- Parser: `pip install ui-tars` provides `parse_action_to_structure_output()` and `parsing_response_to_pyautogui_code()`

### ShowUI Format
```json
{"action": "CLICK", "value": "Search box", "position": [0.45, 0.32]}
{"action": "INPUT", "value": "hello", "position": [0.45, 0.32]}
{"action": "SCROLL", "value": "down", "position": null}
```
- Coordinates: **Normalized 0-1** (relative to screenshot dimensions)
- Convert to pixels: `pixel_x = position[0] * screenshot_width`

### CogAgent Format
```
CLICK(box=[[352,102,786,139]], element_info='Search')
TYPE(box=[[352,102,786,139]], text='query', element_info='Search')
SCROLL_DOWN(box=[[0,209,998,952]], step_count=5, element_info='[None]')
```
- Coordinates: **Bounding box** [x1, y1, x2, y2] in pixels
- Click target: center of bounding box

### Qwen2.5-VL (with grounding prompt)
```json
{"bbox": [120, 45, 350, 85], "label": "search box"}
```
- Coordinates: Bounding box in pixels (when using grounding prompts)
- Not structured action format by default -- needs prompt engineering

### Claude Computer Use (for reference / compatibility target)
```json
{
  "type": "computer_20250124",
  "action": "click",
  "coordinate": [523, 287]
}
```
- Actions: click, type, key, scroll, screenshot, mouse_move, etc.
- Coordinates: Pixel-based [x, y]

---

## 8. End-to-End Frameworks

### 8.1 Computer Use OOTB (ShowUI team) -- RECOMMENDED

**URL**: https://github.com/showlab/computer_use_ootb

The closest thing to a "local GPT-5.4 CU". Provides:
- Screenshot capture
- Model inference (local or API)
- Action execution (mouse/keyboard via pyautogui)
- Gradio web UI
- **macOS + Windows support**

**Supported Models**:
- ShowUI-2B (local)
- UI-TARS-7B/72B (local or via SSH)
- Claude 3.5 Sonnet (API)
- GPT-4o + Qwen2-VL (as planner)

**Architecture Options**:
1. **Unified**: Single model handles planning + action (ShowUI, UI-TARS, Claude)
2. **Planner-Actor**: GPT-4o/Qwen2-VL plans, ShowUI/UI-TARS executes

**Requirements**: macOS M1+ with 16GB+ unified RAM for local models.

### 8.2 UI-TARS Desktop (ByteDance)

**URL**: https://github.com/bytedance/UI-TARS-desktop

Desktop application for local GUI automation using UI-TARS models.

**Install**:
```bash
npx @agent-tars/cli@latest
# or
npm install @agent-tars/cli@latest -g
```
Requires Node.js >= 22.

**Supported Providers** (confirmed):
- Volcengine (doubao models)
- Anthropic (Claude 3.7 Sonnet)
- Custom endpoints via `--provider` flag

**Configuration**:
```bash
agent-tars --provider custom --model ui-tars-1.5-7b --apiKey none --baseUrl http://localhost:11434/v1
```

**Integration with Local Models**: The `--provider custom --baseUrl` flag should allow pointing to a local Ollama or MLX server that exposes an OpenAI-compatible API. This is the key integration path.

### 8.3 CUA (trycua) -- VM-Based

**URL**: https://github.com/trycua/cua

Agent framework using Apple Virtualization.Framework for macOS/Linux VMs.

**Pros**: Sandboxed execution (safe), Apple Silicon native VMs
**Cons**: No documented local model support (cloud APIs only as of March 2026), complex setup

### 8.4 browser-use -- Browser-Specific

**URL**: https://github.com/browser-use/browser-use

**Local Model Support**: Yes, via Ollama:
```python
from browser_use import Agent, ChatOllama
llm = ChatOllama(model="llama3.1:8b")
```

**Caveat**: Only `qwen-vl-max` is recommended; other models have issues with action schema formatting. Browser-only (no desktop GUI automation).

---

## 9. Integration with UI-TARS Desktop

### Connecting to Local Ollama

The most practical integration path:

```bash
# Step 1: Start Ollama with UI-TARS
ollama serve &
ollama pull 0000/ui-tars-1.5-7b

# Step 2: Verify Ollama's OpenAI-compatible API
curl http://localhost:11434/v1/models

# Step 3: Start UI-TARS Desktop pointing to local Ollama
npx @agent-tars/cli@latest \
  --provider custom \
  --model 0000/ui-tars-1.5-7b \
  --baseUrl http://localhost:11434/v1 \
  --apiKey ollama
```

### Connecting to Local MLX Server

```bash
# Step 1: Start MLX server
pip install mlx-vlm
mlx_vlm.server --model mlx-community/Qwen2-VL-7B-Instruct-4bit --port 8080 &

# Step 2: Point UI-TARS Desktop to MLX
npx @agent-tars/cli@latest \
  --provider custom \
  --model Qwen2-VL-7B-Instruct-4bit \
  --baseUrl http://localhost:8080/v1 \
  --apiKey none
```

### Key Consideration

UI-TARS Desktop expects specific action output formats from the model. If using a non-UI-TARS model (e.g., plain Qwen2.5-VL), the action parsing may fail because the model doesn't output in UI-TARS format. Best results come from actually running a UI-TARS model through Ollama.

---

## 10. Recommendations

### For Your Setup (M1 Pro 16GB)

**Tier 1 -- Start Here**:
1. Install Ollama + pull `0000/ui-tars-1.5-7b` (Q4 quantized fits in RAM)
2. Test with screenshots: does it correctly identify UI elements and output actions?
3. If too slow, drop to `qwen2.5vl:3b` for faster iteration

**Tier 2 -- Better Performance**:
1. Install `mlx-vlm` and use `mlx-community/Qwen2-VL-2B-Instruct-4bit`
2. Fastest inference on Apple Silicon
3. Less capable than 7B but much faster

**Tier 3 -- Full Framework**:
1. Set up Computer Use OOTB with ShowUI-2B (local, lightweight)
2. This gives you the full screenshot->VLM->action->execute loop
3. macOS supported, 16GB sufficient

### Overall Ranking for GUI Automation Quality

1. **UI-TARS-72B-DPO** -- Best accuracy (22.7% OSWorld), needs 64GB+ RAM
2. **UI-TARS-7B-DPO / UI-TARS-1.5-7B** -- Best practical choice (18.7% OSWorld), fits in 16GB at Q4
3. **CogAgent-9B** -- Good quality, tight fit on 16GB (INT8)
4. **ShowUI-2B** -- Best lightweight option, MIT license
5. **Qwen2.5-VL-7B** -- Good base, needs prompt engineering for GUI actions
6. **SmolVLM2-Agentic-GUI** -- Promising but immature

### For device-use Integration

To replace or supplement GPT-5.4 CU with a local model in `device-use`:

1. Run UI-TARS-1.5-7B via Ollama (OpenAI-compatible API at localhost:11434)
2. Create a new backend class `LocalVLMBackend` in device-use that:
   - Takes screenshots via `mss` (already working)
   - Sends screenshot + task prompt to local Ollama API
   - Parses UI-TARS action format using `ui-tars` pip package
   - Converts to pyautogui commands using `parsing_response_to_pyautogui_code()`
3. This gives you a fully local, zero-API-cost GUI automation loop

The action format translation layer is the key integration work:
```
UI-TARS output:  Action: click(start_box='(523, 287)')
     |
     v  (parse with ui-tars package)
pyautogui code:  pyautogui.click(523, 287)
```

---

## Appendix: Models Not Recommended

| Model | Reason |
|-------|--------|
| SeeClick | No practical GGUF, only 33B derivative available |
| Molmo-7B | Not GUI-specialized, no structured action output |
| Qwen2.5-VL-72B | Needs 49GB+ RAM, impractical on most Macs |
| CogAgent at FP16 | Needs 29GB, won't fit on 16GB Mac |
| vLLM-served anything | No Apple Silicon support |
| SGLang-served anything | No Apple Silicon support |

---

## Appendix: Key URLs

| Resource | URL |
|----------|-----|
| UI-TARS GitHub | https://github.com/bytedance/UI-TARS |
| UI-TARS Desktop | https://github.com/bytedance/UI-TARS-desktop |
| UI-TARS pip package | `pip install ui-tars` |
| Computer Use OOTB | https://github.com/showlab/computer_use_ootb |
| mlx-vlm | https://github.com/Blaizzy/mlx-vlm |
| ShowUI | https://github.com/showlab/ShowUI |
| CogAgent | https://github.com/THUDM/CogAgent |
| CUA Framework | https://github.com/trycua/cua |
| browser-use | https://github.com/browser-use/browser-use |
| Ollama | https://ollama.com |
| LM Studio | https://lmstudio.ai |
| UI-TARS-7B-DPO GGUF (bartowski) | https://huggingface.co/bartowski/UI-TARS-7B-DPO-GGUF |
| UI-TARS-1.5-7B GGUF (Mungert) | https://huggingface.co/Mungert/UI-TARS-1.5-7B-GGUF |
| Qwen2.5-VL GGUF (unsloth) | https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF |
| SmolVLM2-Agentic-GUI | https://huggingface.co/smolagents/SmolVLM2-2.2B-Instruct-Agentic-GUI |
