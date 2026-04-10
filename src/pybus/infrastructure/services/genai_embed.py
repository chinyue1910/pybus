from typing import override

from google import genai
from google.genai.types import EmbedContentConfig

from ...application.services import EmbedService


class GenAIEmbedService(EmbedService):
    def __init__(self, gemini_api_key: str):
        self.client: genai.Client = genai.Client(api_key=gemini_api_key)

    @override
    def embed(self, content: str, output_dimensionality: int = 768) -> list[float]:
        response = self.client.models.embed_content(  # pyright: ignore[reportUnknownMemberType]
            model="gemini-embedding-2-preview",
            contents=content,
            config=EmbedContentConfig(output_dimensionality=output_dimensionality),
        )
        assert response.embeddings is not None and response.embeddings[0].values is not None
        return response.embeddings[0].values
