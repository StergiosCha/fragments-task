# Common tasks. Run `make help` for the list.
PYTHON ?= python3

.PHONY: help ladr test generate check-gold validate score

SEED ?= 0
FRAGMENT ?= fragments/practice_seed0
SUBMISSION ?=
JSON ?=
OUT ?= out/seed$(SEED)
ARGS ?=

help:
	@echo "make ladr   build the pinned Prover9/Mace4 into ./.ladr (then: export PATH=\$$PWD/.ladr/bin:\$$PATH)"
	@echo "make test   run the test suite"
	@echo "make generate SEED=7 OUT=out/seed7 [ARGS='--n-parse 20 --n-interp 20 --n-infer 12']"
	@echo "            generate a fragment with gold (needs LADR)"
	@echo "make check-gold OUT=out/seed7   check that fragment's gold independently"
	@echo "make score FRAGMENT=fragments/practice_seed0 SUBMISSION=my_submission [JSON=results.json]"
	@echo "            score a submission directory (format: docs/SUBMISSION.md)"

ladr:
	scripts/install_ladr.sh .ladr

test:
	$(PYTHON) -m pytest -q -rs

generate:
	cd generator && $(PYTHON) gen.py --seed $(SEED) --out $(abspath $(OUT)) $(ARGS)

check-gold:
	cd generator && $(PYTHON) check_gold.py $(foreach v,nonce english scrambled counter,$(abspath $(OUT))/$(v))

score:
	cd generator && $(PYTHON) score.py --fragment $(abspath $(FRAGMENT)) --submission $(abspath $(SUBMISSION)) \
		$(if $(JSON),--json $(abspath $(JSON)))
