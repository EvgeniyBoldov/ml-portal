import pytest

from app.schemas.common import ChunkProfile
from app.workers.helpers import chunker, generate_chunk_id


@pytest.mark.parametrize(
    "profile,text",
    [
        (ChunkProfile.BY_SENTENCES, "First sentence. Second sentence. Third sentence."),
        (ChunkProfile.BY_PARAGRAPHS, "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."),
        (ChunkProfile.BY_MARKDOWN, "# One\nfirst section\n## Two\nsecond section"),
    ],
)
def test_structure_chunk_profiles_have_unique_monotonic_character_offsets(profile, text):
    chunks = chunker(text, profile=profile, chunk_size=2, overlap=0)

    assert chunks
    offsets = [(chunk["start_pos"], chunk["end_pos"]) for chunk in chunks]
    assert len(offsets) == len(set(offsets))
    assert all(start >= 0 and end > start for start, end in offsets)
    assert offsets == sorted(offsets)
    assert len({generate_chunk_id("00000000-0000-0000-0000-000000000001", start, end) for start, end in offsets}) == len(chunks)


def test_page_chunking_is_rejected_without_page_spans():
    with pytest.raises(ValueError, match="page spans"):
        chunker("plain text", profile=ChunkProfile.BY_PAGES)


def test_token_chunking_rejects_non_progressing_overlap():
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        chunker("one two three", profile=ChunkProfile.BY_TOKENS, chunk_size=2, overlap=2)
