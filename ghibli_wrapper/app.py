from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get('/health', response_class=HTMLResponse)
async def root():
    return 'Hello world!'
