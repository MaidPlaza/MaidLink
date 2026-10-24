from dataclasses import dataclass, field


VRAM_FREE_MIB = 1024
FIT_SLACK_MIB = 1024
VRAM_RESERVE_MIB = VRAM_FREE_MIB + FIT_SLACK_MIB

@dataclass
class LLMConfig:
    model: str = "models/llm/gemma-4-12b-it-qat-q4_0.gguf"
    family: str = ""
    model_choice: str = "gemma"
    reasoning_mode: str = "fast"
    preset: str = "standard"
    base_url: str = "http://127.0.0.1:8000"
    embed_base_url: str = "http://127.0.0.1:8002"
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 20
    presence_penalty: float = 1.5
    repeat_penalty: float = 1.0
    num_ctx: int = 32768
    max_history_tokens: int = 12000
    max_history_messages: int = 300
    ctx_overrides: dict[str, int] = field(default_factory=dict)

    server_binary: str = "llama-server/llama-server.exe"
    server_mmproj: str = "models/mmproj/mmproj-gemma-4-12b-it-qat-q4_0.gguf"
    server_mtp_draft: str = "models/llm/mtp-gemma-4-12b-it-Q8_0.gguf"
    mtp_draft_n_max: int = 2
    vram_free_mib: int = VRAM_FREE_MIB
    server_launch_args: list[str] = field(default_factory=lambda: [
        "-ngl", "auto",
        "-c", "32768",
        "--port", "8000",
        "--jinja",
        "--reasoning", "on",
        "--reasoning-budget", "8192",
        "-fa", "on",
    ])
    server_extra_args: list[str] = field(default_factory=list)
    server_startup_timeout_sec: int = 120
    server_shutdown_timeout_sec: int = 15


@dataclass
class EmbedderConfig:
    model: str = "models/embed/nomic-embed-text-v1.5.Q4_K_M.gguf"
    base_url: str = "http://127.0.0.1:8002"
    server_binary: str = "llama-server/llama-server.exe"
    server_mmproj: str = ""
    server_launch_args: list[str] = field(default_factory=lambda: [
        "--embeddings", "--port", "8002", "-ngl", "0",
        "-c", "8192", "-np", "4", "-b", "2048", "-ub", "2048",
    ])
    server_startup_timeout_sec: int = 60
    server_shutdown_timeout_sec: int = 10


@dataclass
class ImageGenConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8188"
    keep_generated: bool = False

    launch_command: list[str] = field(default_factory=lambda: [
        "image_gen/ComfyUI_windows_portable/python_embeded/python.exe",
        "-s",
        "image_gen/ComfyUI_windows_portable/ComfyUI/main.py",
        "--windows-standalone-build",
        "--cache-none",
        "--disable-auto-launch",
        "--port", "8188",
        "--listen", "127.0.0.1",
    ])
    server_startup_timeout_sec: int = 90
    server_shutdown_timeout_sec: int = 10

    workflow_default: str = "image_gen/workflows/maid_portrait.json"

    output_dir: str = "image_gen/generated"
    comfy_output_dir: str = "image_gen/comfy_output"

    poll_interval_sec: float = 0.5
    generation_timeout_sec: int = 180
    generation_hard_timeout_sec: int = 600


@dataclass
class WeatherConfig:
    enabled: bool = True
    cache_ttl_seconds: int = 600
    forecast_days: int = 7


@dataclass
class LifecycleConfig:
    foreground_unloaded_after_sec: float = 999_999.0
    idle_foreground_unloaded_after_sec: float = 600.0
    background_unloaded_after_sec: float = 60.0


@dataclass
class SessionConfig:
    proactive_enabled: bool = True

    idle_timeout_minutes: int = 15

    reflection_max_attempts: int = 3

    queue_path: str = "data/reflection_queue.json"

    continuation_budget: int = 3

    grammar_polish: bool = True

    burst_wait_seconds: float = 0.6
    burst_typing_grace_seconds: float = 4.0
    burst_max_hold_seconds: float = 90.0
    burst_interrupt_visible_chars: int = 160


@dataclass
class DrawingConfig:
    max_rating: str = "sfw"
    negative_safety_tags: list[str] = field(default_factory=lambda: [
        "child", "loli", "shota", "school uniform",
    ])
    positive_safety_tags: list[str] = field(default_factory=list)
    quality_tags: list[str] = field(default_factory=lambda: [
        "masterpiece", "best quality", "very aesthetic", "absurdres", "newest",
    ])
    renderer_id: str = "sdxl"

    vision_critic_enabled: bool = True
    vision_critic_max_retries: int = 1
    vision_critic_soft_threshold: float = 0.7

    active_style_id: str = "default"
    outfit_change_min_tier: str = "warming"

    portrait_align_enabled: bool = False
    portrait_align_scale: float = 4.5
    portrait_align_shift: float = 0.22

    mood_portraits_enabled: bool = True


