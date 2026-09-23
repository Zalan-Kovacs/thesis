from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embedding(text: str) -> list[float]:
    """From text generates a 384 dimenson vector."""
    return model.encode(text).tolist()

def get_embeddings_batch(texts: list[str]) -> list[float]:
    """For more text at the same time."""
    return model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
