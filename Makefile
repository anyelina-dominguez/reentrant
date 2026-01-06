PY ?= python3.12

.PHONY: test check

test:
	$(PY) -m unittest discover -s tests -t . -q

check:
	$(PY) -c "import reentrant; print(reentrant.__version__)"