@dataclass
class AppConfig:
    character_id: str = ""
    state_path: str = "data/state.json"
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    image_gen: ImageGenConfig = field(default_factory=ImageGenConfig)
    drawing: DrawingConfig = field(default_factory=DrawingConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)


GEMMA_IMAGE_MAX_TOKENS = 512

LLM_MODELS: dict[str, dict] = {
    "qwen": {
        "label": "Qwen 3.5 9B (Q8)",
        "model": "models/llm/Qwen3.5-9B-Q8_0.gguf",
        "mmproj": "models/mmproj/mmproj-BF16.gguf",
        "family": "qwen",
        "ctx": 16384,
        "history_budget": 5000,
        "kv_kib_per_token": 128,
        "ctx_steps": [[16384, 5000]],
    },
    "gemma": {
        "label": "Gemma 4 12B QAT Q4_0",
        "vram_gb": 8,
        "model": "models/llm/gemma-4-12b-it-qat-q4_0.gguf",
        "mmproj": "models/mmproj/mmproj-gemma-4-12b-it-qat-q4_0.gguf",
        "family": "gemma",
        "ctx": 65536,
        "history_budget": 24000,
        "ctx_steps": [[32768, 10000], [49152, 17000], [65536, 24000],
                      [98304, 38000], [131072, 52000]],
        "kv_kib_per_token": 16,
        "mtp": "models/llm/mtp-gemma-4-12b-it-Q8_0.gguf",
        "extra_args": ["--chat-template-file", "llama-server/gemma4-fixed.jinja",
                       "--image-max-tokens", str(GEMMA_IMAGE_MAX_TOKENS)],
        "expected_tps": 30,
    },
    "gemma-strong": {
        "label": "Gemma 4 31B Q3_K_XL",
        "vram_gb": 24,
        "model": "models/llm/gemma-4-31B-it-UD-Q3_K_XL.gguf",
        "mmproj": "",
        "family": "gemma",
        "mtp": "models/llm/mtp-gemma-4-31B-it-Q8_0.gguf",
        "ctx": 32768,
        "history_budget": 16000,
        "ctx_steps": [[16384, 6000], [24576, 10000], [32768, 16000],
                      [40960, 20000], [49152, 24000]],
        "kv_kib_per_token": 42,
        "extra_args": ["-ctk", "q8_0", "-ctv", "q8_0",
                       "--ctx-checkpoints", "32", "--checkpoint-min-step", "2048",
                       "--cache-ram", "16384", "-ub", "1024",
                       "--chat-template-file", "llama-server/gemma4-fixed.jinja"],
        "fast_post": True,
        "reasoning_budget": 2048,
        "expected_tps": 9,
    },
    "gemma-strong-fast": {
        "label": "Gemma 4 31B IQ3_XXS",
        "vram_gb": 16,
        "model": "models/llm/gemma-4-31B-it-UD-IQ3_XXS.gguf",
        "mmproj": "",
        "family": "gemma",
        "ctx": 32768,
        "history_budget": 16000,
        "ctx_steps": [[16384, 6000], [24576, 10000], [32768, 16000],
                      [40960, 20000], [49152, 24000]],
        "kv_kib_per_token": 42,
        "extra_args": ["-ctk", "q8_0", "-ctv", "q8_0",
                       "--ctx-checkpoints", "32", "--checkpoint-min-step", "2048",
                       "--cache-ram", "16384", "-ub", "1024",
                       "--chat-template-file", "llama-server/gemma4-fixed.jinja"],
        "fast_post": True,
        "reasoning_budget": 3072,
        "expected_tps": 24,
    },
    "gemma-mid": {
        "label": "Gemma 4 26B-A4B IQ4 (экспериментальная, vision)",
        "experimental": True,
        "model": "models/llm/gemma-4-26B-A4B-it-UD-IQ4_XS.gguf",
        "mmproj": "models/mmproj/mmproj-gemma-4-26B-A4B-it-F16.gguf",
        "family": "gemma",
        "ctx": 32768,
        "history_budget": 10000,
        "ctx_steps": [[32768, 10000], [49152, 17000], [65536, 24000]],
        "extra_args": ["-ctk", "q8_0", "-ctv", "q8_0",
                       "--load-mode", "none",
                       "--ctx-checkpoints", "32", "--checkpoint-min-step", "2048",
                       "--cache-ram", "16384",
                       "--chat-template-file", "llama-server/gemma4-fixed.jinja",
                       "--image-max-tokens", str(GEMMA_IMAGE_MAX_TOKENS)],
        "reasoning_budget": 6144,
        "expected_tps": 45,
    },
    "gemma-mid-q4": {
        "label": "Gemma 4 26B-A4B Q4 (экспериментальная, без vision)",
        "experimental": True,
        "model": "models/llm/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf",
        "mmproj": "",
        "family": "gemma",
        "ctx": 32768,
        "history_budget": 10000,
        "ctx_steps": [[32768, 10000], [49152, 17000], [65536, 24000]],
        "extra_args": ["-ctk", "q8_0", "-ctv", "q8_0",
                       "--load-mode", "none",
                       "--ctx-checkpoints", "32", "--checkpoint-min-step", "2048",
                       "--cache-ram", "16384",
                       "--chat-template-file", "llama-server/gemma4-fixed.jinja"],
        "reasoning_budget": 6144,
        "expected_tps": 35,
    },
}


