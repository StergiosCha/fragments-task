# Common tasks. Run `make help` for the list.
PYTHON ?= python3

.PHONY: help ladr test

help:
	@echo "make ladr   build the pinned Prover9/Mace4 into ./.ladr (then: export PATH=\$$PWD/.ladr/bin:\$$PATH)"
	@echo "make test   run the test suite"

ladr:
	scripts/install_ladr.sh .ladr

test:
	$(PYTHON) -m pytest -q -rs
