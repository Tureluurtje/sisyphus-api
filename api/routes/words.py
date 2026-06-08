from fastapi import APIRouter, Request, Depends
from uuid import UUID

from api.schema.internal.words import LoadWordList
from api.services.auth_service import get_user_id
from api.services.words_service import get_due_words_service, save_wordlist_service
from api.schema.http.words import DueWordsResponse, WordReviewRequest

router = APIRouter(prefix="/words")

@router.post("/load")
def load_wordlist(
    request: Request,
    word_list: LoadWordList,
    user_id: UUID = Depends(get_user_id),
):
    save_wordlist_service(user_id, word_list)
    return {"success": True}


@router.get("/due")
def get_due_words(
    request: Request, limit: int, offset: int, user_id: UUID = Depends(get_user_id)
) -> DueWordsResponse:
    due_words = get_due_words_service(user_id)
    return due_words


@router.post("/review")
def submit_word_review(request: Request, data: WordReviewRequest, user_id: UUID):
    # submit_word_review_service(data)
    return {"success": True}
