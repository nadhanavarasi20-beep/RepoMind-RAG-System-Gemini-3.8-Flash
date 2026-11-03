import re
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi

CAMEL_CASE_SPLIT = re.compile(r"([a-z])([A-Z])")
NON_ALPHANUM = re.compile(r"[^a-zA-Z0-9_]+")

def code_tokenize(text: str) -> List[str]:
    """
    Code-aware tokenizer that splits camelCase, snake_case, dot.notation,
    and preserves both compound tokens and individual sub-words.
    """
    tokens: List[str] = []
    
    # First split on whitespace and punctuation
    raw_words = NON_ALPHANUM.split(text)
    
    for word in raw_words:
        if not word or len(word) < 2:
            continue
            
        lower_word = word.lower()
        tokens.append(lower_word)
        
        # Split snake_case
        if "_" in word:
            parts = [p.lower() for p in word.split("_") if len(p) >= 2]
            tokens.extend(parts)
            
        # Split camelCase
        camel_split = CAMEL_CASE_SPLIT.sub(r"\1 \2", word)
        if " " in camel_split:
            subparts = [p.lower() for p in camel_split.split() if len(p) >= 2]
            tokens.extend(subparts)
            
    return tokens

class RepoBM25Index:
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        self.corpus_tokens = [code_tokenize(c.get("content", "") + " " + (c.get("file_path", "") or "") + " " + (c.get("symbol_name", "") or "")) for c in chunks]
        if self.corpus_tokens and any(len(t) > 0 for t in self.corpus_tokens):
            self.bm25 = BM25Okapi(self.corpus_tokens)
        else:
            self.bm25 = None

    def search(self, query: str, top_k: int = 10) -> List[Tuple[Dict[str, Any], float]]:
        if not self.bm25 or not self.chunks:
            return []
            
        tokenized_query = code_tokenize(query)
        if not tokenized_query:
            return []
            
        scores = self.bm25.get_scores(tokenized_query)
        scored_pairs = [(self.chunks[i], float(scores[i])) for i in range(len(self.chunks))]
        # Sort descending by score
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]
