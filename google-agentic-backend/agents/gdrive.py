from pydantic_ai import Agent, RunContext
from typing import List, Dict, Any
import logfire
from agents.deps import AgentDeps
from services.drive_services import DriveService
from services.llm_service import get_model_client


logger = logfire.configure()

drive_agent = Agent(
    model = get_model_client(),
    deps_type=AgentDeps,
    system_prompt="""You are a Google Drive specialist agent. You help users manage their files and folders.

Available operations:
- search_files: Search for files. Supports filters like mimeType and modifiedTime dates.
- get_file_content: Get file metadata and content
- share_file: Share a file with someone
- create_folder: Create a new folder
- move_file: Move a file to another location

SEARCH SYNTAX:
When searching with filters, use this format in your query:
- For PDFs: mimeType = 'application/pdf'
- For date ranges: modifiedTime >= '2023-01-01T00:00:00' and modifiedTime <= '2025-12-31T23:59:59'
- Always include: trashed = false

Example query: "mimeType = 'application/pdf' and modifiedTime >= '2023-12-29T00:00:00' and modifiedTime <= '2025-12-29T23:59:59' and trashed = false"

Always provide clear information about file operations."""
)

@drive_agent.tool
async def search_files(ctx: RunContext[AgentDeps], query: str, mime_type: str = None, max_results: int = 10) -> List[Dict]:
    """Search for files in Google Drive"""
    logger.info(f"[DriveAgent] Searching files: {query}")
    
    service = DriveService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    results = await service.search_files(query, mime_type, max_results)
    logger.info(f"[DriveAgent] Found {len(results)} files")
    
    return results

@drive_agent.tool
async def get_file_content(ctx: RunContext[AgentDeps], file_id: str) -> Dict:
    """Get file metadata and content"""
    logger.info(f"[DriveAgent] Fetching file: {file_id}")
    
    service = DriveService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.get_file(file_id)

@drive_agent.tool
async def share_file(ctx: RunContext[AgentDeps], file_id: str, email: str, role: str = "reader") -> Dict:
    """Share a file with someone"""
    logger.info(f"[DriveAgent] Sharing file {file_id} with {email}")
    
    service = DriveService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.share_file(file_id, email, role)

@drive_agent.tool
async def create_folder(ctx: RunContext[AgentDeps], folder_name: str, parent_folder_id: str = None) -> Dict:
    """Create a new folder"""
    logger.info(f"[DriveAgent] Creating folder: {folder_name}")
    
    service = DriveService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.create_folder(folder_name, parent_folder_id)

@drive_agent.tool
async def move_file(ctx: RunContext[AgentDeps], file_id: str, new_parent_id: str) -> Dict:
    """Move a file to another location"""
    logger.info(f"[DriveAgent] Moving file {file_id} to {new_parent_id}")
    
    service = DriveService(
        ctx.deps.google_credentials,
        ctx.deps.db_session,
        ctx.deps.user_email,
        ctx.deps.qdrant_service
    )
    
    return await service.move_file(file_id, new_parent_id)

async def process_drive_query(query: str, deps: AgentDeps) -> Dict[str, Any]:
    """Process Drive-specific queries"""
    try:
        result = await drive_agent.run(query, deps=deps)
        return {
            "success": True,
            "data": result.output,
            "service": "drive"
        }
    except Exception as e:
        logger.error(f"[DriveAgent] Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "service": "drive"
        }