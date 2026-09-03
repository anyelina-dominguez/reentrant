PY ?= python3.12

.PHONY: test check examples all

test:
	$(PY) -m unittest discover -s tests -t . -q

check:
	PYTHONPATH=src $(PY) -c "import reentrant; print(reentrant.__version__)"
	PYTHONPATH=src $(PY) -m reentrant.cli.main check --event data/example-event.json

examples:
	$(PY) examples/plan_check.py > /dev/null
	$(PY) examples/run_the_day.py > /dev/null

all: test check examples
