from googleapiclient.discovery import build
from typing import List, Dict, Any, Optional
import logfire
from datetime import datetime
import uuid
from qdrant_client.models import PointStruct
from configs.config import get_settings
from services.llm_service import get_async_openai_llm_client
import traceback
import re

settings = get_settings()
logger = logfire.configure()

class DriveService:
    def __init__(self, credentials, db_session, user_email, qdrant_service):
        self.service = build('drive', 'v3', credentials=credentials)
        self.db = db_session
        self.user_email = user_email
        self.qdrant = qdrant_service
        self.openai_client = get_async_openai_llm_client()
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI"""
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"[DriveService] Embedding generation error: {str(e)}")
            return [0.0] * 1536
    
    async def search_files(self, query: str, mime_type: Optional[str] = None, 
                        max_results: int = 10) -> List[Dict]:
        """Search files in Google Drive"""
        try:
            logger.info(f"[DriveService] Searching files with query: {query}")
            
            query_parts = []
            
            query_lower = query.lower()
            if "mimetype" in query_lower or "mime_type" in query_lower:
                if "pdf" in query_lower or "application/pdf" in query:
                    mime_type = "application/pdf"
                elif "doc" in query_lower or "document" in query_lower:
                    mime_type = "application/vnd.google-apps.document"
                elif "sheet" in query_lower or "spreadsheet" in query_lower:
                    mime_type = "application/vnd.google-apps.spreadsheet"
                elif "slide" in query_lower or "presentation" in query_lower:
                    mime_type = "application/vnd.google-apps.presentation"
            
            
            time_min_match = re.search(r"modifiedTime\s*>=\s*['\"]([^'\"]+)['\"]", query)
            time_min = time_min_match.group(1) if time_min_match else None
            
            time_max_match = re.search(r"modifiedTime\s*<=\s*['\"]([^'\"]+)['\"]", query)
            time_max = time_max_match.group(1) if time_max_match else None
            
            # Build Drive API query
            if mime_type:
                query_parts.append(f"mimeType='{mime_type}'")
            
            if time_min:
                query_parts.append(f"modifiedTime >= '{time_min}'")
            
            if time_max:
                query_parts.append(f"modifiedTime <= '{time_max}'")
            
            query_parts.append("trashed=false")
            
            drive_query = " and ".join(query_parts)
            
            logger.info(f"[DriveService] Executing Drive query: {drive_query}")
            
            results = self.service.files().list(
                q=drive_query,
                pageSize=max_results,
                fields='files(id, name, mimeType, modifiedTime, webViewLink, size, owners)',
                orderBy='modifiedTime desc'
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                logger.info("[DriveService] No results from Drive API, trying semantic search")
                try:
                    query_embedding = await self._generate_embedding(query)
                    
                    search_filter = {
                        "must": [
                            {"key": "user_id", "match": {"value": self.user_email}},
                            {"key": "type", "match": {"value": "file"}}
                        ]
                    }
                    
                    semantic_results = await self.qdrant.search(
                        query_vector=query_embedding,
                        limit=max_results,
                        filter_dict=search_filter
                    )
                    
                    file_list = []
                    for result in semantic_results:
                        payload = result.get('payload', {})
                        file_list.append({
                            'id': payload.get('file_id'),
                            'name': payload.get('name'),
                            'mime_type': payload.get('mime_type'),
                            'modified_time': payload.get('modified_time'),
                            'link': payload.get('link'),
                            'score': result.get('score')
                        })
                    
                    logger.info(f"[DriveService] Semantic search returned {len(file_list)} files")
                    return file_list
                except Exception as semantic_error:
                    logger.error(f"[DriveService] Semantic search failed: {str(semantic_error)}")
                    return []
            
            file_list = []
            for file in files:
                file_data = {
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file['mimeType'],
                    'modified_time': file['modifiedTime'],
                    'link': file.get('webViewLink', ''),
                    'size': file.get('size', 'N/A'),
                    'owners': [owner.get('emailAddress') for owner in file.get('owners', [])]
                }
                file_list.append(file_data)
                # Index asynchronously
                try:
                    await self._index_file(file_data)
                except Exception as index_error:
                    logger.warning(f"[DriveService] Failed to index file: {str(index_error)}")
            
            logger.info(f"[DriveService] Found {len(file_list)} files")
            return file_list
            
        except Exception as e:
            logger.error(f"[DriveService] Search error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            try:
                logger.info("[DriveService] Falling back to semantic search due to error")
                query_embedding = await self._generate_embedding(query)
                
                search_filter = {
                    "must": [
                        {"key": "user_id", "match": {"value": self.user_email}},
                        {"key": "type", "match": {"value": "file"}}
                    ]
                }
                
                semantic_results = await self.qdrant.search(
                    query_vector=query_embedding,
                    limit=max_results,
                    filter_dict=search_filter
                )
                
                file_list = []
                for result in semantic_results:
                    payload = result.get('payload', {})
                    file_list.append({
                        'id': payload.get('file_id'),
                        'name': payload.get('name'),
                        'mime_type': payload.get('mime_type'),
                        'modified_time': payload.get('modified_time'),
                        'link': payload.get('link'),
                        'score': result.get('score')
                    })
                
                logger.info(f"[DriveService] Fallback semantic search returned {len(file_list)} files")
                return file_list
            except Exception as fallback_error:
                logger.error(f"[DriveService] Semantic search also failed: {str(fallback_error)}")
                return []
            
    async def get_file(self, file_id: str) -> Dict:
        """Get file metadata"""
        try:
            logger.info(f"[DriveService] Fetching file: {file_id}")
            
            file = self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, modifiedTime, webViewLink, size, owners, description'
            ).execute()
            
            file_data = {
                'id': file['id'],
                'name': file['name'],
                'mime_type': file['mimeType'],
                'modified_time': file['modifiedTime'],
                'link': file.get('webViewLink', ''),
                'size': file.get('size', 'N/A'),
                'description': file.get('description', ''),
                'owners': [owner.get('emailAddress') for owner in file.get('owners', [])]
            }
            
            logger.info(f"[DriveService] File fetched: {file_data['name']}")
            return file_data
            
        except Exception as e:
            logger.error(f"[DriveService] Get file error: {str(e)}")
            return {'error': str(e)}
    
    async def share_file(self, file_id: str, email: str, role: str = "reader") -> Dict:
        """Share a file with someone"""
        try:
            logger.info(f"[DriveService] Sharing file {file_id} with {email}")
            
            permission = {
                'type': 'user',
                'role': role,
                'emailAddress': email
            }
            
            self.service.permissions().create(
                fileId=file_id,
                body=permission,
                sendNotificationEmail=False
            ).execute()
            
            logger.info(f"[DriveService] File shared successfully")
            return {
                'success': True,
                'file_id': file_id,
                'shared_with': email,
                'role': role
            }
            
        except Exception as e:
            logger.error(f"[DriveService] Share file error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def create_folder(self, folder_name: str, parent_folder_id: str = None) -> Dict:
        """Create a new folder"""
        try:
            logger.info(f"[DriveService] Creating folder: {folder_name}")
            
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id, name, webViewLink'
            ).execute()
            
            logger.info(f"[DriveService] Folder created: {folder['id']}")
            return {
                'success': True,
                'folder_id': folder['id'],
                'name': folder['name'],
                'link': folder.get('webViewLink', '')
            }
            
        except Exception as e:
            logger.error(f"[DriveService] Create folder error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def move_file(self, file_id: str, new_parent_id: str) -> Dict:
        """Move a file to another location"""
        try:
            logger.info(f"[DriveService] Moving file {file_id}")
            
            file = self.service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()
            
            previous_parents = ",".join(file.get('parents', []))
            
            file = self.service.files().update(
                fileId=file_id,
                addParents=new_parent_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
            logger.info(f"[DriveService] File moved successfully")
            return {
                'success': True,
                'file_id': file_id,
                'new_parent': new_parent_id
            }
            
        except Exception as e:
            logger.error(f"[DriveService] Move file error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def _index_file(self, file_data: Dict):
        """Index file in Qdrant for semantic search"""
        try:
            text_to_embed = f"{file_data.get('name', '')} {file_data.get('description', '')}"
            embedding = await self._generate_embedding(text_to_embed)
            
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "user_id": self.user_email,
                    "type": "file",
                    "file_id": file_data.get('id'),
                    "name": file_data.get('name'),
                    "mime_type": file_data.get('mime_type'),
                    "modified_time": file_data.get('modified_time'),
                    "link": file_data.get('link')
                }
            )
            
            await self.qdrant.add_vectors([point])
            logger.info(f"[DriveService] File indexed: {file_data.get('id')}")
            
        except Exception as e:
            logger.error(f"[DriveService] Indexing error: {str(e)}")