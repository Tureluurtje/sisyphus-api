from typing import Optional, cast

from fastapi import APIRouter, Request, Depends
from uuid import UUID

from api.schema.internal.words import LoadWordList, Stack
from api.services.auth_service import get_user_id, get_user_id_skip_csrf
from api.services.words_service import get_due_words_service, get_stack_service, save_wordlist_service, submit_word_review_service
from api.schema.http.words import DueWordsResponse, GetStacksResponse, WordReviewRequest#, WordReviewResponse

router = APIRouter(prefix="/words", tags=["/words"])

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
    request: Request, limit: Optional[int] = None, offset: Optional[int] = None, user_id: UUID = Depends(get_user_id_skip_csrf)
) -> DueWordsResponse:
    due_words = get_due_words_service(user_id, limit, offset)
    return DueWordsResponse(
        wordAmount=len(due_words),
        words=due_words
    )

@router.post("/review")
def submit_word_review(request: Request, data: WordReviewRequest, user_id: UUID = Depends(get_user_id)):
    #updated_cards = submit_word_review_service(user_id, data.reviews)
    submit_word_review_service(user_id, data.reviews)
    # TODO: Possibly return new cards for frontend caching
    #return WordReviewResponse(
    #    reviews=updated_cards
    #)
    return {"success": True}

@router.get("/stacks")
def get_stacks(
    request: Request,
    user_id: UUID = Depends(get_user_id_skip_csrf)
) -> GetStacksResponse:
    stacks = cast(GetStacksResponse, get_stack_service(
        user_id=user_id,
        all_stacks=True
    ))
    return stacks
