"""User inbox (Epic 02 · slice a): generation from sends, the read endpoints,
and strict per-user isolation."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.db import build_engine, build_session_factory, create_tables
from app.main import create_app
from app.models.notification import Notification
from app.models.user import utcnow
from app.repositories.notification_repo import NotificationRepository
from tests.conftest import make_settings
from tests.helpers import auth, create_agent, do_setup, recv_until, register_member


def _send(client, token, frm, to, body):
    resp = client.post(
        "/api/messages", json={"from": frm, "to": to, "body": body}, headers=auth(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGeneration:
    def test_dm_generates_a_notification_for_the_recipient_owner(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "tem reset de senha?")

        items = client.get("/api/notifications", headers=auth(token)).json()
        assert len(items) == 1
        n = items[0]
        assert n["reason"] == "direct_message"
        assert n["agent_slug"] == "backend-julio"
        assert n["actor"] == "mobile-eduardo"
        assert n["unread"] is True
        assert n["status"] == "inbox"
        assert "backend-julio" in n["link"]  # hub-built deep link, no agent text

        count = client.get("/api/notifications/unread-count", headers=auth(token)).json()
        assert count == {"unread_count": 1}

    def test_repeated_dm_collapses_into_one_thread(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "primeira")
        _send(client, token, "mobile-eduardo", "backend-julio", "segunda")
        items = client.get("/api/notifications", headers=auth(token)).json()
        assert len(items) == 1  # collapsed onto the same thread

    def test_mention_notifies_the_mentioned_owner_only(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")  # admin's
        create_agent(client, member, "mobile-eduardo")  # member's
        create_agent(client, member, "frontend-ze")  # member's (recipient)

        _send(client, member, "mobile-eduardo", "frontend-ze", "ei @backend-julio, dá uma olhada")

        # admin (owner of the mentioned agent) gets a mention
        admin_items = client.get("/api/notifications", headers=auth(admin)).json()
        assert [n["reason"] for n in admin_items] == ["mention"]
        assert admin_items[0]["agent_slug"] == "backend-julio"

        # member (recipient's owner) gets the DM, but NOT the mention
        member_items = client.get("/api/notifications", headers=auth(member)).json()
        assert [n["reason"] for n in member_items] == ["direct_message"]


class TestTriageAndIsolation:
    def test_mark_read_and_set_status(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "oi")
        nid = client.get("/api/notifications", headers=auth(token)).json()[0]["id"]

        read = client.patch(
            f"/api/notifications/{nid}", json={"unread": False}, headers=auth(token)
        ).json()
        assert read["unread"] is False
        assert read["last_read_at"] is not None
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }

        done = client.patch(
            f"/api/notifications/{nid}", json={"status": "done"}, headers=auth(token)
        ).json()
        assert done["status"] == "done"
        # the inbox view no longer lists it
        inbox = client.get("/api/notifications?status=inbox", headers=auth(token)).json()
        assert inbox == []

    def test_observer_receives_notification_then_read_deltas(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        # panel observer (rides the session cookie set by do_setup)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            recv_until(ws, "hello_ack")

            _send(client, token, "mobile-eduardo", "backend-julio", "oi")
            frame = recv_until(ws, "notification")
            assert frame["notification"]["reason"] == "direct_message"
            nid = frame["notification"]["id"]

            # triage in this "tab" → a read delta syncs others (badge + ids)
            client.patch(f"/api/notifications/{nid}", json={"unread": False}, headers=auth(token))
            read = recv_until(ws, "notification_read")
            assert read["ids"] == [nid]
            assert read["unread_count"] == 0

    def test_read_all_clears_unread_and_pushes_an_all_delta(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        create_agent(client, token, "frontend-ze")
        _send(client, token, "mobile-eduardo", "backend-julio", "um")
        _send(client, token, "frontend-ze", "backend-julio", "dois")
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 2
        }
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            recv_until(ws, "hello_ack")
            resp = client.post("/api/notifications/read-all", headers=auth(token))
            assert resp.json() == {"unread_count": 0}
            delta = recv_until(ws, "notification_read")
            assert delta["ids"] == "all"
            assert delta["unread_count"] == 0
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }

    def test_read_all_only_touches_own(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        create_agent(client, admin, "mobile-eduardo")
        create_agent(client, member, "frontend-ze")
        create_agent(client, member, "infra-ana")
        _send(client, admin, "mobile-eduardo", "backend-julio", "p/ admin")
        _send(client, member, "infra-ana", "frontend-ze", "p/ member")
        # admin clears only their own inbox
        client.post("/api/notifications/read-all", headers=auth(admin))
        assert client.get("/api/notifications/unread-count", headers=auth(admin)).json() == {
            "unread_count": 0
        }
        assert client.get("/api/notifications/unread-count", headers=auth(member)).json() == {
            "unread_count": 1
        }


class TestPrefsAndDeliveryGate:
    def test_prefs_default_then_patch_roundtrips(self, client):
        token = do_setup(client)
        assert client.get("/api/notifications/prefs", headers=auth(token)).json() == {
            "notify_level": "mentions_and_direct"
        }
        patched = client.patch(
            "/api/notifications/prefs", json={"notify_level": "mute"}, headers=auth(token)
        )
        assert patched.json() == {"notify_level": "mute"}
        assert client.get("/api/notifications/prefs", headers=auth(token)).json() == {
            "notify_level": "mute"
        }

    def test_prefs_rejects_an_invalid_level(self, client):
        token = do_setup(client)
        resp = client.patch(
            "/api/notifications/prefs", json={"notify_level": "loud"}, headers=auth(token)
        )
        assert resp.status_code == 422

    def test_mute_suppresses_a_dm_but_a_mention_still_lands(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        create_agent(client, token, "frontend-ze")
        client.patch("/api/notifications/prefs", json={"notify_level": "mute"}, headers=auth(token))
        # a plain DM to my agent is gated out while muted
        _send(client, token, "mobile-eduardo", "backend-julio", "oi")
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }
        # the DM to frontend-ze is suppressed too, but the @mention always lands
        _send(client, token, "mobile-eduardo", "frontend-ze", "ei @backend-julio")
        items = client.get("/api/notifications", headers=auth(token)).json()
        assert [n["reason"] for n in items] == ["mention"]


class TestSubscriptions:
    def test_put_subscription_roundtrips_and_rejects_invalid(self, client):
        token = do_setup(client)
        subject = "dm:backend-julio:mobile-eduardo"
        ok = client.put(
            "/api/notifications/subscription",
            json={"subject_key": subject, "state": "ignored"},
            headers=auth(token),
        )
        assert ok.status_code == 200
        assert ok.json() == {"subject_key": subject, "state": "ignored"}

        bad = client.put(
            "/api/notifications/subscription",
            json={"subject_key": subject, "state": "watching"},
            headers=auth(token),
        )
        assert bad.status_code == 422

    def test_ignored_thread_mutes_dms_until_a_mention_resubscribes(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        create_agent(client, token, "frontend-ze")
        subject = "dm:backend-julio:mobile-eduardo"
        client.put(
            "/api/notifications/subscription",
            json={"subject_key": subject, "state": "ignored"},
            headers=auth(token),
        )
        # two DMs on the ignored thread are both muted (no rows)
        _send(client, token, "mobile-eduardo", "backend-julio", "oi")
        _send(client, token, "mobile-eduardo", "backend-julio", "de novo")
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }
        # an @mention on that thread always lands and re-subscribes it
        _send(client, token, "mobile-eduardo", "frontend-ze", "ei @backend-julio")
        mentions = client.get("/api/notifications?reason=mention", headers=auth(token)).json()
        assert len(mentions) == 1
        assert mentions[0]["subject_key"] == subject
        # prove the re-subscription: clear the badge, then a plain DM on that
        # thread is delivered again (collapses in → unread bumps back to 1)
        client.post("/api/notifications/read-all", headers=auth(token))
        _send(client, token, "mobile-eduardo", "backend-julio", "voltou")
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 1
        }


class TestRateCapAndRetention:
    def test_new_thread_rate_cap_drops_excess(self):
        # Own client with a tiny cap (the default is 200 — too high to hit here).
        app = create_app(make_settings(notification_max_new_per_hour=2))
        with TestClient(app) as client:
            token = do_setup(client)
            for slug in ("backend-julio", "sender-um", "sender-dois", "sender-tres"):
                create_agent(client, token, slug)
            # three DMs from three distinct senders → three distinct subject keys
            for sender, body in (
                ("sender-um", "um"),
                ("sender-dois", "dois"),
                ("sender-tres", "tres"),
            ):
                client.post(
                    "/api/messages",
                    json={"from": sender, "to": "backend-julio", "body": body},
                    headers=auth(token),
                )
            # cap=2 → the third new thread is dropped (no flood explosion)
            count = client.get("/api/notifications/unread-count", headers=auth(token)).json()
            assert count == {"unread_count": 2}

    async def test_prune_done_before_deletes_only_stale_done(self):
        # Self-contained real DB (own event loop) to exercise the actual DELETE.
        engine = build_engine("sqlite+aiosqlite:///:memory:")
        await create_tables(engine)
        async with build_session_factory(engine)() as session:
            repo = NotificationRepository(session)

            async def add(key, status):
                return await repo.add(
                    Notification(
                        user_id=1,
                        subject_type="dm",
                        subject_key=key,
                        reason="direct_message",
                        title="t",
                        status=status,
                    )
                )

            old_done = await add("a", "done")
            await add("b", "done")  # recent done — kept
            await add("c", "inbox")  # never pruned regardless of age
            old_done.updated_at = utcnow() - timedelta(days=120)
            await repo.save(old_done)

            removed = await repo.prune_done_before(utcnow() - timedelta(days=90))
            assert removed == 1
            remaining = {n.subject_key for n in await repo.list_for_user(1)}
            assert remaining == {"b", "c"}
        await engine.dispose()

    def test_cross_user_patch_is_404(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        create_agent(client, admin, "mobile-eduardo")
        _send(client, admin, "mobile-eduardo", "backend-julio", "oi")
        nid = client.get("/api/notifications", headers=auth(admin)).json()[0]["id"]
        # member cannot touch (or even confirm the existence of) admin's notification
        resp = client.patch(
            f"/api/notifications/{nid}", json={"unread": False}, headers=auth(member)
        )
        assert resp.status_code == 404
