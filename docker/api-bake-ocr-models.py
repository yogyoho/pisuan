"""构建期烘焙 rapidocr 运行时模型（api.Dockerfile 的 RUN 步骤调用）。

构建机在线下载三个 PP-OCRv5 mobile 模型到 RAPIDOCR_MODEL_DIR，离线客户机首解析
直接吃本层烘焙产物，不再联网下载。

模型参数经 pisuan 侧 RapidOCRParser._get_model_params() 获取，与运行时严格同源
（rapid_ocr.py:57-71）——不在本脚本复写参数，避免双处漂移。若 rapid_ocr.py 的
模型档位（engine/lang/type/version）变更，产物文件名随之变化，下方断言失败即
拦截构建，强迫同步本清单。

另可在运行容器内对临时目录实跑验证烘焙语义：
  docker cp docker/api-bake-ocr-models.py <api容器>:/tmp/
  docker exec -e RAPIDOCR_MODEL_DIR=/tmp/bake-models <api容器> python /tmp/api-bake-ocr-models.py
"""

from pathlib import Path
import os

import numpy as np
from rapidocr import RapidOCR

from pisuan.knowledge.parser.rapid_ocr import RapidOCRParser

# 预期烘焙产物（与 rapid_ocr.py:57-71 的 PP-OCRv5 + MOBILE 档位一一对应；漂移时断言拦截）。
# 注意 cls 档位实际解析为 ch_ppocr_mobile_v2.0_cls_mobile.onnx（rapidocr 对 cls 不分 v5，
# 沿用 v2.0 mobile；2026-11-08 运行容器实测下载日志确认），勿凭直觉写成 textline_ori 名。
EXPECTED = [
    "ch_PP-OCRv5_det_mobile.onnx",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "ch_PP-OCRv5_rec_mobile.onnx",
]


def main() -> None:
    model_dir = os.environ["RAPIDOCR_MODEL_DIR"]
    parser = RapidOCRParser()
    ocr = RapidOCR(params=parser._get_model_params())  # 与运行时同源参数（私有访问为有意为之）
    ocr(np.full((8, 8, 3), 255, dtype=np.uint8))  # 8x8 白图触发一次推理，确保模型完成解析/下载
    missing = [name for name in EXPECTED if not (Path(model_dir) / name).is_file()]
    if missing:
        raise SystemExit(f"烘焙断言失败：{model_dir} 缺模型 {missing}——rapid_ocr.py 参数与烘焙预期漂移？")
    for name in EXPECTED:
        size = (Path(model_dir) / name).stat().st_size
        print(f"[bake] {name} ({size} bytes)")
    print(f"[bake] ok: {len(EXPECTED)} 个模型已在位（{model_dir}）")


if __name__ == "__main__":
    main()
