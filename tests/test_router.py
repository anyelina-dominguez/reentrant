from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.api.http import handle
from reentrant.api.router import METHODS, Router
from reentrant.errors import NotFoundError, ValidationError


class Routing(unittest.TestCase):
    def test_a_literal_beats_a_parameter(self):
        router = Router()
        router.get("/entries/:reference", lambda **_: "parameter")
        router.get("/entries/search", lambda **_: "literal")
        self.assertEqual(router.match("GET", "/entries/search")[0](), "literal")
        self.assertEqual(router.match("GET", "/entries/ENT-1")[0](), "parameter")

    def test_a_known_path_with_the_wrong_method_is_405(self):
        router = Router()
        router.get("/entries", lambda **_: [])
        with self.assertRaises(ValidationError) as caught:
            router.match("DELETE", "/entries")
        self.assertEqual(caught.exception.status, 405)
        self.assertEqual(caught.exception.details["allowed"], ["GET"])

    def test_a_path_that_does_not_exist(self):
        router = Router()
        router.get("/entries", lambda **_: [])
        self.assertRaises(NotFoundError, router.match, "GET", "/nothing")

    def test_only_the_methods_that_exist(self):
        router = Router()
        self.assertRaises(ValidationError, router.add, "FETCH", "/x", lambda **_: None)
        self.assertEqual(METHODS[0], "GET")

    def test_parameters_are_url_decoded(self):
        router = Router()
        router.get("/clubs/:name", lambda **kwargs: kwargs["params"]["name"])
        self.assertEqual(router.match("GET", "/clubs/Dark%20Peak")[1]["name"], "Dark Peak")

    def test_mounting_one_router_inside_another(self):
        inner = Router()
        inner.get("/entries", lambda **_: "inner")
        outer = Router().mount("/api", inner)
        self.assertEqual(outer.match("GET", "/api/entries")[0](), "inner")


class Handling(unittest.TestCase):
    def setUp(self):
        self.router = Router()
        self.router.get("/thing/:id", lambda **kwargs: {"id": kwargs["params"]["id"]})
        self.router.post("/thing", lambda **kwargs: {"made": kwargs["body"]})
        self.router.get("/query", lambda **kwargs: kwargs["query"])
        self.router.get("/teapot", lambda **_: (418, {"short": "stout"}))
        self.router.get("/broken", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))

    def test_a_get_is_200_and_a_post_is_201(self):
        self.assertEqual(handle(self.router, None, "GET", "/thing/7"), (200, {"id": "7"}))
        self.assertEqual(handle(self.router, None, "POST", "/thing", body={"a": 1}),
                         (201, {"made": {"a": 1}}))

    def test_a_handler_may_choose_its_own_status(self):
        self.assertEqual(handle(self.router, None, "GET", "/teapot"), (418, {"short": "stout"}))

    def test_the_query_string_reaches_the_handler(self):
        self.assertEqual(handle(self.router, None, "GET", "/query", {"a": "1"}), (200, {"a": "1"}))

    def test_an_unexpected_error_is_a_500_that_names_itself(self):
        status, body = handle(self.router, None, "GET", "/broken")
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "RuntimeError")
        self.assertEqual(body["message"], "boom")

    def test_a_missing_route_and_a_wrong_method(self):
        self.assertEqual(handle(self.router, None, "GET", "/nowhere")[0], 404)
        self.assertEqual(handle(self.router, None, "DELETE", "/thing/7")[0], 405)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
