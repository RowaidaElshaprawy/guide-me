from fastapi import APIRouter, HTTPException, Depends, Request
from backend.core.schemas import ChatRequest, ChatResponse
from backend.core.config import Settings, get_settings

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request_body: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    try:
        orchestrator = request.app.state.orchestrator
        return await orchestrator.run(request_body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))