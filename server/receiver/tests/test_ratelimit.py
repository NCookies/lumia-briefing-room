from uuid import uuid4

from fastapi.testclient import TestClient

from app.alerts import Alerter, mask_ip
from app.config import Settings
from app.main import create_app
from app.ratelimit import RateLimiter
from tests.test_api import TOKEN, headers, label_body


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def limiter(clock, **kw):
    args = dict(window_sec=600, max_requests=5, max_failures=3, block_sec=3600, clock=clock, on_block=None)
    args.update(kw)
    return RateLimiter(**args)


def test_allows_requests_under_the_limit_and_blocks_over_it():
    clock = Clock()
    rl = limiter(clock)
    assert all(rl.allow("1.1.1.1") for _ in range(5))
    assert not rl.allow("1.1.1.1")
    assert rl.allow("2.2.2.2")


def test_window_slides_so_slow_clients_are_never_blocked():
    clock = Clock()
    rl = limiter(clock)
    for _ in range(20):
        assert rl.allow("1.1.1.1")
        clock.now += 200


def test_repeated_failures_block_the_address_until_it_expires():
    clock = Clock()
    events = []
    rl = limiter(clock, on_block=lambda ip, reason: events.append((ip, reason)))
    for _ in range(3):
        rl.record_failure("9.9.9.9")
    assert not rl.allow("9.9.9.9")
    assert events == [("9.9.9.9", "failures")]
    clock.now += 3601
    assert rl.allow("9.9.9.9")


def test_block_event_fires_once_per_block_not_per_request():
    clock = Clock()
    events = []
    rl = limiter(clock, on_block=lambda ip, reason: events.append(reason))
    for _ in range(50):
        rl.allow("1.1.1.1")
    assert events == ["requests"]


def test_memory_is_bounded_by_dropping_expired_entries():
    clock = Clock()
    rl = limiter(clock, max_tracked=10)
    for i in range(10):
        rl.allow(f"10.0.0.{i}")
    clock.now += 700
    rl.allow("10.0.1.1")
    assert rl.tracked() <= 2


def test_mask_ip_hides_the_host_part():
    assert mask_ip("203.0.113.77") == "203.0.*.*"
    assert mask_ip("2001:db8:85a3::1") == "2001:db8:*"
    assert mask_ip("garbage") == "?"


def test_alerter_sends_and_caps_the_number_of_alerts_per_hour():
    clock, sent = Clock(), []
    alerter = Alerter(send=sent.append, max_per_hour=2, clock=clock, run=lambda f, *a: f(*a))
    for i in range(5):
        alerter.notify(f"m{i}")
    assert sent == ["m0", "m1"]
    clock.now += 3601
    alerter.notify("later")
    assert sent[-1] == "later"


def test_alerter_swallows_send_failures():
    def boom(_):
        raise RuntimeError("discord down")

    Alerter(send=boom, max_per_hour=5, clock=Clock(), run=lambda f, *a: f(*a)).notify("x")


def make_client(tmp_path, alerts, **kw):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=100_000, **kw)
    alerter = Alerter(send=alerts.append, max_per_hour=10, clock=Clock(), run=lambda f, *a: f(*a))
    return TestClient(create_app(settings, alerter=alerter))


def test_api_blocks_an_address_after_repeated_bad_requests_and_alerts_without_the_full_ip(tmp_path):
    alerts = []
    c = make_client(tmp_path, alerts, rate_limit_failures=3)
    ip = {"X-Forwarded-For": "203.0.113.77"}
    for _ in range(3):
        assert c.post("/v1/labels", json=label_body(uuid4()), headers={**ip, **headers("bad")}).status_code == 401
    r = c.post("/v1/labels", json=label_body(uuid4()), headers={**ip, **headers()})
    assert r.status_code == 429 and r.headers["Retry-After"]
    assert len(alerts) == 1 and "203.0.*.*" in alerts[0] and "113.77" not in alerts[0]
    other = {"X-Forwarded-For": "198.51.100.5"}
    assert c.post("/v1/labels", json=label_body(uuid4()), headers={**other, **headers()}).status_code == 200


def test_api_counts_schema_violations_and_unknown_routes_as_failures(tmp_path):
    alerts = []
    c = make_client(tmp_path, alerts, rate_limit_failures=3)
    ip = {"X-Forwarded-For": "203.0.113.9", **headers()}
    bad = label_body(uuid4())
    bad["mode"] = "staging"
    assert c.post("/v1/labels", json=bad, headers=ip).status_code == 422
    assert c.get("/v1/nothing", headers=ip).status_code == 404
    assert c.get("/v1/labels", headers=ip).status_code == 405
    assert c.post("/v1/labels", json=label_body(uuid4()), headers=ip).status_code == 429


def test_client_ip_is_the_last_forwarded_address_so_a_forged_header_does_not_help(tmp_path):
    alerts = []
    c = make_client(tmp_path, alerts, rate_limit_failures=2)
    for forged in ("1.2.3.4", "5.6.7.8"):
        h = {"X-Forwarded-For": f"{forged}, 203.0.113.50", **headers("bad")}
        c.post("/v1/labels", json=label_body(uuid4()), headers=h)
    r = c.post("/v1/labels", json=label_body(uuid4()), headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.50", **headers()})
    assert r.status_code == 429


def test_healthz_is_never_limited(tmp_path):
    alerts = []
    c = make_client(tmp_path, alerts, rate_limit_requests=2)
    assert all(c.get("/healthz").status_code == 200 for _ in range(10))


def test_rate_limit_can_be_disabled(tmp_path):
    c = make_client(tmp_path, [], rate_limit_requests=0, rate_limit_failures=0)
    assert all(c.post("/v1/labels", json=label_body(uuid4()), headers=headers("bad")).status_code == 401 for _ in range(50))
