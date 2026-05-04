import pytest
import asyncio
from unittest.mock import patch
from trimcp.extractors.dispatch import extract_with_fallback
from trimcp.extractors.chunking import chunk_structured, StructuredChunk
from trimcp.extractors.core import Section, empty_skipped

@patch("trimcp.extractors.dispatch.ensure_registered")
@patch("trimcp.extractors.dispatch._REGISTRY", new_callable=dict)
def test_extract_with_fallback_unsupported_extension(mock_registry, mock_ensure):
    # Test that unsupported extensions return a graceful skip instead of crashing
    result = asyncio.run(extract_with_fallback(b"dummy data", filename="test.unknownext"))
    assert result.skipped is True
    assert result.skip_reason == "unsupported_format"
    assert "unknown or unregistered extension" in result.warnings[0]

@patch("trimcp.extractors.dispatch.ensure_registered")
@patch("trimcp.extractors.dispatch._REGISTRY", new_callable=dict)
def test_extract_with_fallback_malformed_pdf(mock_registry, mock_ensure):
    # Mock the registry to have a failing PDF extractor
    async def mock_pdf_extractor(blob):
        raise ValueError("Malformed PDF bytes")
    
    mock_registry["pdf"] = mock_pdf_extractor
    
    # Test that a malformed PDF doesn't crash the system but returns a failure/skip
    result = asyncio.run(extract_with_fallback(b"not a real pdf", filename="test.pdf"))
    assert result.skipped is True
    assert result.skip_reason == "extraction_failed"
    assert len(result.warnings) > 0
    assert "Malformed PDF bytes" in result.warnings[0]

def test_chunk_structured_basic():
    sections = [
        Section(text="Short text.", structure_path="/p", section_type="paragraph", order=0)
    ]
    chunks = chunk_structured(sections, max_chars=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == "Short text."
    assert chunks[0].structure_path == "/p"
    assert chunks[0].source_order == 0

def test_chunk_structured_long_text_split():
    # Create a long text with paragraphs
    para1 = "A" * 60
    para2 = "B" * 60
    text = f"{para1}\n\n{para2}"
    
    sections = [
        Section(text=text, structure_path="/p", section_type="paragraph", order=0)
    ]
    
    # max_chars=100 means para1 (60) + \n\n (2) + para2 (60) = 122 > 100
    # So it should split into two chunks
    chunks = chunk_structured(sections, max_chars=100, overlap=0)
    
    assert len(chunks) == 2
    assert chunks[0].text == para1
    assert chunks[1].text == para2
    assert chunks[0].part_index == 0
    assert chunks[1].part_index == 1

def test_chunk_structured_no_cross_section_merging():
    # Ensure that two short sections are NOT merged into one chunk
    sections = [
        Section(text="Section 1", structure_path="/s1", section_type="h1", order=0),
        Section(text="Section 2", structure_path="/s2", section_type="h1", order=1)
    ]
    
    chunks = chunk_structured(sections, max_chars=1000, overlap=0)
    assert len(chunks) == 2
    assert chunks[0].text == "Section 1"
    assert chunks[1].text == "Section 2"
