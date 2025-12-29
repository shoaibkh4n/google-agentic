from googleapiclient.discovery import build
from typing import List, Dict, Any, Optional
import logfire
from datetime import datetime
import uuid
from qdrant_client.models import PointStruct
from services.llm_service import get_async_openai_llm_client
from configs.config import get_settings
import traceback
settings = get_settings()

logger = logfire.configure()

class CalendarService:
    def __init__(self, credentials, db_session, user_email, qdrant_service):
        self.service = build('calendar', 'v3', credentials=credentials)
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
            logger.error(f"[CalendarService] Embedding generation error: {str(e)}")
            return [0.0] * 1536
        
    async def search_events(self, query: str, time_min: Optional[str] = None, 
                        time_max: Optional[str] = None, max_results: int = 10) -> List[Dict]:
        """Search calendar events"""
        try:
            logger.info(f"[CalendarService] Searching events with query: '{query}'")
            
            clean_query = query.replace(" OR ", " ").replace(" AND ", " ").replace(" NOT ", " ")
            clean_query = clean_query.replace("(", "").replace(")", "").strip()
            
            # Take only the first few keywords
            keywords = [k for k in clean_query.split() if len(k) > 2][:3]
            simple_query = " ".join(keywords) if keywords else ""
            
            logger.info(f"[CalendarService] Cleaned query: '{simple_query}'")
            
            params = {
                'calendarId': 'primary',
                'maxResults': max_results,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            
            if simple_query and len(simple_query) > 0:
                params['q'] = simple_query
            
            if time_min:
                if not time_min.endswith('Z'):
                    time_min = time_min.replace('+00:00', 'Z')
                    if 'T' in time_min and not time_min.endswith('Z'):
                        time_min += 'Z'
                params['timeMin'] = time_min
            else:
                params['timeMin'] = datetime.utcnow().isoformat() + 'Z'
                
            if time_max:
                if not time_max.endswith('Z'):
                    time_max = time_max.replace('+00:00', 'Z')
                    if 'T' in time_max and not time_max.endswith('Z'):
                        time_max += 'Z'
                params['timeMax'] = time_max
            
            logger.info(f"[CalendarService] Calendar API params: {params}")
            
            try:
                events_result = self.service.events().list(**params).execute()
                events = events_result.get('items', [])
                logger.info(f"[CalendarService] Calendar API returned {len(events)} events")
            except Exception as api_error:
                logger.warning(f"[CalendarService] Calendar API failed, trying without query parameter: {str(api_error)}")
                if 'q' in params:
                    del params['q']
                    try:
                        events_result = self.service.events().list(**params).execute()
                        events = events_result.get('items', [])
                        logger.info(f"[CalendarService] Calendar API (without query) returned {len(events)} events")
                    except Exception as retry_error:
                        logger.error(f"[CalendarService] Calendar API failed again: {str(retry_error)}")
                        events = []
                else:
                    logger.error(f"[CalendarService] Calendar API error: {str(api_error)}")
                    events = []
            
            if not events:
                logger.info("[CalendarService] No results from Calendar API, trying semantic search")
                try:
                    query_embedding = await self._generate_embedding(query if query else "calendar event")
                    
                    search_filter = {
                        "must": [
                            {"key": "user_id", "match": {"value": self.user_email}},
                            {"key": "type", "match": {"value": "event"}}
                        ]
                    }
                    
                    semantic_results = await self.qdrant.search(
                        query_vector=query_embedding,
                        limit=max_results,
                        filter_dict=search_filter
                    )
                    
                    event_list = []
                    for result in semantic_results:
                        payload = result.get('payload', {})
                        event_list.append({
                            'id': payload.get('event_id'),
                            'summary': payload.get('summary', 'Untitled Event'),
                            'description': payload.get('description', ''),
                            'start': payload.get('start_time'),
                            'end': payload.get('end_time'),
                            'attendees': payload.get('attendees', []),
                            'location': payload.get('location', ''),
                            'score': result.get('score')
                        })
                    
                    logger.info(f"[CalendarService] Semantic search returned {len(event_list)} events")
                    return event_list
                except Exception as semantic_error:
                    logger.error(f"[CalendarService] Semantic search failed: {str(semantic_error)}")
                    return []
            
            # Format, index events
            event_list = []
            for event in events:
                event_data = self._format_event(event)
                event_list.append(event_data)
                try:
                    await self._index_event(event_data)
                except Exception as index_error:
                    logger.warning(f"[CalendarService] Failed to index event: {str(index_error)}")
            
            logger.info(f"[CalendarService] Successfully processed {len(event_list)} events")
            return event_list
            
        except Exception as e:
            logger.error(f"[CalendarService] Search error: {str(e)}")
            
            # Final fallback to semantic search
            try:
                logger.info("[CalendarService] Final fallback to semantic search")
                query_embedding = await self._generate_embedding(query if query else "calendar event")
                
                search_filter = {
                    "must": [
                        {"key": "user_id", "match": {"value": self.user_email}},
                        {"key": "type", "match": {"value": "event"}}
                    ]
                }
                
                semantic_results = await self.qdrant.search(
                    query_vector=query_embedding,
                    limit=max_results,
                    filter_dict=search_filter
                )
                
                event_list = []
                for result in semantic_results:
                    payload = result.get('payload', {})
                    event_list.append({
                        'id': payload.get('event_id'),
                        'summary': payload.get('summary', 'Untitled Event'),
                        'description': payload.get('description', ''),
                        'start': payload.get('start_time'),
                        'end': payload.get('end_time'),
                        'attendees': payload.get('attendees', []),
                        'location': payload.get('location', ''),
                        'score': result.get('score')
                    })
                
                logger.info(f"[CalendarService] Fallback semantic search returned {len(event_list)} events")
                return event_list
            except Exception as fallback_error:
                logger.error(f"[CalendarService] All search methods failed: {str(fallback_error)}")
                return []
    async def get_event(self, event_id: str) -> Dict:
        """Get event details"""
        try:
            logger.info(f"[CalendarService] Fetching event: {event_id}")
            
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            event_data = self._format_event(event)
            logger.info(f"[CalendarService] Event fetched: {event_data.get('summary')}")
            return event_data
            
        except Exception as e:
            logger.error(f"[CalendarService] Get event error: {str(e)}")
            return {'error': str(e)}
    
    async def create_event(self, summary: str, start_time: str, end_time: str, 
                          description: str = "", attendees: List[str] = None) -> Dict:
        """Create a new calendar event"""
        try:
            logger.info(f"[CalendarService] Creating event: {summary}")
            
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'UTC'
                }
            }
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            result = self.service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            event_data = self._format_event(result)
            await self._index_event(event_data)
            
            logger.info(f"[CalendarService] Event created: {result['id']}")
            return {
                'success': True,
                'event_id': result['id'],
                'summary': summary,
                'link': result.get('htmlLink')
            }
            
        except Exception as e:
            logger.error(f"[CalendarService] Create event error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def update_event(self, event_id: str, **updates) -> Dict:
        """Update an existing event"""
        try:
            logger.info(f"[CalendarService] Updating event: {event_id}")
            
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            event.update(updates)
            
            result = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"[CalendarService] Event updated: {event_id}")
            return {
                'success': True,
                'event_id': result['id'],
                'updated_fields': list(updates.keys())
            }
            
        except Exception as e:
            logger.error(f"[CalendarService] Update event error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def delete_event(self, event_id: str) -> Dict:
        """Delete a calendar event"""
        try:
            logger.info(f"[CalendarService] Deleting event: {event_id}")
            
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            logger.info(f"[CalendarService] Event deleted: {event_id}")
            return {
                'success': True,
                'event_id': event_id,
                'message': 'Event deleted successfully'
            }
            
        except Exception as e:
            logger.error(f"[CalendarService] Delete event error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _format_event(self, event: Dict) -> Dict:
        """Format event data"""
        return {
            'id': event['id'],
            'summary': event.get('summary', ''),
            'description': event.get('description', ''),
            'start': event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
            'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
            'attendees': [a.get('email') for a in event.get('attendees', [])],
            'link': event.get('htmlLink', ''),
            'location': event.get('location', '')
        }
    
    async def _index_event(self, event_data: Dict):
        """Index event in Qdrant for semantic search"""
        try:
            text_to_embed = f"{event_data.get('summary', '')} {event_data.get('description', '')}"
            embedding = await self._generate_embedding(text_to_embed)
            
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "user_id": self.user_email,
                    "type": "event",
                    "event_id": event_data.get('id'),
                    "summary": event_data.get('summary'),
                    "description": event_data.get('description'),
                    "start_time": event_data.get('start'),
                    "end_time": event_data.get('end'),
                    "attendees": event_data.get('attendees', [])
                }
            )
            
            await self.qdrant.add_vectors([point])
            logger.info(f"[CalendarService] Event indexed: {event_data.get('id')}")
            
        except Exception as e:
            logger.error(f"[CalendarService] Indexing error: {str(e)}")