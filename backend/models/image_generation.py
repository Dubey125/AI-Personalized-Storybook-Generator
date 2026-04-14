import os
import logging
from PIL import Image, ImageDraw, ImageOps


logger = logging.getLogger(__name__)

class ImageGenerator:
    def __init__(self):
        self.device = "cpu"
        self._torch = None
        self._diffusers_available = False
        try:
            import torch

            self._torch = torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._diffusers_available = True
        except Exception:
            self._torch = None
            self._diffusers_available = False
        self.model_id = "runwayml/stable-diffusion-v1-5" # Base model
        self.pipe = None
        self.active_adapter_path = None

    def runtime_mode(self) -> str:
        if self._diffusers_available:
            return "full-diffusers"
        return "photo-personalized-fallback"

    def _build_personalized_fallback(self, prompt: str, seed: int, reference_image_path: str = "") -> Image.Image:
        base_color = (220 + (seed % 24), 236 + (seed % 14), 248)
        image = Image.new("RGB", (768, 768), base_color)
        draw = ImageDraw.Draw(image)

        if reference_image_path and os.path.exists(reference_image_path):
            try:
                with Image.open(reference_image_path) as reference:
                    portrait = reference.convert("RGB")
                    portrait = ImageOps.fit(portrait, (420, 420), method=Image.Resampling.LANCZOS)
                    image.paste(portrait, (174, 120))
            except Exception:
                pass

        draw.rectangle((30, 582, 738, 736), fill=(255, 255, 255))
        draw.text((50, 610), "Personalized fallback mode", fill=(19, 33, 58))
        draw.text((50, 646), prompt[:92], fill=(67, 88, 120))
        return image
        
    def load_model(self):
        if not self._diffusers_available:
            return
        if not self.pipe:
            from diffusers import StableDiffusionPipeline

            print(f"Loading Stable Diffusion model on {self.device}...")
            self.pipe = StableDiffusionPipeline.from_pretrained(
                self.model_id, 
                torch_dtype=self._torch.float16 if self.device == "cuda" else self._torch.float32,
                low_cpu_mem_usage=True,
                safety_checker=None
            )
            self.pipe = self.pipe.to(self.device)
            # To reduce memory usage:
            self.pipe.enable_attention_slicing()
            print("Model loaded successfully.")

    def _deactivate_adapter(self):
        if self.pipe and hasattr(self.pipe, "unload_lora_weights"):
            try:
                self.pipe.unload_lora_weights()
            except Exception:
                pass
        self.active_adapter_path = None

    def _activate_adapter(self, adapter_path: str, adapter_scale: float = 0.85):
        self.load_model()
        if not self.pipe:
            return

        if not adapter_path or not os.path.exists(adapter_path):
            self._deactivate_adapter()
            return

        if not adapter_path.lower().endswith((".safetensors", ".bin", ".pt", ".ckpt")):
            self._deactivate_adapter()
            return

        if self.active_adapter_path == adapter_path:
            return

        self._deactivate_adapter()
        adapter_dir = os.path.dirname(adapter_path)
        adapter_name = os.path.basename(adapter_path)
        try:
            self.pipe.load_lora_weights(adapter_path)
        except Exception:
            # diffusers commonly expects directory + weight_name for local files.
            self.pipe.load_lora_weights(adapter_dir, weight_name=adapter_name)
        if hasattr(self.pipe, "set_adapters"):
            try:
                self.pipe.set_adapters(["default"], adapter_weights=[adapter_scale])
            except Exception as exc:
                logger.warning("Adapter scale application skipped: %s", exc)
        self.active_adapter_path = adapter_path
            
    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        adapter_path: str = "",
        adapter_scale: float = 0.85,
        reference_image_path: str = "",
        num_inference_steps: int | None = None,
        guidance_scale: float = 7.5,
    ) -> Image.Image:
        self.load_model()
        if not self.pipe or not self._torch:
            return self._build_personalized_fallback(
                prompt=prompt,
                seed=seed,
                reference_image_path=reference_image_path,
            )

        if adapter_path:
            try:
                self._activate_adapter(adapter_path, adapter_scale=adapter_scale)
            except Exception as exc:
                logger.warning("Adapter activation failed for '%s': %s", adapter_path, exc)
                self._deactivate_adapter()
        else:
            self._deactivate_adapter()
        
        generator = self._torch.Generator(self.device).manual_seed(seed)
        effective_steps = num_inference_steps
        if effective_steps is None:
            # CPU inference is very slow for SD1.5; keep a lower default for practical latency.
            effective_steps = 4 if self.device == "cpu" else 30
        effective_steps = max(1, int(effective_steps))
        
        print(f"Generating image for prompt: '{prompt}'")
        image = self.pipe(
            prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=effective_steps,
            guidance_scale=guidance_scale,
            generator=generator
        ).images[0]
        
        return image

# Placeholder for Face IP-Adapter / InsightFace integration for consistency
# In a full production app, you would use IP-Adapter-FaceID to enforce the 
# uploaded face embed onto the SD generation process.
