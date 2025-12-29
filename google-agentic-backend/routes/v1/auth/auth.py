from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from configs.google_auth import AuthService
from configs.config import get_settings
from schemas import AuthStatusResponse
import logfire
from jose import jwt, JWTError
from datetime import datetime, timedelta

logger = logfire.configure()
settings = get_settings()

router = APIRouter(tags=["Authentication"], prefix="/auth")

JWT_SECRET_KEY = "random_stranger_things_character"

def create_session_token(user_email: str) -> str:
    """Create JWT session token"""
    payload = {
        "email": user_email,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    logger.info(f"[AuthRoute] Session token created for: {user_email}")
    return token


def verify_session_token(token: str) -> str:
    """Verify JWT session token and return email"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        email = payload.get("email")
        if email is None:
            logger.warning("[AuthRoute] Token missing email claim")
            return None
        return email
    except JWTError as e:
        logger.error(f"[AuthRoute] JWT verification failed: {str(e)}")
        return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Get current authenticated user from session token"""
    token = request.cookies.get("session_token")
    if not token:
        logger.warning("[AuthRoute] No session token found")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    email = verify_session_token(token)
    if not email:
        logger.warning("[AuthRoute] Invalid session token")
        raise HTTPException(status_code=401, detail="Invalid session")
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.error(f"[AuthRoute] User not found: {email}")
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@router.get("/google")
async def google_auth():
    """Initiate Google OAuth flow"""
    logger.info("[AuthRoute] Starting Google OAuth flow")
    
    try:
        flow = AuthService.create_flow()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        logger.info("[AuthRoute] Redirecting to Google authorization")
        return RedirectResponse(authorization_url)
    except Exception as e:
        logger.error(f"[AuthRoute] OAuth initiation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/callback")
async def auth_callback(code: str, response: Response, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    logger.info("[AuthRoute] Received OAuth callback")
    
    try:
        flow = AuthService.create_flow()
        flow.fetch_token(code=code)
        
        credentials = flow.credentials
        logger.info("[AuthRoute] OAuth token fetched successfully")
        
        from googleapiclient.discovery import build
        oauth_service = build('oauth2', 'v2', credentials=credentials)
        user_info = oauth_service.userinfo().get().execute()
        
        user_email = user_info.get('email')
        logger.info(f"[AuthRoute] User authenticated: {user_email}")
        
        user = db.query(User).filter(User.email == user_email).first()
        
        if not user:
            logger.info(f"[AuthRoute] Creating new user: {user_email}")
            user = User(
                email=user_email,
                google_access_token=credentials.token,
                google_refresh_token=credentials.refresh_token,
                token_expiry=datetime.utcnow() + timedelta(hours=1)
            )
            db.add(user)
        else:
            logger.info(f"[AuthRoute] Updating existing user: {user_email}")
            user.google_access_token = credentials.token
            if credentials.refresh_token:
                user.google_refresh_token = credentials.refresh_token
            user.token_expiry = datetime.utcnow() + timedelta(hours=1)
            user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        session_token = create_session_token(user.email)
        
        redirect = RedirectResponse(url=settings.frontend_url)
        redirect.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            max_age=7*24*60*60,
            samesite="lax",
            secure=False
        )
        
        logger.info(f"[AuthRoute] Session created for user: {user_email}")
        return redirect
        
    except Exception as e:
        logger.error(f"[AuthRoute] Auth callback error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """Check user authentication status"""
    try:
        user = get_current_user(request, db)
        credentials = AuthService.get_credentials_from_user(user)
        
        is_valid = AuthService.validate_credentials(credentials)
        
        logger.info(f"[AuthRoute] Auth status check for {user.email}: {is_valid}")
        
        return AuthStatusResponse(
            connected=is_valid,
            services={
                "gmail": is_valid,
                "calendar": is_valid,
                "drive": is_valid
            },
            user_email=user.email if is_valid else None
        )
    except HTTPException:
        logger.info("[AuthRoute] Auth status check: Not authenticated")
        return AuthStatusResponse(
            connected=False,
            services={"gmail": False, "calendar": False, "drive": False},
            user_email=None
        )


@router.post("/logout")
async def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    """Logout user"""
    try:
        user = get_current_user(request, db)
        logger.info(f"[AuthRoute] User logged out: {user.email}")
    except:
        pass
    
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}
