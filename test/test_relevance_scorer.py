import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import math

from content_extractor.relevance_scorer import RelevanceScorer
from content_extractor.dom_treeSt import DOMTreeSt

# =================================================================
# relevance_scorer.py のテスト
# =================================================================

@pytest.fixture
def mock_relevance_scorer():
    """
    A fixture that provides a RelevanceScorer instance with mocked heavy dependencies.
    """
    with patch('sentence_transformers.SentenceTransformer') as MockSentenceTransformer:
        mock_model_instance = MagicMock()
        # The order of embeddings matters: query is encoded first, then items.
        mock_model_instance.encode.side_effect = [
            np.array([0.5, 0.6]),  # For query
            np.array([[0.1, 0.2], [0.3, 0.4]]) # For items
        ]
        MockSentenceTransformer.return_value = mock_model_instance
        
        scorer = RelevanceScorer()
        
        mock_tfidf_instance = MagicMock()
        scorer.tfidf_vectorizer = mock_tfidf_instance
        
        return scorer

@pytest.fixture
def sample_items():
    """A fixture for a list of DOMTreeSt items."""
    return [
        DOMTreeSt(text="first item about python"),
        DOMTreeSt(text="second item about javascript")
    ]

# --- Tests for score_relevance ---

def test_score_relevance_empty_list(mock_relevance_scorer):
    """Test score_relevance with an empty list of items."""
    result = mock_relevance_scorer.score_relevance("python", [])
    assert result == []

def test_score_relevance_calculation(mock_relevance_scorer, sample_items):
    """
    Test the hybrid score calculation by mocking the individual components.
    """
    query = "python"
    
    # The fixture now correctly mocks the encode method.
    # We only need to mock the functions called within the method.
    mock_relevance_scorer._calculate_jaccard = MagicMock(side_effect=[0.7, 0.1])
    mock_relevance_scorer.tfidf_vectorizer.fit_transform.return_value = "dummy_matrix"

    with patch('content_extractor.relevance_scorer.cosine_similarity', return_value=np.array([0.8, 0.2])) as mock_tfidf_sim, \
         patch('content_extractor.relevance_scorer.cos_sim', return_value=np.array([[0.9, 0.1]])) as mock_semantic_sim:

        updated_items = mock_relevance_scorer.score_relevance(query, sample_items)
        
        # Expected score for item 1: (0.2 * 0.7) + (0.3 * 0.8) + (0.5 * 0.9) = 0.14 + 0.24 + 0.45 = 0.83
        assert updated_items[0].relevance_score == pytest.approx(0.83)
        # Expected score for item 2: (0.2 * 0.1) + (0.3 * 0.2) + (0.5 * 0.1) = 0.02 + 0.06 + 0.05 = 0.13
        assert updated_items[1].relevance_score == pytest.approx(0.13)

        assert mock_relevance_scorer._calculate_jaccard.call_count == 2
        mock_tfidf_sim.assert_called_once()
        mock_semantic_sim.assert_called_once()


# --- Tests for _calculate_jaccard ---

def test_calculate_jaccard(mock_relevance_scorer):
    text1 = "hello world from python"
    text2 = "hello python universe"
    # Intersection: {"hello", "python"} (2)
    # Union: {"hello", "world", "from", "python", "universe"} (5)
    # Jaccard = 2 / 5 = 0.4
    assert mock_relevance_scorer._calculate_jaccard(text1, text2) == pytest.approx(0.4)

def test_calculate_jaccard_no_common_words(mock_relevance_scorer):
    assert mock_relevance_scorer._calculate_jaccard("a b c", "d e f") == 0.0

def test_calculate_jaccard_empty_strings(mock_relevance_scorer):
    assert mock_relevance_scorer._calculate_jaccard("", "") == 0.0


# --- Tests for calculate_sqs ---

def test_calculate_sqs_no_results(mock_relevance_scorer):
    """Test SQS calculation when there are no results."""
    score, category = mock_relevance_scorer.calculate_sqs(0, 0, 0, 0)
    assert score == 0
    assert category == "Invalid/Empty"

def test_calculate_sqs_valid_score(mock_relevance_scorer):
    """Test SQS calculation resulting in a 'Valid' score."""
    with patch.dict('content_extractor.relevance_scorer.QUALITY_SCORING_CONFIG', {"sqs_thresholds": {"valid": 60, "low_quality": 20}, "sqs_weights": {"result_count": 0.2, "avg_relevance": 0.4, "relevance_variance": 0.2, "max_relevance": 0.2}}):
        score, category = mock_relevance_scorer.calculate_sqs(
            result_count=10,
            avg_relevance=0.8,
            relevance_variance=0.1,
            max_relevance=0.9
        )
        assert score > 60
        assert category == "Valid"

def test_calculate_sqs_low_quality_score(mock_relevance_scorer):
    """Test SQS calculation resulting in a 'Low Quality' score."""
    with patch.dict('content_extractor.relevance_scorer.QUALITY_SCORING_CONFIG', {"sqs_thresholds": {"valid": 60, "low_quality": 20}, "sqs_weights": {"result_count": 0.2, "avg_relevance": 0.4, "relevance_variance": 0.2, "max_relevance": 0.2}}):
        score, category = mock_relevance_scorer.calculate_sqs(
            result_count=3,
            avg_relevance=0.4,
            relevance_variance=0.3,
            max_relevance=0.5
        )
        assert 20 <= score < 60
        assert category == "Low Quality"

def test_calculate_sqs_invalid_score(mock_relevance_scorer):
    """Test SQS calculation resulting in an 'Invalid/Empty' score."""
    with patch.dict('content_extractor.relevance_scorer.QUALITY_SCORING_CONFIG', {"sqs_thresholds": {"valid": 60, "low_quality": 20}, "sqs_weights": {"result_count": 0.2, "avg_relevance": 0.4, "relevance_variance": 0.2, "max_relevance": 0.2}}):
        score, category = mock_relevance_scorer.calculate_sqs(
            result_count=1,
            avg_relevance=0.1,
            relevance_variance=0.5,
            max_relevance=0.2
        )
        assert score < 20
        assert category == "Invalid/Empty"

def test_calculate_sqs_negative_score_becomes_zero(mock_relevance_scorer):
    """Test that a calculated negative score is floored at 0."""
    # These values should produce a negative score before the max(0, sqs) check
    # sqs = (log(2)*0.2 + 0.1*0.4 - 1.0*0.2 + 0.1*0.2) * 100
    #     = (0.1386 + 0.04 - 0.2 + 0.02) * 100 = -0.14
    score, category = mock_relevance_scorer.calculate_sqs(
        result_count=1,
        avg_relevance=0.1,
        relevance_variance=1.0, # very high variance
        max_relevance=0.1
    )
    assert score == 0