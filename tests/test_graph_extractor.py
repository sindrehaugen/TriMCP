import pytest
from unittest.mock import patch, MagicMock
from trimcp.graph_extractor import extract, _spacy_extract, _regex_extract, Entity, Triplet

def test_regex_extract():
    text = "Redis connects to PostgreSQL"
    entities, triplets = _regex_extract(text)
    
    assert len(entities) >= 2
    assert any(e.label.lower() == "redis" for e in entities)
    assert any(e.label.lower() == "postgresql" for e in entities)
    
    assert len(triplets) == 1
    assert triplets[0].subject.lower() == "redis"
    assert triplets[0].predicate == "connects to"
    assert triplets[0].obj.lower() == "postgresql"

@patch("trimcp.graph_extractor._spacy_extract")
def test_extract_uses_spacy(mock_spacy):
    mock_entities = [Entity(label="A", entity_type="CONCEPT", source_text="A")]
    mock_triplets = [Triplet(subject="A", predicate="is", obj="B")]
    mock_spacy.return_value = (mock_entities, mock_triplets)
    
    text = "A is B"
    entities, triplets = extract(text)
    
    mock_spacy.assert_called_once_with(text)
    assert entities == mock_entities
    assert triplets == mock_triplets

@patch("trimcp.graph_extractor._spacy_extract")
@patch("trimcp.graph_extractor._regex_extract")
def test_extract_falls_back_to_regex(mock_regex, mock_spacy):
    mock_spacy.side_effect = ImportError("spacy not installed")
    
    mock_entities = [Entity(label="A", entity_type="CONCEPT", source_text="A")]
    mock_triplets = [Triplet(subject="A", predicate="is", obj="B")]
    mock_regex.return_value = (mock_entities, mock_triplets)
    
    text = "A is B"
    entities, triplets = extract(text)
    
    mock_spacy.assert_called_once_with(text)
    mock_regex.assert_called_once_with(text)
    assert entities == mock_entities
    assert triplets == mock_triplets
