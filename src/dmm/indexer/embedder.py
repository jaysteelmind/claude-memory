"""Composite embedding generation for memory files."""

from dataclasses import dataclass
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from dmm.core.constants import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from dmm.core.exceptions import EmbeddingError
from dmm.models.memory import MemoryFile


@dataclass
class MemoryEmbedding:
    """Embedding result for a memory file."""

    memory_id: str
    composite_embedding: list[float]
    directory_embedding: list[float]
    composite_text: str

    @property
    def composite_array(self) -> np.ndarray:
        """Get composite embedding as numpy array."""
        return np.array(self.composite_embedding, dtype=np.float32)

    @property
    def directory_array(self) -> np.ndarray:
        """Get directory embedding as numpy array."""
        return np.array(self.directory_embedding, dtype=np.float32)


class MemoryEmbedder:
    """Generates composite embeddings for memory files."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        device: str | None = None,
    ) -> None:
        """
        Initialize embedder with specified model.

        Args:
            model_name: Name of the sentence-transformers model
            device: Device to use ('cpu', 'cuda', etc). None for auto-detect.
        """
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        # Default to CPU to avoid CUDA compatibility issues
        self._device = device if device is not None else "cpu"

    def _ensure_model_loaded(self) -> SentenceTransformer:
        """Lazy load the model on first use."""
        if self._model is None:
            try:
                self._model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                )
            except Exception as e:
                raise EmbeddingError(
                    f"Failed to load embedding model '{self._model_name}': {e}",
                    details={"model": self._model_name},
                ) from e
        return self._model

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return EMBEDDING_DIMENSION

    def embed_memory(self, memory: MemoryFile) -> MemoryEmbedding:
        """
        Generate composite embedding for a memory.

        The composite format combines structural and content information:
        [DIRECTORY] {directory}
        [TITLE] {title}
        [TAGS] {tags}
        [SCOPE] {scope}
        [CONTENT] {body}
        """
        composite_text = self._build_composite_text(memory)
        directory_text = self._build_directory_text(memory.directory)

        model = self._ensure_model_loaded()

        try:
            # Embed both texts in a single batch for efficiency
            embeddings = model.encode(
                [composite_text, directory_text],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            return MemoryEmbedding(
                memory_id=memory.id,
                composite_embedding=embeddings[0].tolist(),
                directory_embedding=embeddings[1].tolist(),
                composite_text=composite_text,
            )
        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate embedding for memory '{memory.id}': {e}",
                details={"memory_id": memory.id, "path": memory.path},
            ) from e

    def embed_directory(self, directory: str, description: str = "") -> list[float]:
        """Generate embedding for a directory path."""
        text = self._build_directory_text(directory, description)
        model = self._ensure_model_loaded()

        try:
            embedding = model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return embedding.tolist()
        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate directory embedding: {e}",
                details={"directory": directory},
            ) from e

    def embed_query(self, query: str) -> list[float]:
        """Embed a query string."""
        model = self._ensure_model_loaded()

        try:
            embedding = model.encode(
                query,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return embedding.tolist()
        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate query embedding: {e}",
                details={"query": query[:100]},
            ) from e

    def embed_batch(self, memories: list[MemoryFile]) -> list[MemoryEmbedding]:
        """Batch embed multiple memories for efficiency."""
        if not memories:
            return []

        model = self._ensure_model_loaded()

        # Build all texts
        composite_texts = [self._build_composite_text(m) for m in memories]
        directory_texts = [self._build_directory_text(m.directory) for m in memories]

        # Combine for single batch encode
        all_texts = composite_texts + directory_texts

        try:
            all_embeddings = model.encode(
                all_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=len(memories) > 10,
            )

            # Split results
            composite_embeddings = all_embeddings[: len(memories)]
            directory_embeddings = all_embeddings[len(memories) :]

            return [
                MemoryEmbedding(
                    memory_id=memory.id,
                    composite_embedding=comp_emb.tolist(),
                    directory_embedding=dir_emb.tolist(),
                    composite_text=comp_text,
                )
                for memory, comp_emb, dir_emb, comp_text in zip(
                    memories, composite_embeddings, directory_embeddings, composite_texts
                )
            ]
        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate batch embeddings: {e}",
                details={"batch_size": len(memories)},
            ) from e

    def compute_similarity(
        self,
        query_embedding: list[float],
        memory_embedding: list[float],
    ) -> float:
        """Compute cosine similarity between embeddings."""
        query_arr = np.array(query_embedding, dtype=np.float32)
        memory_arr = np.array(memory_embedding, dtype=np.float32)

        # Embeddings are already normalized, so dot product = cosine similarity
        similarity = float(np.dot(query_arr, memory_arr))

        # Clamp to valid range
        return max(0.0, min(1.0, similarity))

    def _build_composite_text(self, memory: MemoryFile) -> str:
        """Build the composite text for embedding."""
        parts = [
            f"[DIRECTORY] {memory.directory}",
            f"[TITLE] {memory.title}",
            f"[TAGS] {', '.join(memory.tags)}",
            f"[SCOPE] {memory.scope.value}",
            f"[CONTENT] {memory.body}",
        ]
        return "\n".join(parts)

    def _build_directory_text(self, directory: str, description: str = "") -> str:
        """Build text representation of a directory for embedding."""
        # Convert path to semantic text
        # e.g., "project/constraints" -> "project constraints"
        semantic_path = directory.replace("/", " ").replace("_", " ").replace("-", " ")

        if description:
            return f"{semantic_path}: {description}"
        return semantic_path

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        self._model = None

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model."""
        return {
            "model_name": self._model_name,
            "dimension": self.dimension,
            "loaded": self._model is not None,
            "device": self._device,
        }
