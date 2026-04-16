from app.services.structured_answer_service import StructuredAnswerService


def test_structured_answer_blocks_include_code_table_file_and_citations():
    text = (
        "Summary line.\n\n"
        "```sql\nselect 1;\n```\n\n"
        "| col1 | col2 |\n| --- | --- |\n| a | b |\n"
    )
    attachments = [
        {
            "file_name": "report.csv",
            "url": "https://example.local/files/123",
            "content_type": "text/csv",
            "size_bytes": 123,
        }
    ]
    rag_sources = [{"title": "Policy Doc", "uri": "kb://doc-1", "score": 0.9, "snippet": "sample"}]

    blocks = StructuredAnswerService().build_blocks(
        text=text,
        attachments=attachments,
        rag_sources=rag_sources,
    )
    block_types = [item["type"] for item in blocks]

    assert "bigstring" in block_types
    assert "code" in block_types
    assert "table" in block_types
    assert "file" in block_types
    assert "citations" in block_types


def test_structured_answer_table_parser_skips_invalid_table():
    blocks = StructuredAnswerService().build_blocks(text="No table here", attachments=[], rag_sources=[])
    assert all(item["type"] != "table" for item in blocks)


def test_build_grounding_score_from_rag_sources():
    payload = StructuredAnswerService().build_grounding(
        rag_sources=[{"score": 0.9}, {"score": 0.7}, {"score": 0.8}]
    )
    assert payload["citations_count"] == 3
    assert payload["mode"] == "strong"
    assert payload["score"] >= 0.8
