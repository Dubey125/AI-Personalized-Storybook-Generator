import hashlib
from typing import Any, Dict, List

from PIL import Image

MAX_SEED = 2_147_483_647


class FaceIdentityService:
    def __init__(self) -> None:
        self._insightface_app = None
        self._insightface_error = ""

    def _build_seed_from_embedding(self, embedding: List[float]) -> int:
        rounded = ",".join(f"{value:.5f}" for value in embedding)
        digest = hashlib.sha256(rounded.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % MAX_SEED

    def _build_seed_from_image_fingerprint(self, image_path: str) -> int:
        with Image.open(image_path) as image:
            grayscale = image.convert("L").resize((32, 32))
            digest = hashlib.sha256(grayscale.tobytes()).digest()
        return int.from_bytes(digest[:8], "big") % MAX_SEED

    def _load_insightface(self) -> None:
        if self._insightface_app is not None or self._insightface_error:
            return

        try:
            from insightface.app import FaceAnalysis

            self._insightface_app = FaceAnalysis(
                name="buffalo_l",
                providers=["CPUExecutionProvider"],
            )
            self._insightface_app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as exc:
            self._insightface_error = str(exc)

    def build_identity_profile(self, image_path: str) -> Dict[str, Any]:
        self._load_insightface()

        if self._insightface_app is not None:
            try:
                import numpy as np

                with Image.open(image_path) as image:
                    rgb_image = image.convert("RGB")
                    rgb_array = np.array(rgb_image)
                    bgr_array = rgb_array[:, :, ::-1]

                faces = self._insightface_app.get(bgr_array)
                if faces:
                    embedding = faces[0].normed_embedding.tolist()
                    seed = self._build_seed_from_embedding(embedding)
                    return {
                        "identity_seed": seed,
                        "identity_method": "insightface",
                        "face_detected": True,
                        "embedding_dim": len(embedding),
                        "diagnostic": "Identity seed derived from face embedding.",
                    }
            except Exception as exc:
                self._insightface_error = str(exc)

        fallback_seed = self._build_seed_from_image_fingerprint(image_path)
        diagnostic = "Fallback image fingerprint used for identity seed."
        if self._insightface_error:
            diagnostic = f"{diagnostic} InsightFace unavailable: {self._insightface_error}"

        return {
            "identity_seed": fallback_seed,
            "identity_method": "image_fingerprint_fallback",
            "face_detected": False,
            "embedding_dim": 0,
            "diagnostic": diagnostic,
        }
