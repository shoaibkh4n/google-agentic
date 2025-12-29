from pydantic_ai import Agent, RunContext
from typing import List, Dict, Any
import asyncio
import logfire
from agents.deps import AgentDeps
from agents.gmail import process_gmail_query
from agents.gcal import process_calendar_query
from agents.gdrive import process_drive_query
from schemas import Intent
from configs.config import get_settings
from services.llm_service import get_model_client, get_async_llm_client
from sqlalchemy import select
from db.models import Message

settings = get_settings()
logger = logfire.configure()

orchestrator = Agent(
    model=get_model_client(),
    deps_type=AgentDeps,
    system_prompt="""You are an intelligent workspace orchestrator that coordinates multiple specialized agents.

Your responsibilities:
1. Analyze user queries WITH CONVERSATION HISTORY to understand context
2. Classify the intent and extract entities
3. Delegate tasks to specialized agents WITH FULL CONTEXT
4. Coordinate parallel and sequential operations
5. Synthesize results into coherent natural language responses

Available agents:
- Gmail Agent: Email operations (search, send, draft, labels)
- Calendar Agent: Event operations (search, create, update, delete)
- Drive Agent: File operations (search, share, folders)

IMPORTANT: Always consider conversation history to understand what information was already retrieved."""
)


async def get_conversation_history(deps: AgentDeps, limit: int = 20) -> str:
    """Fetches recent messages and formats them for the prompt"""
    if not deps.conversation_id:
        return "No conversation history available."
    
    stmt = (
        select(Message)
        .where(Message.conversation_id == deps.conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = deps.db_session.execute(stmt)
    messages = result.scalars().all()
    messages = list(reversed(messages))
    
    history_lines = []
    for msg in messages:
        content = msg.content.get('text', str(msg.content)) if isinstance(msg.content, dict) else str(msg.content)
        timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')
        history_lines.append(f"[{timestamp}] {msg.role.value.upper()}: {content}")
    
    history_text = "\n".join(history_lines)
    
    try:
        with open("history.txt", "w", encoding="utf-8") as f:
            f.write(history_text)
    except Exception as e:
        logger.warning(f"Could not save history to file: {e}")
    
    return history_text


async def classify_intent_with_context(query: str, deps: AgentDeps) -> Dict[str, Any]:
    """Classify user intent with full conversation context"""
    logger.info(f"[Orchestrator] Classifying intent for query: {query}")
    
    history_text = await get_conversation_history(deps)
    client = get_async_llm_client()
    
    classification_prompt = f"""Analyze this query IN CONTEXT of the conversation history.

CONVERSATION HISTORY:
{history_text}

CURRENT QUERY: {query}

Based on the conversation history and current query, respond with a JSON object containing:
- services: array of needed services ("gmail", "calendar", "drive")
- intent: short description of what user wants
- context_from_history: what information from history is relevant
- entities: key entities extracted from query AND history
- needs_new_search: boolean - does this need new API calls or can we use info from history?
- specific_task: exact task to perform (e.g., "draft_email_to_cancel_flight")
- task_parameters: specific parameters extracted from history (flight details, recipient email, etc.)

Example for "draft a cancellation email":
{{
  "services": ["gmail"],
  "intent": "draft_cancellation_email",
  "context_from_history": "User previously found flight AI 1803 to Kerala on 2 Jan 2026 from calendar",
  "entities": {{
    "flight_number": "AI 1803",
    "destination": "Kerala",
    "date": "2 Jan 2026",
    "time": "01:35 - 03:25",
    "recipient_email": "xyz@gmail.com",
    "recipient_name": "Mr XYZ"
  }},
  "needs_new_search": false,
  "specific_task": "draft_cancellation_email",
  "task_parameters": {{
    "to": "xyz@gmail.com",
    "flight_info": "AI 1803 to Kerala on 2 Jan 2026, 01:35 - 03:25"
  }}
}}"""
    
    response = await client.chat.completions.create(
        model="agentic-large",
        messages=[
            {"role": "system", "content": "You are an intent classification system that understands conversation context. Always respond with valid JSON only."},
            {"role": "user", "content": classification_prompt}
        ],
        temperature=0.1
    )
    
    try:
        import json
        intent_data = json.loads(response.choices[0].message.content)
        logger.info(f"[Orchestrator] Classified intent: {intent_data.get('intent')}, services: {intent_data.get('services')}")
        return intent_data
    except Exception as e:
        logger.error(f"[Orchestrator] Intent classification error: {str(e)}")
        return {
            "services": ["gmail"],
            "intent": "general_query",
            "entities": {},
            "needs_new_search": True,
            "specific_task": "process_query",
            "task_parameters": {}
        }


async def build_contextual_query(original_query: str, intent_data: Dict[str, Any]) -> str:
    """Build a query that includes context and explicit action instructions"""
    
    context = intent_data.get("context_from_history", "")
    entities = intent_data.get("entities", {})
    task_params = intent_data.get("task_parameters", {})
    specific_task = intent_data.get("specific_task", "")
    intent = intent_data.get("intent", "")
    
    action_instruction = ""
    
    # Map intents to explicit action instructions
    if "draft" in intent or "draft" in specific_task:
        action_instruction = "ACTION REQUIRED: Create a draft email using draft_email tool."
    elif "send" in intent or "send" in specific_task:
        action_instruction = "ACTION REQUIRED: Send an email using send_email tool."
    elif "create" in intent or "schedule" in intent or "add" in intent:
        action_instruction = "ACTION REQUIRED: Create a calendar event using create_event tool."
    elif "update" in intent or "modify" in intent or "change" in intent:
        action_instruction = "ACTION REQUIRED: Update the item using the appropriate update tool."
    elif "delete" in intent or "remove" in intent or "cancel" in intent:
        action_instruction = "ACTION REQUIRED: Delete/cancel the item using the appropriate delete tool."
    elif "share" in intent:
        action_instruction = "ACTION REQUIRED: Share the file using share_file tool."
    
    contextual_query = f"""ORIGINAL USER REQUEST: {original_query}

{action_instruction}

CONTEXT FROM CONVERSATION HISTORY:
{context}

EXTRACTED ENTITIES AND PARAMETERS:
"""
    
    for key, value in entities.items():
        contextual_query += f"- {key}: {value}\n"
    
    if task_params:
        contextual_query += "\nTASK PARAMETERS:\n"
        for key, value in task_params.items():
            contextual_query += f"- {key}: {value}\n"
    
    contextual_query += f"""
IMPORTANT INSTRUCTIONS:
1. You MUST perform the action, not just describe it
2. Use the tools available to you to complete the task
3. Extract all necessary parameters from the context above
4. If this is a write operation (create/send/draft/update/delete), you MUST call the appropriate tool
5. Return the actual result of the operation, including IDs, confirmation, etc.
"""
    
    return contextual_query


async def execute_task_with_context(query: str, intent_data: Dict[str, Any], deps: AgentDeps) -> List[Dict[str, Any]]:
    """Execute tasks with full context awareness"""
    
    services = intent_data.get("services", [])
    specific_task = intent_data.get("specific_task", "")
    needs_new_search = intent_data.get("needs_new_search", True)
    
    contextual_query = await build_contextual_query(query, intent_data)
    
    logger.info(f"[Orchestrator] Executing task: {specific_task}, needs_new_search: {needs_new_search}")
    logger.info(f"[Orchestrator] Contextual query: {contextual_query[:200]}...")
    
    results = []
    
    for service in services:
        try:
            if service == "gmail":
                result = await process_gmail_query(contextual_query, deps)
            elif service == "calendar":
                result = await process_calendar_query(contextual_query, deps)
            elif service == "drive":
                result = await process_drive_query(contextual_query, deps)
            else:
                result = {"success": False, "error": f"Unknown service: {service}"}
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"[Orchestrator] Error executing {service}: {str(e)}")
            results.append({"success": False, "error": str(e), "service": service})
    
    return results


async def synthesize_response_with_context(query: str, intent_data: Dict[str, Any], results: List[Dict[str, Any]], deps: AgentDeps) -> str:
    """Synthesize final response with conversation context"""
    logger.info("[Orchestrator] Synthesizing response with context")
    
    history_text = await get_conversation_history(deps)
    client = get_async_llm_client()
    
    results_summary = "\n".join([
        f"- {r.get('service', 'unknown')}: {'Success' if r.get('success') else 'Failed'} - {r.get('data', r.get('error', 'No data'))}"
        for r in results
    ])
    
    context_info = intent_data.get("context_from_history", "")
    entities = intent_data.get("entities", {})
    
    synthesis_prompt = f"""Synthesize a natural, helpful response based on conversation history and results.

CONVERSATION HISTORY (for context):
{history_text}

CURRENT QUERY: {query}

CONTEXT EXTRACTED FROM HISTORY:
{context_info}

RELEVANT ENTITIES FROM HISTORY:
{entities}

RESULTS FROM AGENTS:
{results_summary}

INSTRUCTIONS:
1. Use information from BOTH history and new results
2. If the user references something from history (like "that flight"), use the details from history
3. Provide a complete, helpful response
4. If drafting/sending an email, include the full content
5. Be conversational and don't ask unnecessary questions if you have the info
6. AVOID special characters like arrows (→), use "to" instead

Provide a clear, conversational response."""
    
    response = await client.chat.completions.create(
        model="agentic-large",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that synthesizes information from conversation history and multiple sources. Always use plain text, avoid special Unicode characters."},
            {"role": "user", "content": synthesis_prompt}
        ],
        temperature=0.7
    )
    
    # Clean response to avoid encoding issues
    response_text = response.choices[0].message.content
    
    return response_text


