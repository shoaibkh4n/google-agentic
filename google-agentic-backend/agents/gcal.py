from pydantic_ai import Agent, RunContext
from typing import List, Dict, Any
import logfire
from agents.deps import AgentDeps
from services.calender_service import CalendarService
from services.llm_service import get_model_client

logger = logfire.configure()

calendar_agent = Agent(
    model = get_model_client(),
    deps_type=AgentDeps,
    system_prompt="""You are a Google Calendar specialist agent. You help users manage their calendar events.

Available operations:
- search_events: Search for calendar events (use SIMPLE keywords only - no OR/AND operators)
- get_event_details: Get full details of a specific event
- create_event: Create a new calendar event (USE THIS when user asks to schedule, create, or add an event)
- update_event: Update an existing event
- delete_event: Delete a calendar event

CRITICAL INSTRUCTIONS FOR SEARCHING:
1. Use simple keyword searches only - Google Calendar doesn't support OR, AND, NOT operators
2. Use 1-3 keywords maximum (e.g., "flight" or "meeting client")
3. Specify time ranges when searching for events in specific periods

CRITICAL INSTRUCTIONS FOR CREATING EVENTS:
1. When user asks to "schedule", "create", "add", or "book" an event, you MUST call create_event tool
2. Extract all required parameters from the context provided
3. Convert dates/times to ISO format (YYYY-MM-DDTHH:MM:SS)
4. Always TAKE ACTION - don't just say you'll do something, actually call the tool
5. Use the context provided to extract meeting details (title, time, attendees, etc.)

Always provide clear information about calendar operations and CONFIRM what action was taken."""
)

@calendar_agent.tool
async def search_events(ctx: RunContext[AgentDeps], query: str, time_min: str = None, time_max: str = None, max_results: int = 50) -> List[Dict]:
    """Search for calendar events"""
    logger.info(f"[CalendarAgent] Searching events: {query}")
    
    service = CalendarService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    results = await service.search_events(query, time_min, time_max, max_results)
    logger.info(f"[CalendarAgent] Found {len(results)} events")
    print(f'[CalendarAgentSearch] Results: {results}')
    
    return results

@calendar_agent.tool
async def get_event_details(ctx: RunContext[AgentDeps], event_id: str) -> Dict:
    """Get full details of a specific event"""
    logger.info(f"[CalendarAgent] Fetching event: {event_id}")
    
    service = CalendarService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    return await service.get_event(event_id)

@calendar_agent.tool
async def create_event(ctx: RunContext[AgentDeps], summary: str, start_time: str, end_time: str, description: str = "", attendees: List[str] = None) -> Dict:
    """Create a new calendar event"""
    logger.info(f"[CalendarAgent] Creating event: {summary}")
    
    service = CalendarService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.create_event(summary, start_time, end_time, description, attendees or [])

@calendar_agent.tool
async def update_event(ctx: RunContext[AgentDeps], event_id: str, summary: str = None, start_time: str = None, end_time: str = None, description: str = None) -> Dict:
    """Update an existing calendar event"""
    logger.info(f"[CalendarAgent] Updating event: {event_id}")
    
    service = CalendarService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    updates = {}
    if summary:
        updates['summary'] = summary
    if start_time:
        updates['start'] = {'dateTime': start_time, 'timeZone': 'UTC'}
    if end_time:
        updates['end'] = {'dateTime': end_time, 'timeZone': 'UTC'}
    if description:
        updates['description'] = description
    
    return await service.update_event(event_id, **updates)

@calendar_agent.tool
async def delete_event(ctx: RunContext[AgentDeps], event_id: str) -> Dict:
    """Delete a calendar event"""
    logger.info(f"[CalendarAgent] Deleting event: {event_id}")
    
    service = CalendarService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.delete_event(event_id)

async def process_calendar_query(query: str, deps: AgentDeps) -> Dict[str, Any]:
    """Process Calendar-specific queries"""
    try:
        result = await calendar_agent.run(query, deps=deps)
        return {
            "success": True,
            "data": result.output,
            "service": "calendar"
        }
    except Exception as e:
        logger.error(f"[CalendarAgent] Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "service": "calendar"
        }