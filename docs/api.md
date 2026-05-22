# The http surface

    reentrant serve --port 8080 --event event.json

JSON in, JSON out. No authentication: this runs on the laptop in the download
tent, on a network with four devices on it.

Statuses are the four the error kinds map to -- 400 for a value that is not
legal, 404 for something that does not exist, 409 for something the records or
the rules forbid, 500 for a bug -- plus 405 when the path exists and the method
does not.

## The event

| method | path | |
|---|---|---|
| GET | `/health` | |
| GET | `/event` | counts and the entries per course |
| GET | `/event/check` | what would stop the event running, plus the controller's notes |
| GET/POST | `/controls` | |
| GET | `/controls/:code` | |
| GET/POST | `/courses` | |
| GET | `/courses/:name` | with its legs and description sheet |
| GET | `/classes` | |
| PUT | `/classes/:code` | point a class at a course |

## Entries and starts

| method | path | |
|---|---|---|
| GET/POST | `/entries` | `?course=` `?class=` `?club=` |
| GET/PATCH/DELETE | `/entries/:reference` | |
| GET | `/cards/:card` | who is on a card |
| POST | `/starts/draw` | `{ first, interval, seed }` |
| GET | `/starts` | the list in time order |

## The day

| method | path | |
|---|---|---|
| POST | `/download` | a card read in, a slip out |
| GET | `/downloads` | the log |
| GET | `/outstanding` | who has started and not come back |
| GET | `/results` | `?by=course` |
| GET | `/results/classes/:code` | |
| GET | `/splits/:name` | one course, with the analysis |
| GET | `/board` | `?shown=5`, the provisional sheet |

## The desk

| method | path | |
|---|---|---|
| GET | `/hire` | what is in the box and what is out |
| POST | `/hire/stock` | `{ cards: [...] }` |
| POST | `/hire` | lend one |
| DELETE | `/hire/:card` | take one back |
| GET/POST | `/corrections` | decisions about a run |
| GET/POST | `/complaints` | |
| POST | `/complaints/:reference/answer` | the organiser answers |

## The season

| method | path | |
|---|---|---|
| GET/POST | `/fixtures` | `?on=2026-10-15` for the calendar |
| GET/DELETE | `/fixtures/:name` | delete cancels |
| POST | `/fixtures/:name/entries` | |

## Testing against it

`src/reentrant/api/testapp.py` drives the same handlers without a socket:

```python
from reentrant.api.testapp import test_app
client = test_app(context)
status, body = client.get("/entries?course=Blue")
```

`tests/test_api.py` also runs a handful of requests through a real server, so
the two cannot drift apart.
