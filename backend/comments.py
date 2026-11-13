import math

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from shapely.geometry import Point

import userdb
from auth import current_user

COMMENT_TTL_S = 24 * 3600
MAX_ACTIVE_PER_USER = 20
TEXT_MAX_LEN = 300

router = APIRouter(prefix="/comments")


class CommentBody(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    text: str


def public_comment(row: dict, user: dict) -> dict:
    return {
        "id": row["id"],
        "lat": row["lat"],
        "lon": row["lon"],
        "text": row["text"],
        "author": row["author"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "mine": row["user_id"] == user["id"],
    }


@router.get("")
def list_comments(user: dict = Depends(current_user)):
    return [public_comment(row, user) for row in userdb.active_comments()]


@router.post("")
def create_comment(body: CommentBody, request: Request, user: dict = Depends(current_user)):
    text = " ".join(body.text.split())
    if not text:
        raise HTTPException(400, "Комментарий не может быть пустым")
    if len(text) > TEXT_MAX_LEN:
        raise HTTPException(400, f"Не больше {TEXT_MAX_LEN} символов")
    if not (math.isfinite(body.lat) and math.isfinite(body.lon)):
        raise HTTPException(400, "Некорректная точка")
    if not request.app.state.routing_service.boundary.contains(Point(body.lon, body.lat)):
        raise HTTPException(400, "Точка за пределами Обамы")
    if userdb.count_user_comments(user["id"]) >= MAX_ACTIVE_PER_USER:
        raise HTTPException(429, f"Не больше {MAX_ACTIVE_PER_USER} активных комментариев")
    row = userdb.add_comment(user["id"], user["name"], body.lat, body.lon, text, COMMENT_TTL_S)
    return public_comment(row, user)


@router.delete("/{comment_id}")
def remove_comment(comment_id: int, user: dict = Depends(current_user)):
    if userdb.delete_comment(comment_id, user["id"]):
        return {"ok": True}
    if userdb.comment_exists(comment_id):
        raise HTTPException(403, "Можно удалять только свои комментарии")
    raise HTTPException(404, "Комментарий не найден или уже исчез")
