from __future__ import annotations

import copy
import random
import time
from pathlib import Path

from drawing.renderer import (
    AssembledPrompt, EmptyPromptError, RendererAdapter, RenderResult,
)


NODE_POSITIVE = "17"
NODE_NEGATIVE = "7"
NODE_SAVE = "9"
NODE_LATENT = "5"


class SDXLAdapter(RendererAdapter):
    renderer_id = "sdxl"

    def __init__(
        self,
        comfy_client,
        workflow_template: dict,
        *,
        positive_prefix: str = "embedding:lazypos",
        negative_prefix: str = "embedding:lazyneg, embedding:lazyhand",
        timeout_sec: int = 180,
        poll_interval_sec: float = 0.5,
        hard_timeout_sec: float | None = None,
    ):
        self.comfy_client = comfy_client
        self.workflow_template = workflow_template
        self.positive_prefix = positive_prefix
        self.negative_prefix = negative_prefix
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.hard_timeout_sec = hard_timeout_sec

    def render(self, prompt: AssembledPrompt) -> RenderResult:
        if not prompt.positive.strip():
            raise EmptyPromptError("SDXL render: empty positive prompt")

        wf = self._inject_into_workflow(
            self.workflow_template, prompt.positive, prompt.negative, prompt.seed,
            filename_prefix=prompt.filename_prefix,
            width=prompt.width,
            height=prompt.height,
        )

        start = time.time()
        paths: list[Path] = self.comfy_client.generate(
            wf,
            timeout_sec=self.timeout_sec,
            poll_interval_sec=self.poll_interval_sec,
            hard_timeout_sec=self.hard_timeout_sec,
        )
        duration = time.time() - start

        if not paths:
            raise RuntimeError(
                "SDXL render: ComfyUI вернул 0 изображений "
                f"(prompt_len={len(prompt.positive)}, seed={prompt.seed})"
            )

        return RenderResult(
            image_path=paths[0],
            prompt_used=prompt,
            duration_sec=duration,
            extra={
                "backend": "comfyui",
                "renderer_id": self.renderer_id,
                "all_paths": [str(p) for p in paths],
            },
        )

    @staticmethod
    def _inject_into_workflow(
        template: dict,
        positive: str,
        negative: str,
        seed: int | None,
        *,
        filename_prefix: str = "",
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        wf = copy.deepcopy(template)

        if NODE_POSITIVE in wf and wf[NODE_POSITIVE].get("class_type") == "CLIPTextEncode":
            wf[NODE_POSITIVE]["inputs"]["text"] = positive

        if NODE_NEGATIVE in wf and wf[NODE_NEGATIVE].get("class_type") == "CLIPTextEncode":
            wf[NODE_NEGATIVE]["inputs"]["text"] = negative

        if filename_prefix and NODE_SAVE in wf and wf[NODE_SAVE].get("class_type") == "SaveImage":
            wf[NODE_SAVE]["inputs"]["filename_prefix"] = filename_prefix

        if (width is not None and height is not None
                and NODE_LATENT in wf
                and wf[NODE_LATENT].get("class_type") == "EmptyLatentImage"):
            wf[NODE_LATENT]["inputs"]["width"] = int(width)
            wf[NODE_LATENT]["inputs"]["height"] = int(height)

        actual_seed = seed if seed is not None else random.randint(0, 2**63 - 1)
        s = actual_seed
        for node_id, node in wf.items():
            if "seed" in node.get("inputs", {}):
                wf[node_id]["inputs"]["seed"] = s
                s = (s * 16807 + 17) % (2**63 - 1)

        return wf
