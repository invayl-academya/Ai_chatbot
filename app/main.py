from fastapi import FastAPI


from starlette.middleware.cors import CORSMiddleware

from .database import engine, get_db
from .models import Base, ChatMessage
from  .routers import  auth , chats



app = FastAPI(title="Invayl Tutor – Python • ML • DL")

Base.metadata.create_all(bind=engine) #create tables
app.include_router(auth.authRoutes)
app.include_router(chats.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # add your prod domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/")
def read_root() -> dict:
    return {"msg": "welcome to chatbot project"}






# @app.post("/chat")
# def chat(body: ChatBody):
#     try:
#         req = {
#             "model": "gpt-4o-mini",
#             "input": [
#                 {"role": "system", "content": TUTOR_SYSTEM},
#                 {"role": "user", "content": body.message},
#             ],
#         }
#         if body.max_output_tokens is not None:
#             req["max_output_tokens"] = body.max_output_tokens

#         resp = client.responses.create(**req)

#         # Prefer output_text; fallback to assembling text from output parts if needed
#         reply = getattr(resp, "output_text", "") or ""
#         if not reply and hasattr(resp, "output"):
#             parts = []
#             for item in resp.output:
#                 if getattr(item, "type", "") == "message":
#                     for c in getattr(item, "content", []):
#                         if getattr(c, "type", "") == "output_text":
#                             parts.append(c.text)
#             reply = "".join(parts)

#         return {"reply": reply, "usage": getattr(resp, "usage", None)}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
