# pyrefly: ignore [missing-import]
import uvicorn
import asyncio
import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Try loading from the current directory, or fallback to the script's directory
if not load_dotenv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(dotenv_path=os.path.join(script_dir, ".env"))


async def run_bot_async():
    # Import bot function safely
    # pyrefly: ignore [missing-import]
    from bot.bot_main import run_bot
    await run_bot()

async def main():
    print("Starting Unified Preview Server (API + Bot)")
    
    # Configure Uvicorn server to run in the current asyncio loop
    config = uvicorn.Config("main:app", host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    # Run both the API and the Bot concurrently
    api_task = asyncio.create_task(server.serve())
    bot_task = asyncio.create_task(run_bot_async())
    
    await asyncio.gather(api_task, bot_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutdown requested.")
