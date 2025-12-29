from googleapiclient.discovery import build
from typing import List, Dict, Any, Optional
import logfire
import base64
from email.mime.text import MIMEText
from datetime import datetime
import uuid
from qdrant_client.models import PointStruct
from configs.config import get_settings
from services.llm_service import get_async_openai_llm_client

settings = get_settings()

logger = logfire.configure()

class GmailService:
    def __init__(self, credentials, db_session, user_email, qdrant_service):
        self.service = build('gmail', 'v1', credentials=credentials)
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
            logger.error(f"[GmailService] Embedding generation error: {str(e)}")
            return [0.0] * 1536
    
    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search emails with semantic search fallback"""
        try:
            logger.info(f"[GmailService] Searching emails with query: {query}")
            
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.info("[GmailService] No results from Gmail API, trying semantic search")
                query_embedding = await self._generate_embedding(query)
                semantic_results = await self.qdrant.search(
                    query_vector=query_embedding,
                    limit=max_results,
                    filter_dict={"must": [{"key": "user_id", "match": {"value": self.user_email}}, {"key": "type", "match": {"value": "email"}}]}
                )
                
                email_list = []
                for result in semantic_results:
                    payload = result.get('payload', {})
                    email_list.append({
                        'id': payload.get('email_id'),
                        'subject': payload.get('subject'),
                        'from': payload.get('sender'),
                        'body_preview': payload.get('body_preview'),
                        'score': result.get('score')
                    })
                return email_list
            
            email_list = []
            for msg in messages:
                email_data = await self.get_email(msg['id'])
                email_list.append(email_data)
                await self._index_email(email_data)
            
            logger.info(f"[GmailService] Retrieved {len(email_list)} emails")
            return email_list
            
        except Exception as e:
            logger.error(f"[GmailService] Search error: {str(e)}")
            return []
    
    async def get_email(self, email_id: str) -> Dict:
        """Get full email content"""
        try:
            logger.info(f"[GmailService] Fetching email: {email_id}")
            
            message = self.service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute()
            
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            body = ''
            if 'parts' in message['payload']:
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        break
            elif 'body' in message['payload'] and 'data' in message['payload']['body']:
                body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8', errors='ignore')
            
            email_data = {
                'id': email_id,
                'subject': subject,
                'from': sender,
                'date': date,
                'body_preview': body[:500] if body else '',
                'body_full': body
            }
            
            logger.info(f"[GmailService] Email fetched: {subject}")
            return email_data
            
        except Exception as e:
            logger.error(f"[GmailService] Get email error: {str(e)}")
            return {'error': str(e)}
    
    async def send_email(self, to: str, subject: str, body: str) -> Dict:
        """Send an email"""
        try:
            logger.info(f"[GmailService] Sending email to: {to}")
            
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            logger.info(f"[GmailService] Email sent successfully: {result['id']}")
            return {
                'success': True,
                'message_id': result['id'],
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"[GmailService] Send email error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def draft_email(self, to: str, subject: str, body: str) -> Dict:
        """Create a draft email"""
        try:
            logger.info(f"[GmailService] Creating draft to: {to}")
            
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            draft = self.service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw}}
            ).execute()
            
            logger.info(f"[GmailService] Draft created: {draft['id']}")
            return {
                'success': True,
                'draft_id': draft['id'],
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"[GmailService] Draft error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def update_labels(self, email_id: str, add_labels: List[str] = None, remove_labels: List[str] = None) -> Dict:
        """Update labels on an email"""
        try:
            logger.info(f"[GmailService] Updating labels for: {email_id}")
            
            body = {}
            if add_labels:
                body['addLabelIds'] = add_labels
            if remove_labels:
                body['removeLabelIds'] = remove_labels
            
            result = self.service.users().messages().modify(
                userId='me',
                id=email_id,
                body=body
            ).execute()
            
            logger.info(f"[GmailService] Labels updated for: {email_id}")
            return {
                'success': True,
                'email_id': email_id,
                'labels_added': add_labels or [],
                'labels_removed': remove_labels or []
            }
            
        except Exception as e:
            logger.error(f"[GmailService] Update labels error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def _index_email(self, email_data: Dict):
        """Index email in Qdrant for semantic search"""
        try:
            text_to_embed = f"{email_data.get('subject', '')} {email_data.get('body_preview', '')}"
            embedding = await self._generate_embedding(text_to_embed)
            
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "user_id": self.user_email,
                    "type": "email",
                    "email_id": email_data.get('id'),
                    "subject": email_data.get('subject'),
                    "sender": email_data.get('from'),
                    "body_preview": email_data.get('body_preview'),
                    "date": email_data.get('date')
                }
            )
            
            await self.qdrant.add_vectors([point])
            logger.info(f"[GmailService] Email indexed: {email_data.get('id')}")
            
        except Exception as e:
            logger.error(f"[GmailService] Indexing error: {str(e)}")