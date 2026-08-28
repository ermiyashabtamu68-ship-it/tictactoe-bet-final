"""
services/friend_service.py

Handles the friend request lifecycle: send a request, accept or
decline it, and list a user's accepted friends. Once two users are
friends, inviting them to a match reuses the SAME challenge logic
matchmaking_service already has for "challenge by username" — we
just resolve the username automatically from the friendship instead
of asking the player to type it every time.
"""

import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models.models import Friendship, User
from app.services.user_service import get_user_by_username
from app.core import telegram_notify


class FriendNotFoundError(Exception):
    pass


class CannotFriendSelfError(Exception):
    pass


class AlreadyFriendsError(Exception):
    pass


class RequestNotFoundError(Exception):
    pass


class NotFriendsError(Exception):
    pass


def send_request(db: Session, requester: User, friend_identifier: str) -> Friendship:
    """
    friend_identifier can be either an @username OR a numeric
    Telegram ID (shown on each player's Profile screen as "Your ID").
    Not every Telegram account has a public username, so the ID is
    the one input guaranteed to always work.
    """
    friend_identifier = friend_identifier.strip().lstrip("@")

    if friend_identifier.isdigit():
        addressee = db.query(User).filter(User.telegram_user_id == int(friend_identifier)).first()
    else:
        addressee = get_user_by_username(db, friend_identifier)

    if addressee is None:
        raise FriendNotFoundError(f"No registered player found for '{friend_identifier}'.")

    if addressee.internal_id == requester.internal_id:
        raise CannotFriendSelfError("You can't add yourself as a friend.")

    existing = db.query(Friendship).filter(
        or_(
            and_(Friendship.requester_id == requester.internal_id, Friendship.addressee_id == addressee.internal_id),
            and_(Friendship.requester_id == addressee.internal_id, Friendship.addressee_id == requester.internal_id),
        )
    ).first()

    if existing is not None:
        if existing.status == "accepted":
            raise AlreadyFriendsError("You're already friends with this player.")
        if existing.status == "pending":
            raise AlreadyFriendsError("A friend request with this player is already pending.")
        # Previously declined — let them try again with a fresh row.
        existing.status = "pending"
        existing.requester_id = requester.internal_id
        existing.addressee_id = addressee.internal_id
        db.commit()
        db.refresh(existing)
        return existing

    friendship = Friendship(requester_id=requester.internal_id, addressee_id=addressee.internal_id)
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


def respond_request(db: Session, responder: User, request_id: str, accept: bool) -> Friendship:
    friendship = db.query(Friendship).filter(Friendship.id == uuid.UUID(request_id)).first()
    if friendship is None or friendship.addressee_id != responder.internal_id:
        raise RequestNotFoundError("Friend request not found.")

    friendship.status = "accepted" if accept else "declined"
    db.commit()
    db.refresh(friendship)
    return friendship


def list_friends(db: Session, user: User) -> list[User]:
    friendships = db.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(Friendship.requester_id == user.internal_id, Friendship.addressee_id == user.internal_id),
    ).all()

    friend_ids = [
        f.addressee_id if f.requester_id == user.internal_id else f.requester_id
        for f in friendships
    ]
    if not friend_ids:
        return []
    return db.query(User).filter(User.internal_id.in_(friend_ids)).all()


def list_pending_requests(db: Session, user: User) -> list[Friendship]:
    return db.query(Friendship).filter(
        Friendship.addressee_id == user.internal_id,
        Friendship.status == "pending",
    ).all()


def are_friends(db: Session, user_a_id, user_b_id) -> bool:
    return db.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(
            and_(Friendship.requester_id == user_a_id, Friendship.addressee_id == user_b_id),
            and_(Friendship.requester_id == user_b_id, Friendship.addressee_id == user_a_id),
        ),
    ).first() is not None


async def invite_friend(redis_client, db: Session, inviter: User, friend_id: str, stake_amount: Decimal, game_type: str = "tictactoe") -> dict:
    """
    Sends a match invite to an already-accepted friend, without
    needing to retype their @username. Under the hood this is the
    exact same pending-challenge mechanism 'Play vs Friend' uses —
    we just look up the username automatically first, THEN push a
    Telegram notification with Accept/Decline buttons to the friend
    directly, since the Mini App invite has no chat handler already
    running to do that for us the way the old in-chat flow did.
    """
    from app.services import matchmaking_service

    friend = db.query(User).filter(User.internal_id == uuid.UUID(friend_id)).first()
    if friend is None:
        raise FriendNotFoundError("That friend could not be found.")

    if not are_friends(db, inviter.internal_id, friend.internal_id):
        raise NotFriendsError("You're not friends with this player yet.")

    result = matchmaking_service.create_challenge_for_user(
        redis_client, db, inviter, friend, stake_amount, game_type=game_type,
    )

    game_label = "Checkers" if game_type == "checkers" else "Tic-Tac-Toe"
    await telegram_notify.send_message(
        result["opponent_telegram_id"],
        f"🎯 <b>{inviter.full_name or inviter.telegram_username or inviter.telegram_user_id} "
        f"challenged you to a {game_label} match for {stake_amount} ETB!</b>",
        reply_markup=telegram_notify.challenge_response_markup(),
    )

    return result
