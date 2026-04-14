from PIL import Image

CONTROLNET_MODEL_ID = "lllyasviel/sd-controlnet-openpose"

class ControlNetPoseHelper:
    def __init__(self, device=None):
        self._torch = None
        try:
            import torch

            self._torch = torch
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        except Exception:
            self.device = device or "cpu"
        self.controlnet = None
        self.pipe = None

    def load_controlnet(self):
        if not self._torch:
            raise RuntimeError("ControlNet dependencies are unavailable")

        from diffusers import StableDiffusionControlNetPipeline, ControlNetModel

        if self.controlnet is None:
            self.controlnet = ControlNetModel.from_pretrained(CONTROLNET_MODEL_ID, torch_dtype=self._torch.float16 if self.device == "cuda" else self._torch.float32)
            self.controlnet = self.controlnet.to(self.device)
        if self.pipe is None:
            self.pipe = StableDiffusionControlNetPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                controlnet=self.controlnet,
                torch_dtype=self._torch.float16 if self.device == "cuda" else self._torch.float32,
            )
            self.pipe = self.pipe.to(self.device)

    def generate_with_pose(self, prompt, pose_image: Image.Image, negative_prompt="", seed=42, num_inference_steps=30, guidance_scale=7.5):
        self.load_controlnet()
        generator = self._torch.Generator(self.device).manual_seed(seed)
        result = self.pipe(
            prompt=prompt,
            image=pose_image,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        return result.images[0]