async def execute_query(query: str, deps: AgentDeps) -> Dict[str, Any]:
    """Main orchestration logic with full context awareness"""
    logger.info(f"[Orchestrator] Processing query: {query}")
    
    try:
        intent_data = await classify_intent_with_context(query, deps)
        
        services = intent_data.get("services", [])
        
        if not services or intent_data.get("intent") in ["greeting", "casual_conversation", "thanks"]:
            simple_responses = {
                "greeting": "Hello! How can I help you with your Gmail, Calendar, or Drive today?",
                "casual_conversation": "I'm here to help with your Google Workspace. What would you like to do?",
                "thanks": "You're welcome! Let me know if you need anything else."
            }
            response_text = simple_responses.get(intent_data.get("intent"), 
                "Hello! I can help you with Gmail, Calendar, and Drive. What would you like to do?")
            
            return {
                "response": response_text,
                "actions_taken": [],
                "intent": intent_data
            }
        
        results = await execute_task_with_context(query, intent_data, deps)
        
        response_text = await synthesize_response_with_context(query, intent_data, results, deps)
        
        actions_taken = []
        for r in results:
            if r.get("success"):
                service = r.get("service", "unknown")
                actions_taken.append(f"{service}: operation completed")
        
        logger.info(f"[Orchestrator] Query processed successfully, {len(actions_taken)} actions taken")
        
        return {
            "response": response_text,
            "actions_taken": actions_taken,
            "intent": intent_data
        }
        
    except Exception as e:
        logger.error(f"[Orchestrator] Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "response": f"I encountered an error processing your request: {str(e)}",
            "actions_taken": [],
            "intent": None
        }