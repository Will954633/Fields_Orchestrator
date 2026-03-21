# Last Edit: 20/02/2026, Thursday (Brisbane Time)
# OpenAI GPT Vision client for property photo analysis.
# Replaces the former Ollama implementation - same interface, OpenAI backend.
"""
OpenAI GPT Vision client for property photo analysis.
Maintains the same interface as the former OllamaClientSingleImage so that
worker_multi.py requires no changes.
"""
import json
import time
import requests
import base64
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TIMEOUT, MAX_RETRIES, RETRY_DELAY
from logger import logger


class OllamaClientSingleImage:
    """Photo analysis client using OpenAI GPT Vision API."""

    def __init__(self):
        self.model = OPENAI_MODEL
        self.timeout = OPENAI_TIMEOUT
        self.api_key = OPENAI_API_KEY
        self.base_url = "https://api.openai.com/v1/chat/completions"

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        logger.info(f"Initialized OpenAI photo analysis client with model: {self.model}")

    def _download_and_encode_image(self, image_url):
        """Download image and return base64 data URI."""
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_data = base64.b64encode(response.content).decode("utf-8")
            return f"data:image/jpeg;base64,{image_data}"
        except Exception as e:
            logger.error(f"Failed to download image {image_url}: {e}")
            return None

    def _analyze_single_image(self, encoded_image, image_index):
        """Analyze a single image with OpenAI GPT Vision."""
        prompt = f"""Analyze this property image (image #{image_index}).

Provide a JSON response with:
{{
  "image_type": "exterior/interior/kitchen/bathroom/bedroom/living_room/outdoor/pool/garage/floor_plan/other",
  "description": "brief description of what the image shows",
  "usefulness_score": 1-10,
  "quality_score": 1-10,
  "marketing_value": "high/medium/low",
  "features_visible": ["list", "of", "visible", "features"]
}}

Return ONLY valid JSON, no other text."""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": encoded_image, "detail": "auto"},
                        },
                    ],
                }
            ],
            "max_completion_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

        try:
            response = requests.post(
                self.base_url, headers=headers, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            content = (
                response.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to analyze image {image_index}: {e}")
            return None

    def analyze_property_images(self, image_urls, address, max_images=5):
        """Analyze property images and return aggregated results."""
        images_to_use = image_urls[:max_images]
        logger.info(f"Analyzing {len(images_to_use)} images for {address}")

        start_time = time.time()
        image_analyses = []

        for idx, url in enumerate(images_to_use):
            logger.info(f"Processing image {idx + 1}/{len(images_to_use)}...")
            encoded = self._download_and_encode_image(url)
            if not encoded:
                logger.warning(f"Skipping image {idx} - download failed")
                continue
            analysis = self._analyze_single_image(encoded, idx)
            if analysis:
                analysis["image_index"] = idx
                analysis["url"] = url
                image_analyses.append(analysis)
                logger.info(
                    f"Image {idx}: {analysis.get('image_type', 'unknown')} - score {analysis.get('usefulness_score', 0)}/10"
                )

        elapsed = time.time() - start_time
        logger.info(f"Analyzed {len(image_analyses)} images in {elapsed:.1f}s")

        return {
            "image_analysis": image_analyses,
            "metadata": {
                "total_images_analyzed": len(image_analyses),
                "processing_time_seconds": elapsed,
            },
        }

    def extract_image_analysis(self, analysis_result, image_urls):
        """Extract and sort image analysis by usefulness score."""
        image_analysis = analysis_result.get("image_analysis", [])
        image_analysis.sort(key=lambda x: x.get("usefulness_score", 0), reverse=True)
        logger.info(f"Extracted {len(image_analysis)} image analyses")
        return image_analysis

    def extract_property_data(self, analysis_result):
        """Extract aggregated property data from image analyses."""
        image_analyses = analysis_result.get("image_analysis", [])

        all_features = []
        for img in image_analyses:
            all_features.extend(img.get("features_visible", []))

        return {
            "structural": {},
            "exterior": {},
            "interior": {},
            "renovation": {},
            "outdoor": {},
            "layout": {},
            "overall": {"unique_features": list(set(all_features))},
            "metadata": {
                "model_used": self.model,
                "extracted_at": time.time(),
                "analysis_engine": "openai",
                "analysis_method": "single_image_aggregation",
                "total_images_analyzed": len(image_analyses),
            },
        }
