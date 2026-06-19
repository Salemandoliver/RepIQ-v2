"""Playlists: curated collections of calls for team learning
(e.g. 'BTnet calls', 'Good rejection handling', 'Best SPIN calls').
Anyone can create playlists and add calls; only the owner or an admin can
rename/delete a playlist or remove items."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..db import get_db
from ..models import Playlist, PlaylistItem, Call, User
from ..serializers import to_list_item

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


def _can_edit(p: Playlist, user: User) -> bool:
    return user.role == "admin" or p.owner_id == user.id


def _summary(db: Session, p: Playlist) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "owner": {"id": p.owner.id, "name": p.owner.name,
                  "avatar_color": p.owner.avatar_color} if p.owner else None,
        "tracks": db.query(func.count(PlaylistItem.id))
                    .filter(PlaylistItem.playlist_id == p.id).scalar() or 0,
        "created_at": p.created_at,
        "can_edit": False,  # filled by caller
    }


@router.get("")
def list_playlists(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    out = []
    for p in (db.query(Playlist).options(joinedload(Playlist.owner))
              .order_by(Playlist.name).all()):
        s = _summary(db, p)
        s["can_edit"] = _can_edit(p, user)
        out.append(s)
    return out


@router.post("")
def create_playlist(body: dict, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Playlist name is required")
    if db.query(Playlist).filter(Playlist.name == name).first():
        raise HTTPException(409, "A playlist with that name already exists")
    p = Playlist(name=name, description=(body.get("description") or "").strip(),
                 owner_id=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    s = _summary(db, p)
    s["can_edit"] = True
    return s


@router.get("/{playlist_id}")
def get_playlist(playlist_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    p = (db.query(Playlist).options(joinedload(Playlist.owner))
         .filter(Playlist.id == playlist_id).first())
    if not p:
        raise HTTPException(404, "Playlist not found")
    items = (db.query(PlaylistItem).options(joinedload(PlaylistItem.adder))
             .filter(PlaylistItem.playlist_id == p.id)
             .order_by(PlaylistItem.position, PlaylistItem.id).all())
    s = _summary(db, p)
    s["can_edit"] = _can_edit(p, user)
    s["items"] = []
    for it in items:
        call = db.get(Call, it.call_id)
        if call:
            s["items"].append({
                "item_id": it.id,
                "added_by": {"id": it.adder.id, "name": it.adder.name} if it.adder else None,
                "added_at": it.added_at,
                "call": to_list_item(db, call).model_dump(),
            })
    return s


@router.patch("/{playlist_id}")
def update_playlist(playlist_id: int, body: dict, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    p = db.get(Playlist, playlist_id)
    if not p:
        raise HTTPException(404, "Playlist not found")
    if not _can_edit(p, user):
        raise HTTPException(403, "Only the playlist owner or an admin can edit it")
    if body.get("name"):
        p.name = body["name"].strip()
    if "description" in body:
        p.description = (body.get("description") or "").strip()
    db.commit()
    s = _summary(db, p)
    s["can_edit"] = True
    return s


@router.delete("/{playlist_id}")
def delete_playlist(playlist_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    p = db.get(Playlist, playlist_id)
    if p:
        if not _can_edit(p, user):
            raise HTTPException(403, "Only the playlist owner or an admin can delete it")
        db.delete(p)
        db.commit()
    return {"ok": True}


@router.post("/{playlist_id}/items")
def add_item(playlist_id: int, body: dict, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    p = db.get(Playlist, playlist_id)
    if not p:
        raise HTTPException(404, "Playlist not found")
    call_id = body.get("call_id")
    if not call_id or not db.get(Call, call_id):
        raise HTTPException(404, "Call not found")
    if db.query(PlaylistItem).filter(PlaylistItem.playlist_id == playlist_id,
                                     PlaylistItem.call_id == call_id).first():
        return {"ok": True, "duplicate": True}
    max_pos = (db.query(func.max(PlaylistItem.position))
               .filter(PlaylistItem.playlist_id == playlist_id).scalar() or 0)
    db.add(PlaylistItem(playlist_id=playlist_id, call_id=call_id,
                        added_by=user.id, position=max_pos + 1))
    db.commit()
    return {"ok": True}


@router.delete("/{playlist_id}/items/{call_id}")
def remove_item(playlist_id: int, call_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    p = db.get(Playlist, playlist_id)
    if not p:
        raise HTTPException(404, "Playlist not found")
    it = db.query(PlaylistItem).filter(PlaylistItem.playlist_id == playlist_id,
                                       PlaylistItem.call_id == call_id).first()
    if it:
        if not (_can_edit(p, user) or it.added_by == user.id):
            raise HTTPException(403, "You can only remove calls you added")
        db.delete(it)
        db.commit()
    return {"ok": True}
