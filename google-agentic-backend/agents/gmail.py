from pydantic_ai import Agent, RunContext
from typing import List, Dict, Any
import logfire
from agents.deps import AgentDeps
from services.gmail_service import GmailService
from services.llm_service import get_model_client
import traceback

logger = logfire.configure()

gmail_agent = Agent(
    model = get_model_client(),
    deps_type=AgentDeps,
    system_prompt="""You are a Gmail specialist agent. You help users with email operations.

Available operations:
- search_emails: Search for emails by query, sender, date range
- get_email_content: Get full content of a specific email
- send_email: Send a new email
- draft_email: Create a draft email
- update_labels: Add or remove labels from emails

Always provide clear, concise responses about email operations."""
)

@gmail_agent.tool
async def search_emails(ctx: RunContext[AgentDeps], query: str, max_results: int = 20) -> List[Dict]:
    """Search for emails matching the query"""
    logger.info(f"[GmailAgent] Searching emails: {query}")
    
    service = GmailService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    results = await service.search_emails(query, max_results)
    logger.info(f"[GmailAgent] Found {len(results)} emails")
    
    return results

@gmail_agent.tool
async def get_email_content(ctx: RunContext[AgentDeps], email_id: str) -> Dict:
    """Get full content of a specific email"""
    logger.info(f"[GmailAgent] Fetching email: {email_id}")
    
    service = GmailService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.get_email(email_id)

@gmail_agent.tool
async def send_email(ctx: RunContext[AgentDeps], to: str, subject: str, body: str) -> Dict:
    """Send a new email"""
    logger.info(f"[GmailAgent] Sending email to: {to}")
    
    service = GmailService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.send_email(to, subject, body)

@gmail_agent.tool
async def draft_email(ctx: RunContext[AgentDeps], to: str, subject: str, body: str) -> Dict:
    """Create a draft email"""
    logger.info(f"[GmailAgent] Drafting email to: {to}")
    
    service = GmailService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.draft_email(to, subject, body)

@gmail_agent.tool
async def update_labels(ctx: RunContext[AgentDeps], email_id: str, add_labels: List[str] = None, remove_labels: List[str] = None) -> Dict:
    """Add or remove labels from an email"""
    logger.info(f"[GmailAgent] Updating labels for email: {email_id}")
    
    service = GmailService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.update_labels(email_id, add_labels, remove_labels)

async def process_gmail_query(query: str, deps: AgentDeps) -> Dict[str, Any]:
    """Process Gmail-specific queries"""
    try:
        print(f'[GmailAgent] Processing: {deps.google_credentials}')
        result = await gmail_agent.run(query, deps=deps)
        
        return {
            "success": True,
            "data": result.output,
            "service": "gmail"
        }
    except Exception as e:
        logger.error(f"[GmailAgent] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "service": "gmail"
        }