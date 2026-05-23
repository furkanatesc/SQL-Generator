import unittest
import numpy as np
from typing import List
from app.schema_embedding import SchemaEmbeddingIndex

class MockEmbeddingClient:
    def __init__(self):
        self.model = "mock-embedder"
        
    def get_embedding(self, text: str, api_key: str = None) -> List[float]:
        if "ülke" in text:
            return [1.0, 0.0, 0.0]
        elif "sipariş" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]
        
    def get_embeddings_batch(self, texts: List[str], api_key: str = None) -> List[List[float]]:
        results = []
        for text in texts:
            if "COUNTRY" in text:
                results.append([0.9, 0.1, 0.0]) # "ülke" ile benzer
            elif "ORDER_ID" in text:
                results.append([0.1, 0.9, 0.0]) # "sipariş" ile benzer
            else:
                results.append([0.0, 0.1, 0.9])
        return results

class TestSchemaEmbeddingIndex(unittest.TestCase):
    def setUp(self):
        self.client = MockEmbeddingClient()
        self.embedder = SchemaEmbeddingIndex(embedding_client=self.client)
        
    def test_cosine_similarity(self):
        v1 = [1.0, 0.0]
        v2 = [1.0, 0.0]
        v3 = [0.0, 1.0]
        
        self.assertAlmostEqual(self.embedder.cosine_similarity(v1, v2), 1.0)
        self.assertAlmostEqual(self.embedder.cosine_similarity(v1, v3), 0.0)
        
    def test_build_index(self):
        schema = {
            "tables": {
                "CUSTOMERS": {
                    "columns": [{"name": "CUSTOMER_ID"}, {"name": "COUNTRY"}]
                },
                "ORDERS": {
                    "columns": [{"name": "ORDER_ID"}]
                }
            }
        }
        
        embeddings = self.embedder.build_index(schema)
        self.assertIn("CUSTOMERS", embeddings)
        self.assertIn("ORDERS", embeddings)
        self.assertEqual(len(embeddings["CUSTOMERS"]), 3)
        
    def test_find_relevant_tables(self):
        # CUSTOMERS is closer to "ülke" (1.0, 0.0, 0.0) vs (0.9, 0.1, 0.0) -> high sim
        # ORDERS is closer to "sipariş" (0.0, 1.0, 0.0) vs (0.1, 0.9, 0.0)
        table_embeddings = {
            "CUSTOMERS": [0.9, 0.1, 0.0],
            "ORDERS": [0.1, 0.9, 0.0],
            "PRODUCTS": [0.0, 0.1, 0.9]
        }
        
        relevant = self.embedder.find_relevant_tables("ülkeler", table_embeddings, top_k=2)
        # "ülke" -> returns [1.0, 0.0, 0.0] in our mock
        # sim(CUSTOMERS) = (0.9*1.0) / (1 * ~0.905) = 0.99
        self.assertTrue(len(relevant) > 0)
        self.assertEqual(relevant[0][0], "CUSTOMERS")
        
if __name__ == '__main__':
    unittest.main()
