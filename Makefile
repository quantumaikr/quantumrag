VENV := .venv/bin

.PHONY: check lint test quick smoke fix coverage scenario-test typecheck scale-test help

## ---------------------------------------------------------------------------
##  빠른 검증 (일상 개발용)
## ---------------------------------------------------------------------------

quick: lint  ## 빠른 검증: lint만 (0.1초)
	@echo "OK"

smoke: lint  ## 스모크 테스트: lint + 핵심 테스트 (2초)
	@$(VENV)/python -m pytest tests/unit/test_engine.py tests/unit/test_config.py tests/unit/test_pipeline.py -q --tb=short -x

## ---------------------------------------------------------------------------
##  전체 검증 (커밋/PR 전)
## ---------------------------------------------------------------------------

check: lint test  ## 전체 검증: lint + 전체 유닛 테스트 (7초)

lint:
	@$(VENV)/ruff check quantumrag/ --select E9,F63,F7,F82 --quiet
	@$(VENV)/ruff format --check quantumrag/ --quiet

test:
	@$(VENV)/python -m pytest tests/unit/ -q --tb=short -x

## ---------------------------------------------------------------------------
##  타겟 테스트 (변경 영역만)
## ---------------------------------------------------------------------------

test-gen:  ## generate/ 관련 테스트만
	@$(VENV)/python -m pytest tests/unit/test_evaluation.py tests/unit/test_postprocess.py tests/unit/test_rewriter.py tests/unit/test_fact_verifier.py tests/unit/test_completeness.py -q --tb=short -x

test-ret:  ## retrieve/ 관련 테스트만
	@$(VENV)/python -m pytest tests/unit/test_retrieval.py tests/unit/test_rerankers_and_budget.py tests/unit/test_slow_retrieval.py tests/unit/test_storage.py -q --tb=short -x

test-ingest:  ## ingest/ 관련 테스트만
	@$(VENV)/python -m pytest tests/unit/test_chunkers.py tests/unit/test_parsers.py tests/unit/test_ingest_modes.py -q --tb=short -x

test-api:  ## api/cli 관련 테스트만
	@$(VENV)/python -m pytest tests/unit/test_api.py tests/unit/test_cli.py tests/unit/test_middleware_security.py -q --tb=short -x

## ---------------------------------------------------------------------------
##  심층 검증 (릴리스/큰 변경 후)
## ---------------------------------------------------------------------------

scenario-test:  ## 시나리오 테스트 (hard/extreme)
	@$(VENV)/python tests/scenarios/v4/run_hard_only.py

coverage:  ## 유닛 테스트 + 커버리지 리포트
	@$(VENV)/python -m pytest tests/unit/ -q --tb=short \
		--cov=quantumrag --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml

typecheck:  ## mypy 타입 체크
	@$(VENV)/mypy quantumrag/ --ignore-missing-imports --no-error-summary || true

MULT ?= 10
scale-test:  ## 스케일 테스트: make scale-test MULT=10
	@$(VENV)/python tests/scale/run_scale_test.py --multiplier $(MULT)

## ---------------------------------------------------------------------------
##  유틸리티
## ---------------------------------------------------------------------------

fix:  ## 린트 자동 수정
	@$(VENV)/ruff check quantumrag/ tests/ --fix
	@$(VENV)/ruff format quantumrag/ tests/

help:  ## 사용 가능한 명령어 목록
	@echo "사용법: make [command]"
	@echo ""
	@echo "일상 개발:"
	@echo "  quick         lint만 (0.1초)"
	@echo "  smoke         lint + 핵심 테스트 (2초)"
	@echo ""
	@echo "변경 영역별:"
	@echo "  test-gen      generate 관련 테스트"
	@echo "  test-ret      retrieve 관련 테스트"
	@echo "  test-ingest   ingest 관련 테스트"
	@echo "  test-api      api/cli 관련 테스트"
	@echo ""
	@echo "전체/심층:"
	@echo "  check         lint + 전체 유닛 (7초)"
	@echo "  scenario-test 시나리오 테스트"
	@echo "  coverage      커버리지 리포트"
	@echo ""
	@echo "유틸리티:"
	@echo "  fix           린트 자동 수정"
