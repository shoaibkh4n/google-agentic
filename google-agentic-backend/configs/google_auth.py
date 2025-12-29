from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import logfire
from db.models import User
from configs.config import get_settings

settings = get_settings()

logger = logfire.configure()

REDIRECT_URI = "http://localhost:8000/v1/auth/callback"

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

class AuthService:
    
    @staticmethod
    def create_flow():
        """Create OAuth flow for Google authentication"""
        client_config = {
            "web": {
                "client_id": settings.google_oauth.client_id,
                "client_secret": settings.google_oauth.client_secret.get_secret_value(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        return flow
    
    @staticmethod
    def get_credentials_from_user(user: User) -> Credentials:
        """Get Google credentials from user object and refresh if needed"""
        if not user.google_access_token:
            logger.warning(f"No access token for user: {user.email}")
            return None
        
        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_oauth.client_id,
            client_secret=settings.google_oauth.client_secret.get_secret_value(),
            scopes=SCOPES
        )
        
        if credentials.expired and credentials.refresh_token:
            try:
                logger.info(f"Refreshing token for user: {user.email}")
                credentials.refresh(Request())
                user.google_access_token = credentials.token
                user.token_expiry = datetime.utcnow() + timedelta(hours=1)
                logger.info(f"Token refreshed successfully for: {user.email}")
            except Exception as e:
                logger.error(f"Token refresh failed for {user.email}: {str(e)}")
                return None
        
        return credentials
    
    @staticmethod
    def validate_credentials(credentials: Credentials) -> bool:
        """Check if credentials are valid"""
        if not credentials:
            return False
        
        if credentials.expired:
            if credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    return True
                except:
                    return False
            return False
        
        return True