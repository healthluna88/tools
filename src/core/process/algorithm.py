import cv2
import numpy as np

from .parameter import ParameterFloat, ParameterEnum, ParameterInt
from .processor import Processor


_cv_kernels = \
    {
        "3x3": cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        "5x5": cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        "7x7": cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        "9x9": cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    }


@Processor.register
class Blur(Processor):

    Name  = 'Blur'
    Label = '模糊'

    def __init__(self):

        super().__init__(Blur.Name, Blur.Label)

        self.add(ParameterFloat("strength", default = 10.0, v_min = 1.0, v_max = 50.0, v_step = 1.0))

    def process(self, image, mask):

        strength = self.get("strength")

        return cv2.GaussianBlur(mask, (0, 0), sigmaX = strength)


@Processor.register
class Erode(Processor):

    Name  = 'Erode'
    Label = '腐蚀'

    def __init__(self):

        super().__init__(Erode.Name, Erode.Label)

        self.add(ParameterEnum("kernel", _cv_kernels.keys(), default = "3x3"))
        self.add(ParameterInt("iterations", default = 1, v_min = 1, v_max = 50, v_step = 1))

    def process(self, image, mask):

        kernel     = self.get("kernel"    )
        iterations = self.get("iterations")

        return cv2.erode(mask, _cv_kernels[kernel], iterations = iterations)


@Processor.register
class Dilate(Processor):

    Name  = 'Dilate'
    Label = '膨胀'

    def __init__(self):

        super().__init__(Dilate.Name, Dilate.Label)

        self.add(ParameterEnum("kernel", _cv_kernels.keys(), default = "3x3"))
        self.add(ParameterInt("iterations", default = 1, v_min = 1, v_max = 50, v_step = 1))

    def process(self, image, mask):

        kernel     = self.get("kernel"    )
        iterations = self.get("iterations")

        return cv2.dilate(mask, _cv_kernels[kernel], iterations = iterations)


# @Processor.register
# class Contour(Processor):
#
#     Name  = 'Contour'
#     Label = '轮廓测试'
#
#     def __init__(self):
#
#         super().__init__(Contour.Name, Contour.Label)
#
#     def process(self, image):
#
#         contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#
#         smooth = np.zeros_like(image)
#
#         # cv2.drawContours(smooth, contours, -1, (255, 255, 255, 255), -1)
#
#         # return smooth
#
#         for cnt in contours:
#
#             eps = 0.001 * cv2.arcLength(cnt, True)
#
#             approx = cv2.approxPolyDP(cnt, eps, True)
#
#             cv2.drawContours(smooth, [approx], -1, (0, 255, 0, 255), -1)
#
#         return smooth


