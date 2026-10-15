from fastapi import APIRouter, Request
from ..models import QueryRequest, QueryResponse

router = APIRouter()

@router.post("/chat/query", response_model=QueryResponse)
async def chat_query(request: QueryRequest):
    # Initialize services
    from ..services.chroma_service import ChromaService
    from ..services.hybrid_retriever import HybridRetriever
    from ..services.answer_generator import AnswerGenerator

    chroma_service = ChromaService()
    retriever = HybridRetriever(chroma_service=chroma_service)
    retriever_response = retriever.retrieve(request.query, n_results=request.max_sources)

    # Generate answer
    answer_gen = AnswerGenerator()
    response = answer_gen.generate(request.query, retriever_response, request.max_sources)

    return response

@router.get("/chat/conversations")
async def get_conversations():
    return []

@router.delete("/chat/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    return {"status": "deleted"}