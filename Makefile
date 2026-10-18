PYTHON ?= python3

.PHONY: validate corpus envelopes policies restore negative test results check-generated ci e2e

validate:            ## Evidence packages: schema + real digests + fail-closed rules
	PYTHON=$(PYTHON) ./scripts/validate-evidence.sh

corpus:              ## Agent security corpus through the gate (writes results/envelopes/)
	$(PYTHON) -m tools.run_corpus

envelopes:           ## Verify every retained envelope
	$(PYTHON) -m tools.envelope

policies:            ## Chapter 13-14 policy schemas + admission fixtures
	$(PYTHON) -m tools.check_policies

restore:             ## Recovery Contract decisions over RestorePoint files
	$(PYTHON) -m tools.check_restore

negative:            ## Mutations that must be rejected
	$(PYTHON) -m tools.negative_checks

test:                ## pytest suite (includes the negative checks)
	$(PYTHON) -m pytest -q

results:             ## Regenerate results/results.json and docs/EVIDENCE.md
	$(PYTHON) -m tools.build_results

check-generated:     ## Fail if committed results differ from a fresh run
	$(PYTHON) -m tools.build_results --run-metadata
	git diff --exit-code -- results docs/EVIDENCE.md

ci: validate corpus envelopes policies restore negative test check-generated

e2e:                 ## PreSync gate on kind + Argo CD (needs Docker, kind, kubectl; see cluster/README.md)
	PYTHON=$(PYTHON) ./cluster/e2e.sh