MODEL_CATALOG = ["gemma", "gemma-strong-fast", "gemma-strong"]


def model_label(key: str) -> str:
    spec = LLM_MODELS.get(key) or {}
    label = spec.get("label") or key
    vram = spec.get("vram_gb")
    return f"{label} ({vram:g} ГБ)" if vram else label


def resolve_ctx_step(spec: dict, override: int | None) -> tuple[int, int]:
    ctx = int(spec.get("ctx") or 0)
    hist = int(spec.get("history_budget", 12000))
    if override:
        for pair in spec.get("ctx_steps") or []:
            if int(pair[0]) == int(override):
                return int(pair[0]), int(pair[1])
    return ctx, hist


LLM_PRESETS: dict[str, dict] = {
    "standard": {
        "label": "Стандартный",
        "model": "gemma",
        "reasoning_mode": "fast",
        "summary": "Быстрые ответы, видит картинки. Хватает для повседневного общения.",
        "speed": 3,
    },
    "balanced": {
        "label": "Сбалансированный",
        "model": "gemma-strong-fast",
        "reasoning_mode": "fast",
        "summary": "Умнее стандартного и заметно быстрее рассудительного. Без vision.",
        "speed": 2,
    },
    "reasoning": {
        "label": "Рассудительный",
        "model": "gemma-strong",
        "reasoning_mode": "fast",
        "summary": "Умнее и тоньше в прозе и психологии, но заметно медленнее. Без vision.",
        "speed": 1,
    },
    "custom": {
        "label": "Пользовательский",
        "summary": "Модель, окно контекста и режим рассуждений — вручную.",
    },
}
PRESET_ORDER = ["standard", "balanced", "reasoning", "custom"]


def preset_matches(config: "AppConfig", key: str) -> bool:
    p = LLM_PRESETS.get(key) or {}
    model = p.get("model")
    if not model:
        return False
    llm = config.llm
    if llm.model_choice != model:
        return False
    if (getattr(llm, "ctx_overrides", None) or {}).get(model):
        return False
    return llm.reasoning_mode == p.get("reasoning_mode")


def resolve_preset(config: "AppConfig") -> str:
    saved = getattr(config.llm, "preset", "") or ""
    if saved == "custom":
        return "custom"
    if saved in LLM_PRESETS and preset_matches(config, saved):
        return saved
    for key in PRESET_ORDER:
        if preset_matches(config, key):
            return key
    return "custom"


def apply_preset_choice(config: "AppConfig", key: str) -> bool:
    p = LLM_PRESETS.get(key)
    if p is None:
        return False
    config.llm.preset = key
    model = p.get("model")
    if not model:
        return True
    over = dict(getattr(config.llm, "ctx_overrides", None) or {})
    over.pop(model, None)
    config.llm.ctx_overrides = over
    config.llm.reasoning_mode = p["reasoning_mode"]
    return apply_model_choice(config, model)


def apply_model_choice(config: "AppConfig", choice: str) -> bool:
    spec = LLM_MODELS.get(choice)
    if spec is None:
        return False
    config.llm.model = spec["model"]
    config.llm.server_mmproj = spec["mmproj"]
    config.llm.family = spec["family"]
    config.llm.model_choice = choice
    _ov = (getattr(config.llm, "ctx_overrides", None) or {}).get(choice)
    ctx, hist = resolve_ctx_step(spec, _ov)
    if ctx:
        args = config.llm.server_launch_args
        for i, a in enumerate(args[:-1]):
            if a == "-c":
                args[i + 1] = str(ctx)
                break
        else:
            config.llm.server_launch_args = list(args) + ["-c", str(ctx)]
    config.llm.max_history_tokens = hist
    config.llm.server_mtp_draft = spec.get("mtp", "")
    args = config.llm.server_launch_args
    for i, a in enumerate(args[:-1]):
        if a == "-ngl":
            args[i + 1] = "auto"
            break
    else:
        config.llm.server_launch_args = list(args) + ["-ngl", "auto"]
    rb = int(spec.get("reasoning_budget", 8192))
    args = config.llm.server_launch_args
    for i, a in enumerate(args[:-1]):
        if a == "--reasoning-budget":
            args[i + 1] = str(rb)
            break
    else:
        config.llm.server_launch_args = list(args) + ["--reasoning-budget", str(rb)]
    config.llm.server_extra_args = list(spec.get("extra_args", []))
    return True
