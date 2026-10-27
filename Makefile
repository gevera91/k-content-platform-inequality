PYTHON ?= python3

.PHONY: replicate test
replicate:
	$(PYTHON) scripts/replicate.py --profile full

test:
	$(PYTHON) -m unittest discover -s tests -v
