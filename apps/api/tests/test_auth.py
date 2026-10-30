from collections.abc import Awaitable, Callable

from httpx import AsyncClient

PASSWORD = "correct horse battery"
SignUp = Callable[..., Awaitable[dict[str, str]]]
GetToken = Callable[[AsyncClient, str], Awaitable[str]]


async def test_signup_requires_verification_then_login(
    client: AsyncClient, get_token: GetToken
) -> None:
    token = await get_token(client, "Alice@Example.com")

    r = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_not_verified"

    assert (await client.post("/api/v1/auth/verify", json={"token": token})).status_code == 200
    client.cookies.clear()

    r = await client.post(
        "/api/v1/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert r.status_code == 200
    me = (await client.get("/api/v1/auth/me")).json()["data"]
    assert me["email"] == "alice@example.com"
    assert me["email_verified"] is True
    assert me["org"]["plan_id"] == "free"
    assert me["market"] == "in"


async def test_session_cookie_flags(client: AsyncClient, get_token: GetToken) -> None:
    token = await get_token(client, "flags@example.com")
    r = await client.post("/api/v1/auth/verify", json={"token": token})
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("sm_session="))
    csrf = next(c for c in cookies if c.startswith("sm_csrf="))
    assert "HttpOnly" in session
    assert "samesite=lax" in session.lower()
    assert "HttpOnly" not in csrf


async def test_bad_verification_token(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/verify", json={"token": "forged.token.value"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "token_invalid"


async def test_wrong_password_and_duplicate(client: AsyncClient, get_token: GetToken) -> None:
    email = "dup@example.com"
    await get_token(client, email)
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 409
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass-1"})
    assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401


async def test_short_password_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "short@example.com", "password": "short"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_login_rate_limited(client: AsyncClient) -> None:
    body = {"email": "brute@example.com", "password": "wrong-pass-1"}
    codes = [(await client.post("/api/v1/auth/login", json=body)).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


async def test_me_requires_session(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_csrf_required_for_mutations(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    body = {"name": "Site", "domain": "csrf-example.com", "market": "us"}
    r = await client.post("/api/v1/projects", json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = await client.post("/api/v1/projects", json=body, headers={"x-csrf-token": "forged"})
    assert r.status_code == 403
    r = await client.post("/api/v1/projects", json=body, headers=headers)
    assert r.status_code == 201


async def test_logout(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_market_preference(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    r = await client.patch("/api/v1/auth/me", json={"market": "us"}, headers=headers)
    assert r.json()["data"]["market"] == "us"
    r = await client.patch("/api/v1/auth/me", json={"market": "uk"}, headers=headers)
    assert r.status_code == 422


async def test_signup_never_returns_verification_link(client: AsyncClient, outbox: list) -> None:  # type: ignore[type-arg]
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "nolink@example.com", "password": PASSWORD}
    )
    assert r.status_code == 201
    assert "token" not in r.text and "verify" not in r.text.lower().replace("verification", "")
    mail = [m for m in outbox if m.to == "nolink@example.com"]
    assert len(mail) == 1 and "/verify?token=" in mail[0].text
    assert "sm_session" not in r.headers.get("set-cookie", "")  # signup alone never logs in


async def test_resend_verification(client: AsyncClient, outbox: list) -> None:  # type: ignore[type-arg]
    email = "resend@example.com"
    await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    r = await client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert r.status_code == 202
    assert len([m for m in outbox if m.to == email]) == 2

    # unknown email: same response, nothing sent (no account enumeration)
    before = len(outbox)
    r = await client.post("/api/v1/auth/resend-verification", json={"email": "ghost@example.com"})
    assert r.status_code == 202 and len(outbox) == before
