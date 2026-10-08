# Run with: uvicorn server:app --reload --port 8000

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import random
from pydantic import BaseModel
import time
from cf import get_turn_credentials
import store


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

backend = store.backend

class OfferPatch(BaseModel):
    offer: str | None = None
    answer: str | None = None



with open('words.txt') as f:
    words = f.readlines()

def generate_code():
    return random.choice(words).strip()


@app.post("/offer")
def create_offer():
    store.cleanup()

    code = generate_code()
    while backend.get(code) is not None:
        code = generate_code()
    backend.set(code, store.new_session())
    return {"code": code}


@app.patch("/offer/{code}")
def patch_offer(code: str, patch: OfferPatch):
    session = backend.get(code)
    if session is None:
        # force-patch: recreate evicted/missing sessions
        session = store.new_session()
    for field in patch.model_fields_set:
        session[field] = getattr(patch, field)
    backend.set(code, session)
    return session


@app.get("/offer/{code}")
def get_offer(code: str):
    session = backend.get(code)
    if session is None:
        raise HTTPException(status_code=404, detail="Not found")
    return session


@app.get("/turn/{code}")
def get_turn(code: str):
    session = backend.get(code)
    if session is None:
        raise HTTPException(status_code=404, detail="Not found")
    if session.get('servers'): return session
    session['servers'] = get_turn_credentials()
    backend.set(code, session)
    print(f'Requesting TURN server - received {session["servers"]}')
    return session


app.mount("/", StaticFiles(directory=".", html=True), name="static")