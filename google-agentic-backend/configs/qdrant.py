from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Any
import logfire
from configs.config import get_settings

settings = get_settings()

logger = logfire.configure()

qdrant_client = QdrantClient(
    url=settings.qdrant_creds.url, 
    api_key=settings.qdrant_creds.api_key.get_secret_value(),
)
class QdrantService:
    def __init__(self):
        self.client = qdrant_client
        self.collection_name = "workspace_data"
        self._ensure_collection()
    
    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
                )
                logger.info("Collection created successfully")
        except Exception as e:
            logger.error(f"Error ensuring collection: {str(e)}")
    
    async def add_vectors(self, points: List[PointStruct]):
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Added {len(points)} vectors to Qdrant")
        except Exception as e:
            logger.error(f"Error adding vectors: {str(e)}")
            raise
    
    async def search(self, query_vector: List[float], limit: int = 5, 
                    filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        try:
            search_params = {
                "collection_name": self.collection_name,
                "query_vector": query_vector,
                "limit": limit
            }
            
            if filter_dict:
                search_params["query_filter"] = filter_dict
            
            results = self.client.search(**search_params)
            
            logger.info(f"Found {len(results)} results from Qdrant search")
            
            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                }
                for result in results
            ]
        except Exception as e:
            logger.error(f"Error searching Qdrant: {str(e)}")
            return []
    
    async def delete_by_user(self, user_id: str):
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector={"filter": {"must": [{"key": "user_id", "match": {"value": user_id}}]}}
            )
            logger.info(f"Deleted vectors for user: {user_id}")
        except Exception as e:
            logger.error(f"Error deleting vectors: {str(e)}")