# Run with: uvicorn server:app --reload --port 8000

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import random
from pydantic import BaseModel
import time
from cf import get_turn_credentials


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}

class OfferPatch(BaseModel):
    offer: str | None = None
    answer: str | None = None



with open('words.txt') as f:
    words = f.readlines()

def generate_code():
    return random.choice(words).strip()


@app.post("/offer")
def create_offer():
    for s in list(sessions.keys()):
        oa = sessions[s].get('offer') and sessions[s].get('answer')
        if (sessions[s].get('created') or 0) + 600 * (24 if oa else .5) < time.time():
            del(sessions[s])

    code = generate_code()
    while code in sessions:
        code = generate_code()
    sessions[code] = {"offer": None, "answer": None, "created": time.time(), "servers": None}
    return {"code": code}


@app.patch("/offer/{code}")
def patch_offer(code: str, patch: OfferPatch):
    session = sessions.get(code)
    if session is None:
        sessions[code] = {"offer": None, "answer": None, "created": time.time()}
        session = sessions.get(code)
    for field in patch.model_fields_set:
        session[field] = getattr(patch, field)
    return session


@app.get("/offer/{code}")
def get_offer(code: str):
    if code not in sessions:
        raise HTTPException(status_code=404, detail="Not found")
    return sessions[code]


@app.get("/turn/{code}")
def get_turn(code: str):
    session = sessions.get(code)
    if session.get('servers'): return session
    session['servers'] = get_turn_credentials()
    print(f'Requesting TURN server - received {session["servers"]}')
    return session


app.mount("/", StaticFiles(directory=".", html=True), name="static")
