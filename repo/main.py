from fastapi import FastAPI
from routers import users, items, monsters

app = FastAPI(
    title="Monster Harvesting API", 
    description="Backend for the text-based RPG Discord Bot",
    version="1.0.0"
)

# Include the routers with appropriate prefixing
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(items.router, prefix="/api", tags=["Items"])
app.include_router(monsters.router, prefix="/api", tags=["Monsters"])

@app.get("/", tags=["System"])
def health_check():
    """
    Service health check endpoint.
    """
    return {
        "status": "online", 
        "message": "Monster Harvesting API is operational.",
        "version": "1.0.0"
    }
