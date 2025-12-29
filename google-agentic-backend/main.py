import secrets
import uvicorn
import os
from fastapi import Depends, FastAPI, APIRouter, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
import logfire

from routes.v1 import v1_router
from routes import *
from configs.config import get_settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logger
logger = logfire.configure()

# Load settings and set environment variables
settings = get_settings()
env_vars = settings.get_environment_variables()
logger.info("Setting environment variables")
for key, value in env_vars.items():
    os.environ[key] = value
logger.info("Environment variables set")

# Initialize HTTP Basic security
security = HTTPBasic()

# Initialize FastAPI with explicit configuration
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    title="Google Agentic Assignment API",
    description="Your API Description",
    version="1.0.0",
    debug=True
)

# Initialize root router
root_router = APIRouter()



def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, settings.swagger_docs.username)
    correct_password = secrets.compare_digest(credentials.password, settings.swagger_docs.password.get_secret_value())
    if not (correct_username and correct_password):
        logger.error("Incorrect email or password for Swagger docs")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# app.middleware("http")(AuthMiddleware())

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_endpoint(username: str = Depends(get_current_username)):
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Google Agentic Assignment API",
        version="1.0.0",
        routes=app.routes,
    )
    
    # Initialize components if it doesn't exist
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Add security requirement to all endpoints
    for path in openapi_schema["paths"].values():
        for operation in path.values():
            if "security" not in operation:
                operation["security"] = []
            operation["security"].append({"bearerAuth": []})
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="API Documentation",
    )


# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic routes
@app.get("/", status_code=200)
def hello_world():
    return "Server is running!"

@app.get("/health")
def health_check():
    return {"status": "UP"}

@app.get("/version")
def get_version():
    return "v1"

# Include routers
root_router.include_router(v1_router, prefix="/v1")
app.include_router(root_router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )