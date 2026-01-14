# Imports
import asyncio
import datetime
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

# 3rd party libraries - these need to be installed
# pip install -r requirements_search.txt
import backoff
from duckduckgo_search import AsyncDDGS
from duckduckgo_search.exceptions import RatelimitException, TimeoutException
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

# Local imports
from content_processorl import ContentProcessor

# --- Logger Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# PHASE 2: Robustness - Caching Layer
# ==============================================================================

class SearchCache:
    """
    A simple in-memory cache with Time-To-Live (TTL) support.
    Implements the 'cache-aside' pattern.
    """
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._ttl: Dict[str, datetime.datetime] = {}
        logger.info("In-memory cache initialized.")

    def _normalize_query(self, query: str) -> str:
        """
        Normalizes a query to be used as a cache key.
        Lowercase and sort words to maximize cache hits.
        """
        return " ".join(sorted(query.lower().split()))

    def get(self, query: str) -> Optional[List[Dict]]:
        """
        Retrieves a result from the cache if it exists and has not expired.
        """
        key = self._normalize_query(query)
        if key in self._cache:
            if datetime.datetime.now() < self._ttl[key]:
                logger.info(f"CACHE HIT for query: '{query}'")
                return self._cache[key]
            else:
                logger.info(f"CACHE EXPIRED for query: '{query}'")
                # Clean up expired entry
                del self._cache[key]
                del self._ttl[key]
        
        logger.info(f"CACHE MISS for query: '{query}'")
        return None

    def set(self, query: str, results: List[Dict], ttl_seconds: int = 3600):
        """
        Stores a result in the cache with a specified TTL.
        """
        key = self._normalize_query(query)
        self._cache[key] = results
        self._ttl[key] = datetime.datetime.now() + datetime.timedelta(seconds=ttl_seconds)
        logger.info(f"CACHE SET for query: '{query}' with TTL: {ttl_seconds}s")

# ==============================================================================
# PHASE 1 & 2: Baseline & Robustness - Resilient Search Client
# ==============================================================================

class ResilientSearchClient:
    """
    A robust search client for DuckDuckGo that handles rate limits
    with exponential backoff and implements a backend fallback strategy.
    """
    def __init__(self):
        self.backends = ['html', 'lite', 'bing']
        logger.info(f"ResilientSearchClient initialized with backends: {self.backends}")

    @backoff.on_exception(backoff.expo,
                          (RatelimitException, TimeoutException),
                          max_tries=3,
                          jitter=backoff.full_jitter)
    async def search(self,
                     query: str,
                     region: str = 'wt-wt',
                     safesearch: str = 'moderate',
                     timelimit: Optional[str] = None,
                     max_results: int = 50) -> List[Dict]:
        """
        Performs an asynchronous search with specified parameters.
        It tries different backends if one fails.
        """
        async with AsyncDDGS() as ddgs:
            for backend in self.backends:
                try:
                    logger.info(f"Searching '{query}' using backend: '{backend}'")
                    results = await ddgs.text(
                        keywords=query,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                        max_results=max_results,
                        backend=backend
                    )
                    if results:
                        logger.info(f"Found {len(results)} results with backend '{backend}'.")
                        return results
                except Exception as e:
                    logger.warning(f"Backend '{backend}' failed for query '{query}': {e}. Trying next backend.")
                    continue
        logger.error(f"All backends failed for query: '{query}'")
        return []

# ==============================================================================
# PHASE 3: Relevance - Query Enhancement
# ==============================================================================

def enhance_query(base_query: str, high_credibility_sources: bool = True) -> List[str]:
    """
    Generates multiple query variations from a base query.
    """
    # Example modifiers. This can be expanded significantly.
    modifiers = ["", "best", "tutorial", "for beginners", "review", "vs"]
    # Example operators.
    operators = ["", 'intitle:"{query}"']

    # Phase 1: Strategic query generation for high-credibility sources
    if high_credibility_sources:
        operators.extend([
            '"{query}" site:.gov',
            '"{query}" site:.edu',
            '"{query}" filetype:pdf'
        ])

    enhanced_queries = {base_query} # Use a set to avoid duplicates

    for mod in modifiers:
        enhanced_queries.add(f"{base_query} {mod}".strip())
        enhanced_queries.add(f"{mod} {base_query}".strip())

    for op_template in operators:
        if "{query}" in op_template:
            enhanced_queries.add(op_template.format(query=base_query))

    logger.info(f"Enhanced '{base_query}' into {len(enhanced_queries)} variations: {list(enhanced_queries)}")
    return list(enhanced_queries)

# ==============================================================================
# PHASE 3 & 4: Relevance & Precision - Re-ranking
# ==============================================================================

