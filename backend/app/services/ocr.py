from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import DATA_DIR, get_settings


class OCRError(RuntimeError):
    pass


@dataclass
class OCRResult:
    provider: str
    text: str
    blocks: list[dict[str, Any]]


class OCRProvider:
    name = "disabled"

    def extract_text(self, content: bytes, filename: str) -> OCRResult:
        raise OCRError("本地 OCR 未启用，请安装 PaddleOCR 依赖并设置 OCR_PROVIDER=paddleocr；当前可先使用 Excel 或文字型 PDF")


class DisabledOCRProvider(OCRProvider):
    name = "disabled"


class PaddleOCRProvider(OCRProvider):
    name = "local_paddleocr"

    def __init__(self, lang: str = "ch") -> None:
        self.lang = lang

    def extract_text(self, content: bytes, filename: str) -> OCRResult:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise OCRError("PaddleOCR 未安装，请先安装 paddleocr/paddlepaddle 后再使用图片识别") from exc

        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise OCRError("PaddleOCR 图像依赖未安装完整，请检查 opencv-python/numpy") from exc

        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise OCRError("未能读取图片内容，请确认文件是有效图片")

        model_root = DATA_DIR / "ocr_models" / self.lang
        engine = PaddleOCR(
            use_angle_cls=False,
            lang=self.lang,
            show_log=False,
            use_gpu=False,
            det_model_dir=str(model_root / "det"),
            rec_model_dir=str(model_root / "rec"),
            cls_model_dir=str(model_root / "cls"),
        )
        raw_result = engine.ocr(image, cls=False)
        blocks: list[dict[str, Any]] = []
        lines: list[str] = []
        for page in raw_result or []:
            for item in page or []:
                if not item or len(item) < 2:
                    continue
                box, text_info = item[0], item[1]
                text = str(text_info[0] if text_info else "").strip()
                confidence = float(text_info[1]) if text_info and len(text_info) > 1 else 0
                if not text:
                    continue
                lines.append(text)
                blocks.append({"text": text, "confidence": confidence, "box": box})
        if not lines:
            raise OCRError("OCR 未识别到可用文字，请改用 Excel 导入")
        return OCRResult(provider=self.name, text="\n".join(lines), blocks=blocks)


def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    provider = settings.ocr_provider.strip().lower()
    if provider in {"local_paddleocr", "paddleocr"}:
        return PaddleOCRProvider(settings.ocr_lang)
    return DisabledOCRProvider()
