import numpy as np
import torch

from segment_anything import sam_model_registry, SamPredictor

from app.util import get_resource_path


class Segmenter:

    class Predictor(SamPredictor):

        def __init__(self):

            # model_type, checkpoint = "vit_b", "sam_vit_b_01ec64.pth"
            # model_type, checkpoint = "vit_l", "sam_vit_l_0b3195.pth"
            model_type, checkpoint = "vit_h", "sam_vit_h_4b8939.pth"

            checkpoint = get_resource_path(checkpoint)

            model = sam_model_registry[model_type](checkpoint = checkpoint)

            if torch.cuda.is_available():

                device = "cuda"

            elif torch.backends.mps.is_available():

                device = "mps"

            else:

                device = "cpu"

            model.to(device)

            self.original_size = (0, 0)
            self.input_size    = (0, 0)
            self.features      = None
            self.is_image_set  = False

            super().__init__(model)

        def set_image_embedding(self, embedding: np.ndarray, original_width: int, original_height: int):

            embedding = torch.from_numpy(embedding).to(self.device)

            scale = 1024.0 / max(original_width, original_height)

            input_w = int(round(original_width  * scale))
            input_h = int(round(original_height * scale))

            self.original_size = (original_height, original_width)
            self.input_size    = (input_h, input_w)
            self.features      = embedding
            self.is_image_set  = True

    def __init__(self):

        self._predictor = Segmenter.Predictor()

    def set_image(self, image, embedding = None) -> np.ndarray:

        predictor = self._predictor

        if embedding is None:

            predictor.set_image(image)

            embedding = predictor.get_image_embedding().detach().cpu().numpy()

        else:

            height, width = image.shape[:2]

            predictor.set_image_embedding(embedding, width, height)

        return embedding

    def predict(self, prompts) -> np.ndarray:

        predictor = self._predictor

        coords = []
        labels = []

        for v in prompts:

            coords.append((v['x'], v['y']))
            labels.append(v['label'])

        masks, scores, logits = predictor.predict \
            (
                point_coords = np.asarray(coords),
                point_labels = np.asarray(labels),
                multimask_output = False
            )

        return masks[0]