class ReRanker:
    """
    Handles lexical (BM25) and semantic (Cross-Encoder) re-ranking of search results.
    """
    def __init__(self, cross_encoder_model: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'):
        self.cross_encoder = None
        try:
            logger.info(f"Loading Cross-Encoder model: {cross_encoder_model}...")
            start_time = time.time()
            self.cross_encoder = CrossEncoder(cross_encoder_model)
            end_time = time.time()
            logger.info(f"Cross-Encoder model loaded in {end_time - start_time:.2f} seconds.")
        except Exception as e:
            logger.error(f"Failed to load Cross-Encoder model: {e}")
            logger.error("Please ensure 'sentence-transformers' and 'torch' are installed.")

    def lexical_rerank(self, query: str, documents: List[Dict], top_n: int = 100) -> List[Dict]:
        """
        Re-ranks documents using Okapi BM25.
        `documents` is a list of dicts, each with a 'body' key.
        """
        if not documents:
            return []
        
        logger.info(f"Performing BM25 re-ranking on {len(documents)} documents.")
        
        # We need the text content for BM25. 'body' is the most descriptive field.
        corpus = [doc.get('body', '') for doc in documents]
        tokenized_corpus = [doc.split(" ") for doc in corpus]
        tokenized_query = query.split(" ")

        bm25 = BM25Okapi(tokenized_corpus)
        doc_scores = bm25.get_scores(tokenized_query)

        # Combine scores with original documents
        for doc, score in zip(documents, doc_scores):
            doc['bm25_score'] = score

        # Sort by BM25 score in descending order
        reranked_docs = sorted(documents, key=lambda x: x.get('bm25_score', 0), reverse=True)
        
        logger.info("BM25 re-ranking complete.")
        return reranked_docs[:top_n]

    def semantic_rerank(self, query: str, documents: List[Dict], top_n: int = 25) -> List[Dict]:
        """
        Re-ranks documents using a Cross-Encoder model for semantic relevance.
        `documents` is a list of dicts, each with a 'body' key.
        """
        if not self.cross_encoder or not documents:
            logger.warning("Cross-Encoder not available or no documents to re-rank. Skipping semantic re-ranking.")
            return documents

        logger.info(f"Performing semantic re-ranking on {len(documents)} documents.")
        
        # The Cross-Encoder expects pairs of [query, document_text]
        sentence_pairs = [[query, doc.get('body', '')] for doc in documents]
        
        # Predict scores
        scores = self.cross_encoder.predict(sentence_pairs)

        # Combine scores with original documents
        for doc, score in zip(documents, scores):
            doc['semantic_score'] = score

        # Sort by semantic score in descending order
        reranked_docs = sorted(documents, key=lambda x: x.get('semantic_score', 0), reverse=True)
        
        logger.info("Semantic re-ranking complete.")
        return reranked_docs[:top_n]

# ==============================================================================
# FINAL SYSTEM: High-Precision Search System
# ==============================================================================

class HighPrecisionSearchSystem:
    """
    Orchestrates the entire high-precision search pipeline.
    """
    def __init__(self):
        self.cache = SearchCache()
        self.client = ResilientSearchClient()
        self.reranker = ReRanker()
        self.content_processor = ContentProcessor()
        self.executor = ThreadPoolExecutor(max_workers=10)
        logger.info("HighPrecisionSearchSystem initialized.")

    def _reciprocal_rank_fusion(self, ranked_lists: List[List[Dict]], k: int = 60) -> Dict[str, float]:
        """
        Performs Reciprocal Rank Fusion on multiple ranked lists.
        """
        rrf_scores: Dict[str, float] = {}
        for ranked_list in ranked_lists:
            for rank, item in enumerate(ranked_list):
                item_id = item.get('href')
                if not item_id:
                    continue
                if item_id not in rrf_scores:
                    rrf_scores[item_id] = 0
                rrf_scores[item_id] += 1 / (k + rank + 1)
        return rrf_scores

    async def _process_content_for_results(self, documents: List[Dict]) -> List[Dict]:
        """
        Asynchronously fetches and processes content for a list of search results.
        """
        loop = asyncio.get_running_loop()
        tasks = []

        for doc in documents:
            task = loop.run_in_executor(
                self.executor, self.content_processor.process_url, doc['href']
            )
            tasks.append(task)
        
        processed_contents = await asyncio.gather(*tasks)

        updated_docs = []
        for i, content_data in enumerate(processed_contents):
            original_doc = documents[i]
            if content_data:
                original_doc['body'] = content_data.get('text', original_doc.get('body', ''))
                original_doc['extracted_metadata'] = {
                    'author': content_data.get('author'),
                    'date': content_data.get('date'),
                    'sitename': content_data.get('sitename')
                }
                original_doc['credibility_score'] = content_data.get('credibility_score', 0.0)
            else:
                original_doc['credibility_score'] = 0.0
            updated_docs.append(original_doc)
        
        return updated_docs

    def generate_llm_prompt(self, query: str, ranked_documents: List[Dict]) -> str:
        """
        Generates a structured prompt for an LLM based on the final ranked documents.
        """
        context_str = ""
        for i, doc in enumerate(ranked_documents):
            context_str += f"--- Information Source {i+1} ---\n"
            context_str += f"Title: {doc.get('title', 'N/A')}\n"
            context_str += f"URL: {doc.get('href', 'N/A')}\n"
            context_str += f"Final Score: {doc.get('final_score', 'N/A'):.4f} (Credibility: {doc.get('credibility_score', 'N/A'):.2f})\n"
            context_str += f"Extracted Content:\n{doc.get('body', 'No content extracted.')}\n\n"

        return f"""You are a research assistant. Based on the following multiple sources of information, please provide a comprehensive answer to the user's question.

**Instructions:**
* When creating your answer, **prioritize information from sources with the highest credibility score**.
* If the content contradicts between sources, point out the contradiction and then **adopt the view of the source with the higher credibility score**.
* Clearly indicate which source each part of your answer is based on by citing it (e.g., [Source 1], [Source 2]).

**User Question:**\n{query}\n\n**Information Sources:**\n{context_str}\n**Your Answer:**"""

    async def search(self,
                     query: str,
                     region: str = 'us-en',
                     safesearch: str = 'moderate',
                     timelimit: Optional[str] = None,
                     use_enhancement: bool = True,
                     use_cache: bool = True,
                     lexical_top_n: int = 100,
                     semantic_top_n: int = 25
                     ) -> List[Dict]:
        """
        Executes the full search and re-ranking pipeline.
        """
        start_time = time.time()
        
        # 1. Input & 2. Query Enhancement
        if use_enhancement:
            queries = enhance_query(query)
        else:
            queries = [query]

        # 3. Parallel Search (with Caching)
        all_results = {}
        search_tasks = []

        for q in queries:
            if use_cache:
                cached_results = self.cache.get(q)
                if cached_results:
                    for res in cached_results:
                        all_results[res['href']] = res # Use href as a unique key to avoid duplicates
                    continue # Skip network call if cached
            
            task = self.client.search(
                query=q,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=lexical_top_n # Fetch enough results for re-ranking
            )
            search_tasks.append((q, task))

        # Execute non-cached searches in parallel
        if search_tasks:
            results_from_api = await asyncio.gather(*[task for _, task in search_tasks])
            
            # 4. Aggregate & Cache
            for (q, _), results in zip(search_tasks, results_from_api):
                if results:
                    if use_cache:
                        self.cache.set(q, results)
                    for res in results:
                        all_results[res['href']] = res

        aggregated_results = list(all_results.values())
        logger.info(f"Aggregated {len(aggregated_results)} unique results from {len(queries)} queries.")

        if not aggregated_results:
            return []

        # Phase 2: Content Extraction and Credibility Scoring
        logger.info(f"Processing content for {len(aggregated_results)} documents...")
        docs_with_content = await self._process_content_for_results(aggregated_results)
        logger.info("Content processing complete.")

        # Phase 3: Integrated Ranking
        # 5. 1st Re-ranking (Lexical)
        bm25_reranked = self.reranker.lexical_rerank(query, docs_with_content, top_n=lexical_top_n)

        # 6. 2nd Re-ranking (Semantic)
        semantic_reranked = self.reranker.semantic_rerank(query, bm25_reranked, top_n=semantic_top_n)

        # Create a credibility-ranked list
        credibility_reranked = sorted(docs_with_content, key=lambda x: x.get('credibility_score', 0), reverse=True)

        # 7. Final Score Fusion (RRF)
        rrf_scores = self._reciprocal_rank_fusion([bm25_reranked, semantic_reranked, credibility_reranked])

        for doc in docs_with_content:
            doc['final_score'] = rrf_scores.get(doc.get('href'), 0.0)
        
        final_results = sorted(docs_with_content, key=lambda x: x.get('final_score', 0.0), reverse=True)

        end_time = time.time()
        logger.info(f"Total search pipeline finished in {end_time - start_time:.2f} seconds.")
        
        return final_results[:semantic_top_n]

# ==============================================================================
# Example Usage
# ==============================================================================

async def main():
    """Main function to demonstrate the search system."""
    print("--- Initializing High-Precision Search System ---")
    search_system = HighPrecisionSearchSystem()
    
    print("\n--- Performing Search ---")
    # query_to_search = "python web scraping libraries"
    query_to_search = "best python framework for web development"
    
    results = await search_system.search(
        query=query_to_search,
        region='us-en',
        timelimit='y', # last year
        lexical_top_n=50, # Fetch 50 results for initial pool
        semantic_top_n=10 # Show top 10 final results
    )

    print(f"\n--- Top {len(results)} Search Results for '{query_to_search}' ---")
    if results:
        for i, res in enumerate(results):
            print(f"{i+1}. {res.get('title')}")
            print(f"   URL: {res.get('href')}")
            print(f"   BM25 Score: {res.get('bm25_score', 'N/A'):.4f}")
            print(f"   Semantic Score: {res.get('semantic_score', 'N/A'):.4f}")
            print(f"   Credibility Score: {res.get('credibility_score', 'N/A'):.4f}")
            print(f"   Final RRF Score: {res.get('final_score', 'N/A'):.4f}")
            # print(f"   Body: {res.get('body', '')[:150]}...") # Uncomment to see body snippet
            print("-" * 20)

        # Phase 4: Generate LLM Prompt
        print("\n--- Generating LLM Prompt ---")
        llm_prompt = search_system.generate_llm_prompt(query_to_search, results)
        print(llm_prompt)
    else:
        print("No results found.")

if __name__ == "__main__":
    # Note: The first run will be slower due to model download.
    asyncio.run(main())